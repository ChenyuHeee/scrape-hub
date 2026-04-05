"""Platform-specific scrapers."""

from scrape_hub.platforms.x_twitter import XTwitterScraper
from scrape_hub.platforms.wechat import WeChatScraper

__all__ = ["XTwitterScraper", "WeChatScraper"]
