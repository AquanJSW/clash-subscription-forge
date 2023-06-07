from urllib.parse import urlparse

from .proxiesfilter import ProxiesFilter


class Subscription:
    def __init__(self, url: str, config: dict) -> None:
        self.url = url
        self.id = urlparse(url).hostname
        self.cache_filename = self.id + '.yaml'
        self.config = config
