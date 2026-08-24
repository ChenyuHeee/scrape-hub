"""WeChat search backends registry."""

from scrape_hub.platforms.wechat.backends.base import WeChatBackend
from scrape_hub.platforms.wechat.backends.metasearch import MetaSearchBackend
from scrape_hub.platforms.wechat.backends.sogou import SogouBackend

BACKENDS: dict[str, type[WeChatBackend]] = {
    SogouBackend.name: SogouBackend,
    MetaSearchBackend.name: MetaSearchBackend,
}

DEFAULT_ENGINES = ["metasearch", "sogou"]

__all__ = ["WeChatBackend", "SogouBackend", "MetaSearchBackend", "BACKENDS", "DEFAULT_ENGINES"]
