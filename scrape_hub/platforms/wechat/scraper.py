"""WeChat public-account article scraper — multi-engine + full-content.

Why multiple engines?
    No public search engine fully indexes WeChat articles. Sogou's dedicated
    WeChat index is incomplete and updates slowly (plus frequent captchas).
    General engines (Bing / Baidu / 360) crawl mp.weixin.qq.com continuously,
    so a ``site:mp.weixin.qq.com`` query finds fresher articles Sogou misses.

Pipeline per query:
    1. Run each configured engine, merge results (dedup by URL).
    2. Optionally resolve redirect links to canonical mp.weixin.qq.com URLs.
    3. Optionally fetch full article content (title/account/time/body) —
       this also lets account queries verify the true publisher.
"""

from __future__ import annotations

import time
from typing import Any

from scrape_hub.core.base_scraper import BaseScraper, ScrapeResult
from scrape_hub.platforms.wechat import article as article_mod
from scrape_hub.platforms.wechat.backends import BACKENDS, DEFAULT_ENGINES
from scrape_hub.platforms.wechat.backends.base import WeChatBackend


class WeChatScraper(BaseScraper):
    """Multi-engine WeChat article scraper (see module docstring)."""

    @property
    def platform_name(self) -> str:
        return "wechat"

    @property
    def default_config(self) -> dict[str, Any]:
        return {
            "locale": "zh-CN",
            "keywords": [],
            "accounts": [],
            # Engine pipeline: order matters; each engine contributes results.
            "engines": DEFAULT_ENGINES,
            "metasearch_engines": ["bing", "baidu", "so360"],
            "max_pages": 3,                # sogou pagination
            "max_results_per_engine": 10,
            "page_pause": 2.5,
            "query_delay": 4.0,
            "resolve_links": True,         # redirect → canonical mp URL
            "fetch_content": False,        # fetch full article body
            "debug": False,
        }

    # ── browser setup ───────────────────────────────────────

    def on_browser_ready(self, page) -> None:
        print("✓ 浏览器就绪（多引擎微信搜索）\n")

    # ── core search ─────────────────────────────────────────

    def search(self, query_type: str, query_value: str, **kwargs) -> ScrapeResult:
        engines = kwargs.get("engines", self.config["engines"])
        limit = kwargs.get(
            "max_results_per_engine", self.config["max_results_per_engine"]
        )

        merged: list[dict] = []
        for engine_name in engines:
            backend = self._get_backend(engine_name)
            if backend is None:
                continue
            print(f"  ▸ 引擎 {engine_name}: {query_type}={query_value}")
            try:
                if query_type == "keyword":
                    items = backend.search_keyword(
                        self._page, query_value, limit=limit, **{**self.config, **kwargs}
                    )
                elif query_type == "account":
                    items = backend.search_account(
                        self._page, query_value, limit=limit, **{**self.config, **kwargs}
                    )
                else:
                    items = []
            except Exception as e:
                print(f"  ✗ 引擎 {engine_name} 失败: {e}")
                items = []

            for it in items:
                it.setdefault("engine", engine_name)
                it.setdefault("query_type", query_type)
                it.setdefault("query_value", query_value)
            merged.extend(items)

        merged = self._dedup_by_link_or_title(merged)

        # Resolve redirects → canonical mp.weixin.qq.com URLs (light mode:
        # server-side redirect following; full JS redirects resolved later).
        if kwargs.get("resolve_links", self.config["resolve_links"]):
            merged = self._resolve_links(merged, cap=len(merged))

        # Optionally fetch full content; for account queries this also lets
        # us keep only articles actually published by that account.
        if kwargs.get("fetch_content", self.config["fetch_content"]):
            merged = self._enrich_with_content(merged, query_type, query_value)

        print(f"  → 合计 {len(merged)} 篇（去重后）")
        return ScrapeResult(
            query_type=query_type,
            query_value=query_value,
            items=merged,
        )

    # ── helpers ─────────────────────────────────────────────

    def _get_backend(self, name: str) -> WeChatBackend | None:
        cls = BACKENDS.get(name)
        if cls is None:
            print(f"  ⚠ 未知引擎: {name}（可用: {', '.join(BACKENDS)}）")
            return None
        return cls()

    def _dedup_by_link_or_title(self, items: list[dict]) -> list[dict]:
        seen_links: set[str] = set()
        seen_titles: set[str] = set()
        out: list[dict] = []
        for it in items:
            link = (it.get("link") or "").strip()
            title = (it.get("title") or "").strip()
            if link and link in seen_links:
                continue
            if not link and title and title in seen_titles:
                continue
            if link:
                seen_links.add(link)
            if title:
                seen_titles.add(title)
            out.append(it)
        return out

    def _resolve_links(self, items: list[dict], cap: int) -> list[dict]:
        """Resolve redirect links to canonical article URLs where cheap."""
        from scrape_hub.platforms.wechat.backends.metasearch import MetaSearchBackend

        resolved = 0
        for it in items:
            if resolved >= cap:
                break
            link = it.get("link") or ""
            if not link or article_mod.is_wechat_article_url(link):
                continue
            final = MetaSearchBackend._resolve_redirect(self._page, link)
            if final and article_mod.is_wechat_article_url(final):
                it["link"] = final
                resolved += 1
        if resolved:
            print(f"  → 已解析 {resolved} 个跳转链接为原文链接")
        return items

    def _enrich_with_content(
        self, items: list[dict], query_type: str, query_value: str
    ) -> list[dict]:
        """Fetch full article content for each result.

        Slow but thorough: for account queries, only keep articles whose
        real publisher matches the account (verified on the article page).
        """
        pause = float(self.config.get("page_pause", 2.0))
        enriched: list[dict] = []
        for i, it in enumerate(items):
            print(f"  ▸ 抓取正文 [{i + 1}/{len(items)}]: {it.get('title', '')[:50]}")
            full = article_mod.fetch_article(
                self._page, it.get("link", ""), resolve=True, include_content=True
            )
            merged_it = {**it, **{k: v for k, v in full.items() if v}}
            # Prefer the canonical URL resolved while fetching.
            if merged_it.get("url") and merged_it["url"] != merged_it.get("link"):
                merged_it["link"] = merged_it["url"]
            if merged_it.get("error") and not merged_it.get("content"):
                print(f"    ⚠ {merged_it['error']}")
                continue

            # Account verification
            if query_type == "account":
                account = (merged_it.get("account") or "").strip()
                if account and query_value not in account and account not in query_value:
                    print(f"    ↷ 跳过（真实来源 {account} ≠ {query_value}）")
                    continue

            enriched.append(merged_it)
            time.sleep(pause)

        return enriched

    # ── markdown formatting ─────────────────────────────────

    def format_item_md(self, item: dict, index: int) -> str:
        lines = [f"### {index}. {item.get('title', 'N/A')}\n"]

        meta = []
        if item.get("account"):
            meta.append(f"**来源**: {item['account']}")
        if item.get("author"):
            meta.append(f"**作者**: {item['author']}")
        if item.get("publish_time") or item.get("time_text"):
            meta.append(f"**时间**: {item.get('publish_time') or item.get('time_text')}")
        if item.get("engine"):
            meta.append(f"**引擎**: {item['engine']}")
        if meta:
            lines.append("  |  ".join(meta) + "\n")

        if item.get("summary"):
            lines.append(f"\n> {item['summary']}\n")
        if item.get("content"):
            lines.append("\n" + item["content"] + "\n")
        if item.get("link"):
            lines.append(f"\n[阅读原文]({item['link']})\n")

        lines.append("\n---\n")
        return "\n".join(lines)
