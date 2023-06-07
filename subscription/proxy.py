import copy

import yaml


class Proxy:
    def __init__(self, raw: dict) -> None:
        self.raw = raw
        self.ingress_ip: str = ...
        self.egress_ip: str = ...

    def __getitem__(self, key):
        return self.raw[key]

    def __hash__(self):
        return hash((self.ingress_ip, self.egress_ip))

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __str__(self):
        obj = copy.deepcopy(self.raw)
        obj['ingress-ip'] = self.ingress_ip if self.ingress_ip != ... else ''
        obj['egress-ip'] = self.egress_ip if self.egress_ip != ... else ''
        return yaml.safe_dump(obj, allow_unicode=True)

    @staticmethod
    def convert_proxies_to_string(proxies: list):
        sep = '\n' + '-' * 79 + '\n'
        return sep.join([str(proxy) for proxy in proxies])
