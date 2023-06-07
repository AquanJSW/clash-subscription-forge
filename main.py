#!/usr/bin/env python3
import argparse
import asyncio
import gzip
import io
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml
from colored import fg

from clash import Clash
from globals import CACHE_DIR, CLASH_PATH, CLASH_URL, logger
from subscription import ProxiesFilter, Subscription
from template import Template
from utils import get_retry_session, is_path_writable


class MyFormatter(logging.Formatter):
    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = "[%(levelname)s] %(message)s"

    FORMATS = {
        logging.DEBUG: fg(14) + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


# Initiate logger
handler = logging.StreamHandler()
handler.setFormatter(MyFormatter())
logger.addHandler(handler)
logger.setLevel(os.environ.get('LOGLEVEL', 'INFO').upper())

# Make cache directory
logger.debug(f'creating cache dir {CACHE_DIR}')
os.makedirs(CACHE_DIR, exist_ok=True)

# Prepare Clash binary
if not CLASH_PATH.exists:
    logger(f'downloading clash bin from {CLASH_URL}')
    clash_data = gzip.decompress(requests.get(CLASH_URL).content)
    with open(CLASH_PATH, 'wb') as fs:
        fs.write(clash_data)


# Parse arguments
parser = argparse.ArgumentParser()
# fmt: off
parser.add_argument('-s', '--subscriptions', help='subscription urls', nargs='+')
parser.add_argument('-t', '--templates', help='templates paths', nargs='+')
parser.add_argument('-o', '--outputs', help='output paths', nargs='+')
parser.add_argument('-c', '--cache', help='using cache instead of re-download to speed up test', action='store_true')
parser.add_argument('-d', '--days', help='cache live time in days, 0 for eternal', default=30)
parser.add_argument('-p', '--patterns', help='proxy name patterns for filtering', nargs='*')
# fmt: on
args = parser.parse_args()


def cache_subscription_config(subscription):
    config_path = CACHE_DIR / subscription.cache_filename
    with open(config_path, 'w') as fs:
        logger.debug(f'caching clash configuration {config_path}')
        yaml.safe_dump(subscription.config, fs, allow_unicode=True)


def download_config(url):
    response = requests.get(url, allow_redirects=True)
    return yaml.safe_load(io.StringIO(response.text))


def load_cache_config(filepath):
    with open(filepath) as fs:
        config = yaml.safe_load(fs)
    logger.info(f'load config from cache {filepath}')
    return config


def load_config(url) -> dict:
    # if enable cache, load config from cache
    if args.cache:
        try:
            filepath = CACHE_DIR / (urlparse(url).hostname + '.yaml')
            age = (
                datetime.now() - datetime.fromtimestamp(os.path.getmtime(filepath))
            ).days
            if age < args.days:
                logger.info(f'safe age for {filepath}: {age} < {args.days}')
                config = load_cache_config(filepath)
                return config
            logger.info(f'unsafe age for {filepath}: {age} >= {args.days}')
        except FileNotFoundError:
            logger.warning(f'cache config not found, turn to download')
    # if disable cache or fail to loading cache, download from url
    logger.info(f'downloading config from {url}')
    session = get_retry_session(3)
    config = yaml.safe_load(io.StringIO(session.get(url, allow_redirects=True).text))
    return config


def prepare_clash():
    if os.path.exists(CLASH_PATH):
        logger.info(f'clash binary exists: {CLASH_PATH}')
    else:
        logger.info(f'downloading clash binary from {CLASH_URL}')
        data = requests.get(CLASH_URL).content
        data = gzip.decompress(data)
        with open(CLASH_PATH, 'wb') as fs:
            fs.write(data)
        os.chmod(CLASH_PATH, 0o755)
    Clash.bin_path = CLASH_PATH


async def main():
    # Make output directories
    [os.makedirs(Path(path).parent, exist_ok=True) for path in args.outputs]
    # Make sure the output paths are writable
    if not all([is_path_writable(path) for path in args.outputs]):
        sys.exit(1)
    # load configs
    configs = [load_config(url) for url in args.subscriptions]
    prev_lens = [len(config['proxies']) for config in configs]
    # prepare clash
    prepare_clash()

    # Create subscription instances
    subscriptions = [
        Subscription(url, config) for url, config in zip(args.subscriptions, configs)
    ]
    # cache subscription config
    [cache_subscription_config(subscription) for subscription in subscriptions]

    # Init filter
    proxiesFilter = ProxiesFilter(args.patterns)
    # filter proxies
    for subscription in subscriptions:
        logger.info(f'start filtering {subscription.id}')
        subscription.config['proxies'] = await proxiesFilter.filter(
            subscription.config['proxies']
        )
    
    # log
    for i in range(len(configs)):
        name = subscriptions[i].id
        prev_len = prev_lens[i]
        now_len = len(subscriptions[i].config['proxies'])
        logger.info(f'change of {name}: {prev_len} -> {now_len}')

    # load templates
    templates = [Template(template) for template in args.templates]
    # fit template
    configs = [template.fit(subscriptions) for template in templates]
    # save fitted configs
    for path, config in zip(args.outputs, configs):
        with open(path, 'w') as fs:
            logger.info(f'saving config {path}')
            yaml.safe_dump(config, fs, allow_unicode=True)


if __name__ == '__main__':
    asyncio.run(main())
