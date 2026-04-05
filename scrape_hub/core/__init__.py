"""Core abstractions for scrape-hub."""

from scrape_hub.core.base_scraper import BaseScraper
from scrape_hub.core.browser import BrowserManager
from scrape_hub.core.storage import Storage

__all__ = ["BaseScraper", "BrowserManager", "Storage"]
