import asyncio
import socket
from ipaddress import ip_address
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

from globals import logger


def get_retry_session(n):
    session = requests.session()
    adapter = HTTPAdapter(max_retries=n)
    session.mount('http://', adapter=adapter)
    session.mount('https://', adapter=adapter)
    return session


def get_egress_ip(proxy: dict | None):
    s = get_retry_session(3)
    r = s.get('https://icanhazip.com', proxies=proxy)
    return r.text.strip()


def is_tcp_port_in_use(port: int):
    timeout = 0.01
    addr = '127.0.0.1'
    ret = False
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((addr, port))
        ret = True
        s.close()
    except socket.error:
        pass
    return ret


def get_tcp_port_picker(port=1024):
    max_port = 65535
    while port <= max_port:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('', port))
            sock.close()
            yield port
        except OSError:
            pass
        port += 1

    raise IOError('no free tcp ports')


def is_path_writable(path):
    """

    Warning: This test may override the file of the given path.
    """
    path = Path(path)
    if Path(path).is_dir():
        logger.error(f'output path {path} is a directory')
        return False
    with open(path, 'w') as fs:
        result = fs.writable()
        if not result:
            logger.error(f'non-writable output path {path}')
        return result


async def nslookup(host):
    loop = asyncio.get_event_loop()
    try:
        response = await loop.getaddrinfo(host, None, proto=socket.SOCK_RAW)
    except socket.gaierror:
        # empty record
        return ['']
    # return a list of IPs
    return [r[4][0] for r in response]


async def convert_host_to_ip(host):
    """Convert host(hostname or IP) to IP, the return could be an empty string."""
    try:
        ip_address(host)
        # host itself is an IP, no need to nslookup
        return host
    except:
        result = await nslookup(host)
        return result[0]
