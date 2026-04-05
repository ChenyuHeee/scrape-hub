"""
Scrape Hub API server entry point.

Usage:
    uvicorn scrape_hub.api.server:app --host 0.0.0.0 --port 8000
"""

from scrape_hub.api import app  # noqa: F401
