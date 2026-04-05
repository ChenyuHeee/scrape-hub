"""
API client for calling the remote Scrape Hub backend.

Used by the Streamlit frontend when running on Streamlit Cloud
(where Playwright/Chromium is unavailable).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import streamlit as st

# Use httpx if available (lighter), fall back to urllib (stdlib)
try:
    import httpx as _httpx  # type: ignore[import-untyped]
except ImportError:
    _httpx = None  # type: ignore[assignment]

import json
import urllib.request
import urllib.error


@dataclass
class ScrapeResult:
    """Mirror of core.base_scraper.ScrapeResult for API responses."""
    query_type: str
    query_value: str
    items: list[dict]
    collected_at: str = field(default_factory=lambda: datetime.now().isoformat())
    error: str | None = None


def get_api_url() -> str:
    """Get the API backend URL from Streamlit secrets or env."""
    # Streamlit Cloud secrets (preferred)
    url = st.secrets.get("SCRAPE_HUB_API_URL", "") if hasattr(st, "secrets") else ""
    if not url:
        url = os.environ.get("SCRAPE_HUB_API_URL", "")
    return url.rstrip("/")


def get_api_token() -> str:
    """Get the API auth token from Streamlit secrets or env."""
    token = st.secrets.get("SCRAPE_HUB_API_SECRET", "") if hasattr(st, "secrets") else ""
    if not token:
        token = os.environ.get("SCRAPE_HUB_API_SECRET", "")
    return token


def is_remote_mode() -> bool:
    """Check if we should use remote API mode (i.e., API URL is configured)."""
    return bool(get_api_url())


def get_backend_mode() -> str:
    """
    Detect which backend mode to use. Priority:
    1. 'api'    — SCRAPE_HUB_API_URL is set → use FastAPI backend
    2. 'github' — GITHUB_TOKEN + GITHUB_REPO are set → use GitHub Actions
    3. 'local'  — fall back to local Playwright
    """
    if get_api_url():
        return "api"
    # Lazy import to avoid circular dependency
    from scrape_hub.api.github_backend import is_github_mode
    if is_github_mode():
        return "github"
    return "local"


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = get_api_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def api_health_check() -> bool:
    """Check if the remote API backend is reachable."""
    url = get_api_url()
    if not url:
        return False
    try:
        if _httpx is not None:
            r = _httpx.get(f"{url}/health", timeout=5)
            return r.status_code == 200
        else:
            req = urllib.request.Request(f"{url}/health")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
    except Exception:
        return False


def remote_scrape(
    platform: str,
    config: dict[str, Any],
    progress_callback=None,
) -> list[ScrapeResult]:
    """
    Call the remote API to run a scraping task.

    Args:
        platform: "x_twitter" or "wechat"
        config: Platform-specific config dict
        progress_callback: optional callable(current, total, message)

    Returns:
        List of ScrapeResult dataclass instances.
    """
    url = get_api_url()
    if not url:
        raise RuntimeError("SCRAPE_HUB_API_URL is not configured")

    endpoint = f"{url}/scrape"
    payload = {
        "platform": platform,
        "config": config,
        "headless": True,
    }

    if progress_callback:
        progress_callback(0, 1, "正在调用远程 API...")

    try:
        if _httpx is not None:
            r = _httpx.post(
                endpoint,
                json=payload,
                headers=_headers(),
                timeout=300,  # Scraping can take a while
            )
            if r.status_code != 200:
                detail = r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
                raise RuntimeError(f"API 错误 ({r.status_code}): {detail}")
            data = r.json()
        else:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                endpoint,
                data=body,
                headers=_headers(),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode("utf-8"))

    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"无法连接到 API 后端: {e}")

    results = []
    raw_results = data.get("results", [])
    for item in raw_results:
        results.append(ScrapeResult(
            query_type=item["query_type"],
            query_value=item["query_value"],
            items=item["items"],
            collected_at=item.get("collected_at", ""),
            error=item.get("error"),
        ))

    if progress_callback:
        total_items = sum(len(r.items) for r in results)
        progress_callback(
            1, 1,
            f"远程搜索完成！共收集 {total_items} 条 "
            f"(耗时 {data.get('elapsed_seconds', '?')}s)",
        )

    return results
