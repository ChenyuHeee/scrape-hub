"""X (Twitter) scraper — search tweets by account and keyword."""

from __future__ import annotations

import time
import urllib.parse
from typing import Any

from playwright.sync_api import TimeoutError as PwTimeout

from scrape_hub.core.base_scraper import BaseScraper, ScrapeResult


class XTwitterScraper(BaseScraper):
    """
    Scraper for X (formerly Twitter).

    Searches by account mentions and keywords, extracts tweets via scrolling.
    Requires manual login on first run (session saved to persistent browser data).
    """

    @property
    def platform_name(self) -> str:
        return "x_twitter"

    @property
    def default_config(self) -> dict[str, Any]:
        return {
            "locale": "en-US",
            "keywords": [],
            "accounts": [],
            "max_scroll": 15,
            "scroll_pause": 2.5,
            "query_delay": 5.0,
        }

    # ── browser setup ───────────────────────────────────────

    def on_browser_ready(self, page) -> None:
        """
        Navigate to X home and verify login state.

        Supports cookie injection for headless/CI environments.
        With persistent browser data, login is typically already saved.
        If not logged in, waits up to 3 minutes for manual login.
        """
        # Inject cookies if provided (for GitHub Actions / headless mode)
        cookies = self.config.get("cookies")
        if cookies:
            import json as _json
            if isinstance(cookies, str):
                cookies = _json.loads(cookies)
            # Playwright expects cookies with url or domain+path
            for c in cookies:
                if "sameSite" in c:
                    val = c["sameSite"]
                    if val not in ("Strict", "Lax", "None"):
                        c["sameSite"] = "Lax"
                if "url" not in c and "domain" not in c:
                    c["url"] = "https://x.com"
                # Remove fields Playwright doesn't accept
                for key in ["hostOnly", "session", "storeId", "id"]:
                    c.pop(key, None)
            page.context.add_cookies(cookies)
            print(f"✓ 已注入 {len(cookies)} 个 cookies")

        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        # Auto-detect login state
        for attempt in range(90):  # max ~3 minutes
            logged_in = page.evaluate("""
                () => {
                    const url = window.location.href;
                    if (url.includes('/login') || url.includes('/i/flow/login')) return false;
                    const nav = document.querySelector('nav[role="navigation"]');
                    const sidebar = document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
                    return !!(nav || sidebar);
                }
            """)
            if logged_in:
                print("✓ 已检测到 X 登录状态")
                return
            if attempt == 0:
                print("⏳ 等待 X 登录（如使用持久化会话，将自动跳过）...")
            time.sleep(2)

        raise RuntimeError(
            "X 登录超时。请先运行一次非无头模式 (headless=False) 完成登录，"
            "登录态会保存到 .browser_data/ 供后续使用。"
        )

    # ── query building ──────────────────────────────────────

    def build_queries(self) -> list[tuple[str, str]]:
        queries = []
        accounts = self.config.get("accounts", [])
        keywords = self.config.get("keywords", [])

        # Account-based searches: "(from:user) keyword1 OR keyword2"
        for acc in accounts:
            if keywords:
                kw_part = " OR ".join(keywords[:5])
                query = f"(from:{acc}) {kw_part}"
            else:
                query = f"from:{acc}"
            queries.append(("account", query))

        # Keyword searches
        for kw in keywords:
            queries.append(("keyword", kw))

        return queries

    # ── core search ─────────────────────────────────────────

    def search(self, query_type: str, query_value: str, **kwargs) -> ScrapeResult:
        page = self._page
        encoded = urllib.parse.quote(query_value, safe="")
        url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"

        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(3)

        max_scroll = kwargs.get("max_scroll", self.config["max_scroll"])
        scroll_pause = kwargs.get("scroll_pause", self.config["scroll_pause"])

        tweets = self._extract_tweets(page, max_scroll, scroll_pause)

        return ScrapeResult(
            query_type=query_type,
            query_value=query_value,
            items=tweets,
        )

    def _extract_tweets(
        self, page, max_scroll: int = 20, scroll_pause: float = 2.0
    ) -> list[dict]:
        """Scroll and extract tweets from the current search results page."""
        tweets: list[dict] = []
        seen_texts: set[str] = set()

        for scroll_i in range(max_scroll):
            try:
                page.wait_for_selector(
                    'article[data-testid="tweet"]', timeout=8000
                )
            except PwTimeout:
                print(f"    [scroll {scroll_i}] 未找到推文，停止滚动")
                break

            articles = page.query_selector_all('article[data-testid="tweet"]')
            new_count = 0

            for article in articles:
                try:
                    tweet = self._parse_tweet(article)
                    if tweet and tweet["text"] not in seen_texts:
                        seen_texts.add(tweet["text"])
                        tweets.append(tweet)
                        new_count += 1
                except Exception:
                    continue

            print(
                f"    [scroll {scroll_i + 1}/{max_scroll}] "
                f"新增 {new_count} 条，累计 {len(tweets)} 条"
            )

            if new_count == 0 and scroll_i > 2:
                print("    连续无新内容，停止滚动")
                break

            page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
            time.sleep(scroll_pause)

        return tweets

    @staticmethod
    def _parse_tweet(article) -> dict | None:
        """Parse a single tweet article element."""
        text_el = article.query_selector('[data-testid="tweetText"]')
        if not text_el:
            return None
        text = text_el.inner_text().strip()
        if not text or len(text) < 10:
            return None

        user_el = article.query_selector('[data-testid="User-Name"]')
        username = user_el.inner_text().strip() if user_el else "unknown"

        time_el = article.query_selector("time")
        timestamp = time_el.get_attribute("datetime") if time_el else ""

        link = ""
        if time_el:
            parent_a = time_el.evaluate("el => el.closest('a')?.href || ''")
            if parent_a:
                link = parent_a

        metrics = {}
        for metric_name, test_id in [
            ("replies", "reply"),
            ("retweets", "retweet"),
            ("likes", "like"),
        ]:
            el = article.query_selector(f'[data-testid="{test_id}"]')
            if el:
                val = el.get_attribute("aria-label") or el.inner_text()
                metrics[metric_name] = val.strip()

        return {
            "username": username,
            "text": text,
            "timestamp": timestamp,
            "link": link,
            "metrics": metrics,
        }

    # ── markdown formatting ─────────────────────────────────

    def format_item_md(self, item: dict, index: int) -> str:
        lines = [f"### {index}. {item.get('username', 'unknown')}\n"]
        if item.get("timestamp"):
            lines.append(f"**时间**: {item['timestamp']}\n")
        lines.append(f"\n{item['text']}\n")
        if item.get("link"):
            lines.append(f"\n[原文链接]({item['link']})\n")
        if item.get("metrics"):
            m = " | ".join(f"{k}: {v}" for k, v in item["metrics"].items())
            lines.append(f"\n*{m}*\n")
        lines.append("\n---\n")
        return "\n".join(lines)
