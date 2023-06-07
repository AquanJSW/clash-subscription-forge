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
        config['proxies'] = proxies
        for proxy_group in config['proxy-groups']:
            # create if no proxies
            if 'proxies' not in proxy_group:
                proxy_group['proxies'] = names
            # append otherwise
            else:
                proxy_group['proxies'] += names
        return config
