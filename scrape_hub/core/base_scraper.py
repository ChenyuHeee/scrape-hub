"""Abstract base class for all platform scrapers."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from scrape_hub.core.browser import BrowserManager
from scrape_hub.core.storage import Storage


@dataclass
class ScrapeResult:
    """Container for scraping results from a single query."""

    query_type: str          # e.g. "keyword", "account"
    query_value: str         # the actual search term
    items: list[dict]        # list of scraped items
    collected_at: str = field(default_factory=lambda: datetime.now().isoformat())
    error: str | None = None


class BaseScraper(abc.ABC):
    """
    Abstract base class for all platform scrapers.

    Subclasses must implement:
        - platform_name: str property returning the platform identifier
        - default_config: dict property returning default configuration
        - search(query_type, query_value, **kwargs) -> ScrapeResult
        - on_browser_ready(page): called after browser is launched, before scraping
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        output_dir: str | Path | None = None,
        headless: bool = False,
        browser_data_dir: str | Path | None = None,
    ):
        merged = {**self.default_config}
        if config:
            merged.update(config)
        self.config = merged

        self.output_dir = Path(output_dir or f"data/{self.platform_name}")
        self.headless = headless
        self.browser_data_dir = Path(
            browser_data_dir or f".browser_data/{self.platform_name}"
        )

        self._browser_manager: BrowserManager | None = None
        self._page = None

    # ── abstract interface ──────────────────────────────────

    @property
    @abc.abstractmethod
    def platform_name(self) -> str:
        """Return a short identifier like 'x_twitter' or 'wechat'."""

    @property
    @abc.abstractmethod
    def default_config(self) -> dict[str, Any]:
        """Return default configuration dict (keywords, accounts, etc.)."""

    @abc.abstractmethod
    def search(self, query_type: str, query_value: str, **kwargs) -> ScrapeResult:
        """Execute a single search and return results."""

    def on_browser_ready(self, page) -> None:
        """Hook called after the browser page is ready. Override for login flows etc."""

    # ── public API ──────────────────────────────────────────

    def run(self, progress_callback=None, **kwargs) -> list[ScrapeResult]:
        """
        Execute the full scraping pipeline:
            1. Launch browser
            2. Call on_browser_ready (for login etc.)
            3. Build query list from config
            4. Run each query via search()
            5. Save results
            6. Close browser

        Args:
            progress_callback: optional callable(current, total, message)
                               for real-time progress updates (e.g. Streamlit).
        """
        results: list[ScrapeResult] = []

        def _report(cur, tot, msg):
            print(msg)
            if progress_callback:
                progress_callback(cur, tot, msg)

        with BrowserManager(
            user_data_dir=self.browser_data_dir,
            headless=self.headless,
            locale=self.config.get("locale", "en-US"),
        ) as bm:
            self._browser_manager = bm
            self._page = bm.page

            self.on_browser_ready(self._page)

            queries = self.build_queries()
            total = len(queries)

            for i, (q_type, q_value) in enumerate(queries, 1):
                _report(i, total, f"[{i}/{total}] {q_type}: {q_value}")
                try:
                    result = self.search(q_type, q_value, **kwargs)
                    results.append(result)
                    _report(i, total, f"  → 收集 {len(result.items)} 条")
                except Exception as e:
                    _report(i, total, f"  ✗ 失败: {e}")
                    results.append(ScrapeResult(
                        query_type=q_type,
                        query_value=q_value,
                        items=[],
                        error=str(e),
                    ))

                # Inter-query delay
                if i < total:
                    import time
                    delay = self.config.get("query_delay", 5.0)
                    time.sleep(delay)

        self._page = None
        self._browser_manager = None

        # Save
        if any(r.items for r in results):
            self.save(results)

        return results

    def build_queries(self) -> list[tuple[str, str]]:
        """
        Build a list of (query_type, query_value) from self.config.
        Override for custom query building logic.
        Default: yields ("keyword", kw) for each keyword,
                 then ("account", acc) for each account.
        """
        queries = []
        for kw in self.config.get("keywords", []):
            queries.append(("keyword", kw))
        for acc in self.config.get("accounts", []):
            queries.append(("account", acc))
        return queries

    def save(self, results: list[ScrapeResult]) -> tuple[Path, Path]:
        """Save results to JSON and Markdown."""
        return Storage.save(
            results=results,
            output_dir=self.output_dir,
            platform_name=self.platform_name,
            md_formatter=self.format_item_md,
        )

    def format_item_md(self, item: dict, index: int) -> str:
        """
        Format a single scraped item as Markdown.
        Override to customize per-platform Markdown output.
        """
        lines = [f"### {index}. {item.get('title', item.get('text', 'N/A')[:80])}\n"]

        for key, val in item.items():
            if key in ("title", "text"):
                continue
            if val:
                lines.append(f"**{key}**: {val}\n")

        if text := item.get("text"):
            lines.append(f"\n{text}\n")

        lines.append("\n---\n")

        return "\n".join(lines)
