import asyncio
import logging
import sys
import time
from ipaddress import ip_address

import yaml
from tqdm import tqdm

from clash import Clash
from globals import logger
from utils import convert_host_to_ip, get_egress_ip, get_tcp_port_picker

from .proxy import Proxy


class ProxiesFilter:
    def __init__(self, patterns: list[str] = ...) -> None:
        # list of str patterns used to filter by name
        self.patterns = patterns

        # a dict of {'checkpoint description': count} as a log of filtering
        self.count_log = {}

    def _filter_by_patterns(self, proxies: list[dict]):
        # log count
        self.count_log['init'] = len(proxies)

        # no patterns, no filtering
        if self.patterns == ...:
            return proxies

        # has patterns, start filtering
        ret = []
        for proxy in proxies:
            for pattern in self.patterns:
                if proxy['name'].find(pattern) > -1:
                    logger.debug(
                        f'filtered out by pattern {pattern}:\n{yaml.safe_dump(proxy)}'
                    )
                    break
            else:
                ret.append(proxy)

        # log count
        self.count_log['after pattern filtering'] = len(ret)
        return ret

    @staticmethod
    async def _update_egress_ips(proxies: list[Proxy]):
        """

        As a result, only the proxies with valid egress IPs are updated.
        """
        poll_timeout = 3
        ping_retry = 1

        # form a simple temp clash config
        raw_proxies = [proxy.raw for proxy in proxies]
        tcp_port_picker = get_tcp_port_picker()
        port, external_controller_port = [next(tcp_port_picker) for _ in range(2)]
        config = {
            'mixed-port': port,
            'external-controller': f'localhost:{external_controller_port}',
            'ipv6': True,
            'mode': 'global',
            'proxies': raw_proxies,
            'log-level': 'warning',
        }
        # start clash process
        clash = Clash(config)
        clash.run()
        while poll_timeout != 0:
            if clash.is_ready:
                break
            time.sleep(1)
        else:
            logger.error(f'clash initialization polling failed')
            sys.exit(1)

        # using ping for pre-filtering, which will relieve the egress IP
        # getting process
        names = set()
        while ping_retry != 0:
            ping_responses = await clash.ping_all()
            names |= set(
                filter(
                    lambda name: 'delay' in ping_responses[name].keys(), ping_responses
                )
            )
            ping_retry -= 1

        # form a name-proxy dict for fast query
        querier = dict(((proxy['name'], proxy) for proxy in proxies))
        # updating egress IPs
        local_proxy = {
            'https': f'socks5://localhost:{clash.port}',
            'http': f'socks5://localhost:{clash.port}',
        }
        if logger.level == logging.getLevelName('DEBUG'):
            for name in sorted(names):
                if not clash.select('GLOBAL', name):
                    sys.exit(1)
                egress_ip = get_egress_ip(local_proxy)
                querier[name].egress_ip = egress_ip
                logger.info(f'[egress] {name} {egress_ip}')
        else:
            for name in tqdm(sorted(names), 'updating egress IPs'):
                if not clash.select('GLOBAL', name):
                    sys.exit(1)
                egress_ip = get_egress_ip(local_proxy)
                querier[name].egress_ip = egress_ip
        del clash
        return proxies

    async def _filter_by_ingress_ip(self, proxies: list[dict]):
        proxies: list[Proxy] = [Proxy(proxy) for proxy in proxies]

        # get ingress ips
        ingress_ips = await asyncio.gather(
            *[convert_host_to_ip(proxy['server']) for proxy in proxies]
        )
        for i in range(len(proxies)):
            proxies[i].ingress_ip = ingress_ips[i]

        # filter out proxies with empty ingress IPs
        proxies = self._filter(
            proxies, lambda proxy: proxy.ingress_ip != '', 'empty ingress IP'
        )

        # filter out proxies with non-global ingress IPs
        proxies = self._filter(
            proxies,
            lambda proxy: ip_address(proxy.ingress_ip).is_global,
            'non-global ingress IP',
        )

        return proxies

    def _filter(self, proxies: list[Proxy], fn: callable, reason: str):
        """Return proxies that `fn(proxy)` returns True."""
        prev_proxies = proxies
        invalid_proxies = []
        proxies = []
        for proxy in prev_proxies:
            if fn(proxy):
                proxies.append(proxy)
                continue
            invalid_proxies.append(proxy)
        if invalid_proxies:
            logger.debug(
                f'{len(invalid_proxies)} proxies are filtered out because of {reason}:\n{Proxy.convert_proxies_to_string(invalid_proxies)}'
            )
        self.count_log[f'after {reason} filter'] = len(proxies)
        return proxies

    async def _filter_by_egress_ip(self, proxies: list[Proxy]):
        # update egress IPs
        proxies = await self._update_egress_ips(proxies)

        # filter out proxies with empty egress IPs
        proxies = self._filter(
            proxies, lambda proxy: proxy.egress_ip != ..., 'empty egress IP'
        )

        return proxies

    def _filter_duplicated(self, proxies: list[Proxy]):
        # classify by creating a dict of `{hash: [proxies]}`
        classification = {}
        for proxy in proxies:
            if hash(proxy) in classification:
                classification[hash(proxy)].append(proxy)
                continue
            classification[hash(proxy)] = [proxy]

        # log
        proxies_string_list = [
            Proxy.convert_proxies_to_string(proxy_list)
            for proxy_list in classification.values()
        ]
        sep = '\n' + '=' * 80 + '\n'
        debug_string = sep.join(proxies_string_list)
        logger.debug(f'duplication check:\n{debug_string}')

        # extract unique proxies
        proxies = [proxies_list[0] for proxies_list in classification.values()]
        self.count_log['after duplication filtering'] = len(proxies)

        # log
        log_string = ''
        for msg, count in self.count_log.items():
            log_string += f'{msg}: {count}\n'
        logger.debug(f'filtering records:\n{log_string.strip()}')
    
        return proxies

    async def _filter_by_ip(self, proxies: list[dict]):
        """

        Filter out redundant proxies that
            1. have no ingress IPs, i.e. no nslookup records;
            2. have non-global ingress IPs;
            3. have no egress IPs, i.e. clash ping timeout;
            4. are duplicated in both ingress and egress IPs
        """
        # filter by ingress ip
        proxies = await self._filter_by_ingress_ip(proxies)

        # filter by egress ip
        proxies = await self._filter_by_egress_ip(proxies)

        # filter out proxies that duplicated in both ingress and egress IPs
        proxies = self._filter_duplicated(proxies)

        return [proxy.raw for proxy in proxies]

    async def filter(self, proxies: list[dict]):
        # reset
        self.count_log = {}

        # filter by proxy name patterns
        proxies = self._filter_by_patterns(proxies)

        # filter by IP
        proxies = await self._filter_by_ip(proxies)

        return proxies
