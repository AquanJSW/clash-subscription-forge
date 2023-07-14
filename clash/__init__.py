import asyncio
import functools
import json
import os
import subprocess
import tempfile

import requests
import yaml
from requests.adapters import HTTPAdapter

from globals import logger
from utils import get_retry_session


class Clash:
    bin_path: str = ...
    timeout = 2000
    delay_test_url = 'http://www.gstatic.com/generate_204'

    def __init__(self, config: dict) -> None:
        self.config = config

        # create tempfile
        temp = tempfile.NamedTemporaryFile('w', delete=False)
        yaml.safe_dump(config, temp, allow_unicode=True)
        temp.close()

        self.config_path = temp.name
        logger.info(f'creating temp config at {self.config_path}')
        self.process: subprocess.Popen = ...

    @property
    def names(self):
        return [proxy['name'] for proxy in self.config['proxies']]

    def __del__(self):
        # kill process
        self.process.kill()
        # remove temp config
        os.remove(self.config_path)

    def run(self):
        logger.info(f'starting clash...')
        self.process = subprocess.Popen(
            f'{self.bin_path} -f {self.config_path}'.split(' ')
        )

    @property
    def external_controller(self):
        """

        Make sure the 'external-controller' option in the config has full
        format like '127.0.0.1:9090'
        """
        return self.config['external-controller']

    async def ping(self, name) -> dict:
        """

        return - dict of two type
            - `{'delay': 0, 'meanDelay': 0}`
            - `{'message': 'error reason'}`
        """
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=3))
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            functools.partial(
                s.get,
                f'http://{self.external_controller}/proxies/{name}/delay',
                params={'timeout': self.timeout, 'url': self.delay_test_url},
            ),
        )
        logger.debug(f'{name} {response.text.strip()}')
        return json.loads(response.text)

    async def ping_all(self) -> dict[str, dict]:
        """

        return - a dict that
            - its keys are proxies names
            - its values are dicts of the return of @proxy
        """
        responses = await asyncio.gather(*[self.ping(name) for name in self.names])
        return dict(zip(self.names, responses))

    def select(self, selector_name, proxy_name):
        response = requests.put(
            f'http://{self.external_controller}/proxies/{selector_name}',
            data=json.dumps({'name': proxy_name}, ensure_ascii=False).encode('utf-8'),
        )
        if response.status_code != 204:
            logger.warning(
                f'failed to select {proxy_name} in group {selector_name} with status code {response.status_code}'
            )
            return False
        return True

    @property
    def port(self):
        return self.config['mixed-port']

    @property
    def is_ready(self):
        s = get_retry_session(20)
        response = s.get(f'http://{self.external_controller}', proxies=None, timeout=3)
        if response.ok:
            return True
        return False
