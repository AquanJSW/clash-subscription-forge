import logging
from pathlib import Path

import appdirs

APP_NAME = 'clash-subscription-forge'
CACHE_DIR = Path(appdirs.user_cache_dir(appname=APP_NAME))
CLASH_URL = 'https://github.com/Dreamacro/clash/releases/download/v1.16.0/clash-linux-amd64-v1.16.0.gz'
CLASH_PATH = CACHE_DIR / 'clash'

logger = logging.getLogger(APP_NAME)
