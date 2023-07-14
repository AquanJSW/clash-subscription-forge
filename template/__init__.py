import copy
import logging

import yaml

import globals
from subscription import Subscription

logger = logging.getLogger(globals.APP_NAME)


class Template:
    def __init__(self, path) -> None:
        with open(path) as fs:
            logger.info(f'loading template from {path}')
            self.config: dict = yaml.safe_load(fs)

    def fit(self, subscriptions: list[Subscription]):
        proxies = []
        # joint proxies
        for subscription in subscriptions:
            proxies += subscription.config['proxies']
        names = [proxy['name'] for proxy in proxies]
        # fit
        config = copy.deepcopy(self.config)
        if 'proxies' not in config:
            config['proxies'] = []
        config['proxies'] += proxies
        for proxy_group in config['proxy-groups']:
            # skip if keep == True
            if proxy_group.get('keep', False):
                continue
            proxy_group['proxies'] = proxy_group.get('proxies', []) + names
        return config
