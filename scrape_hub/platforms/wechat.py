"""WeChat articles scraper via Sogou WeChat search engine."""

from __future__ import annotations

import re
import time
import urllib.parse
from typing import Any

from scrape_hub.core.base_scraper import BaseScraper, ScrapeResult

SOGOU_WEIXIN_URL = "https://weixin.sogou.com"


class WeChatScraper(BaseScraper):
    """
    Scraper for WeChat public account articles.

    Uses Sogou WeChat search (weixin.sogou.com) as the entry point.
    Supports keyword search (paginated) and account search.
    Handles Sogou captcha by pausing for manual input.
    """

    @property
    def platform_name(self) -> str:
        return "wechat"

    @property
    def default_config(self) -> dict[str, Any]:
        return {
            "locale": "zh-CN",
            "keywords": [],
            "accounts": [],
            "account_filter_keywords": "",
            "max_pages": 3,
            "page_pause": 3.0,
            "query_delay": 5.0,
            "debug": False,
        }

    # ── browser setup ───────────────────────────────────────

    def on_browser_ready(self, page) -> None:
        """Open Sogou WeChat homepage, handle any initial captcha."""
        print("正在打开搜狗微信搜索...")
        try:
            page.goto(SOGOU_WEIXIN_URL, wait_until="domcontentloaded", timeout=20000)
            time.sleep(2)
        except Exception as e:
            print(f"无法访问搜狗微信: {e}")
            raise

        self._handle_captcha(page)
        print("✓ 搜狗微信搜索已就绪\n")

    # ── query building ──────────────────────────────────────

    def build_queries(self) -> list[tuple[str, str]]:
        queries = []
        for kw in self.config.get("keywords", []):
            queries.append(("keyword", kw))
        for acc in self.config.get("accounts", []):
            queries.append(("account", acc))
        return queries

    # ── core search ─────────────────────────────────────────

    def search(self, query_type: str, query_value: str, **kwargs) -> ScrapeResult:
        if query_type == "keyword":
            items = self._search_by_keyword(query_value, **kwargs)
        elif query_type == "account":
            items = self._search_by_account(query_value, **kwargs)
        else:
            items = []

        return ScrapeResult(
            query_type=query_type,
            query_value=query_value,
            items=items,
        )

    # ── keyword search ──────────────────────────────────────

    def _search_by_keyword(self, keyword: str, **kwargs) -> list[dict]:
        page = self._page
        max_pages = kwargs.get("max_pages", self.config["max_pages"])
        page_pause = kwargs.get("page_pause", self.config["page_pause"])
        debug = kwargs.get("debug", self.config["debug"])

        all_articles: list[dict] = []
        seen_titles: set[str] = set()

        for page_num in range(1, max_pages + 1):
            url = self._build_article_search_url(keyword, page_num)
            print(f"    第 {page_num}/{max_pages} 页: {keyword}")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
            except Exception as e:
                print(f"    页面加载失败: {e}")
                break

            time.sleep(page_pause)

            if not self._handle_captcha(page):
                break

            articles = self._extract_articles(page, debug=debug)
            new_count = 0
            for art in articles:
                if art["title"] not in seen_titles:
                    seen_titles.add(art["title"])
                    art["search_keyword"] = keyword
                    all_articles.append(art)
                    new_count += 1

            print(f"    → 新增 {new_count} 篇，累计 {len(all_articles)} 篇")

            if new_count == 0:
                break

            time.sleep(page_pause + page_num * 0.5)

        return all_articles

    # ── account search ──────────────────────────────────────

    def _search_by_account(self, account_name: str, **kwargs) -> list[dict]:
        page = self._page
        page_pause = kwargs.get("page_pause", self.config["page_pause"])
        articles: list[dict] = []

        # Step 1: search for the account
        url = self._build_account_search_url(account_name)
        print(f"    搜索公众号: {account_name}")

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            print(f"    页面加载失败: {e}")
            return articles

        time.sleep(page_pause)

        if not self._handle_captcha(page):
            return articles

        # Step 2: find and visit the account page
        account_info = page.evaluate("""
            (targetName) => {
                const allLinks = document.querySelectorAll('a');
                let bestLink = null, bestScore = 0;
                for (const a of allLinks) {
                    const text = (a.innerText || '').trim();
                    const href = a.getAttribute('href') || '';
                    if (text === targetName) return { href, text };
                    if (text.includes(targetName) || targetName.includes(text)) {
                        if (text.length > bestScore && href) {
                            bestScore = text.length;
                            bestLink = { href, text };
                        }
                    }
                }
                return bestLink;
            }
        """, account_name)

        if account_info:
            href = account_info.get("href", "")
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = SOGOU_WEIXIN_URL + href

            if href:
                try:
                    page.goto(href, wait_until="domcontentloaded", timeout=20000)
                    time.sleep(page_pause)

                    if self._handle_captcha(page):
                        page_articles = page.evaluate("""
                            (accountName) => {
                                const results = [], seen = new Set();
                                for (const a of document.querySelectorAll('a')) {
                                    const t = (a.innerText || '').trim();
                                    const h = a.getAttribute('href') || '';
                                    if (t.length > 6 && !seen.has(t) && h) {
                                        seen.add(t);
                                        results.push({
                                            title: t.slice(0, 200), link: h,
                                            account: accountName, summary: '', time_text: '',
                                        });
                                    }
                                }
                                return results;
                            }
                        """, account_name)
                        for art in page_articles:
                            art["search_keyword"] = f"公众号:{account_name}"
                            articles.append(art)
                except Exception as e:
                    print(f"    访问公众号页面失败: {e}")
        else:
            print(f"    未找到公众号: {account_name}")

        # Step 3: fallback keyword search for this account
        filter_kw = self.config.get("account_filter_keywords", "")
        fallback_kw = f"{account_name} ({filter_kw})" if filter_kw else account_name
        fallback_url = self._build_article_search_url(fallback_kw, 1)
        print(f"    补充搜索: {account_name} 相关文章")

        try:
            page.goto(fallback_url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(page_pause)
            if self._handle_captcha(page):
                extra = self._extract_articles(page)
                seen = {a["title"] for a in articles}
                for art in extra:
                    if art["title"] not in seen:
                        art["search_keyword"] = f"公众号:{account_name}"
                        articles.append(art)
        except Exception:
            pass

        print(f"    → 共提取 {len(articles)} 篇")
        return articles

    # ── helpers ──────────────────────────────────────────────

    @staticmethod
    def _build_article_search_url(keyword: str, page_num: int = 1) -> str:
        params = {
            "type": "2",
            "query": keyword,
            "ie": "utf8",
            "s_from": "input",
            "_sug_": "n",
            "_sug_type_": "",
            "page": str(page_num),
        }
        return f"{SOGOU_WEIXIN_URL}/weixin?{urllib.parse.urlencode(params)}"

    @staticmethod
    def _build_account_search_url(account_name: str) -> str:
        params = {
            "type": "1",
            "query": account_name,
            "ie": "utf8",
            "s_from": "input",
        }
        return f"{SOGOU_WEIXIN_URL}/weixin?{urllib.parse.urlencode(params)}"

    @staticmethod
    def _handle_captcha(page, max_wait: int = 120) -> bool:
        """Detect and wait for user to solve Sogou captcha."""
        try:
            is_captcha = page.evaluate("""
                () => {
                    const url = window.location.href;
                    const body = document.body?.innerText || '';
                    return url.includes('antispider') ||
                           body.includes('请输入验证码') ||
                           body.includes('输入下图中的字符') ||
                           !!document.querySelector('#seccodeInput') ||
                           !!document.querySelector('.input-hint');
                }
            """)
            if is_captcha:
                print("\n    ⚠️  检测到验证码！请在浏览器中手动输入验证码...")
                deadline = time.time() + max_wait
                while time.time() < deadline:
                    time.sleep(2)
                    still_captcha = page.evaluate("""
                        () => window.location.href.includes('antispider')
                    """)
                    if not still_captcha:
                        print("    ✓ 验证码已通过\n")
                        return True
                print("    ✗ 验证码等待超时")
                return False
        except Exception:
            pass
        return True

    def _extract_articles(self, page, debug: bool = False) -> list[dict]:
        """Extract articles from a Sogou WeChat search result page."""
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        time.sleep(1)

        if not self._handle_captcha(page):
            return []

        if debug:
            from datetime import datetime
            from pathlib import Path

            debug_dir = Path(str(self.output_dir)) / "_debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%H%M%S")
            html = page.content()
            (debug_dir / f"page_{ts}.html").write_text(html, encoding="utf-8")

        articles = page.evaluate(r"""
            () => {
                const results = [];
                const BASE = 'https://weixin.sogou.com';
                const allLinks = document.querySelectorAll('a[href*="/link?"]');
                const seen = new Set();

                for (const a of allLinks) {
                    const title = (a.innerText || '').trim();
                    if (!title || title.length < 6) continue;
                    if (seen.has(title)) continue;
                    seen.add(title);

                    let href = a.getAttribute('href') || '';
                    if (href.startsWith('//')) href = 'https:' + href;
                    else if (href.startsWith('/')) href = BASE + href;

                    let summary = '', account = '', timeText = '';
                    let container = a.closest('li') || a.closest('div') || a.parentElement;
                    if (container) {
                        for (const p of container.querySelectorAll('p')) {
                            const t = (p.innerText || '').trim();
                            if (t.length > 20 && t !== title) { summary = t.slice(0, 500); break; }
                        }
                        for (const el of container.querySelectorAll('a, span')) {
                            const t = (el.innerText || '').trim();
                            if (el.tagName === 'A' && t.length > 1 && t.length < 30
                                && t !== title && !t.includes('http')) {
                                if (!account) account = t;
                            }
                            if (/\d/.test(t) && /[-年月日前天小时]/.test(t) && t.length < 30) {
                                timeText = t;
                            }
                        }
                    }
                    results.push({ title, link: href, summary, account, time_text: timeText });
                }

                if (results.length === 0) {
                    for (const a of document.querySelectorAll('h3 a, h4 a')) {
                        const title = (a.innerText || '').trim();
                        if (!title || title.length < 6 || seen.has(title)) continue;
                        seen.add(title);
                        let href = a.getAttribute('href') || '';
                        if (href.startsWith('//')) href = 'https:' + href;
                        else if (href.startsWith('/')) href = BASE + href;
                        results.push({ title, link: href, summary: '', account: '', time_text: '' });
                    }
                }
                return results;
            }
        """)

        # Filter out navigation elements
        valid = []
        for art in articles:
            title = art.get("title", "")
            if re.match(r"^[\d\s]+$", title):
                continue
            if title in ("下一页", "上一页", "搜索帮助", "意见反馈及投诉"):
                continue
            valid.append(art)

        return valid

    # ── markdown formatting ─────────────────────────────────

    def format_item_md(self, item: dict, index: int) -> str:
        lines = [f"### {index}. {item.get('title', 'N/A')}\n"]

        if item.get("account"):
            lines.append(f"**来源**: {item['account']}")
            if item.get("time_text"):
                lines.append(f"  |  **时间**: {item['time_text']}")
            lines.append("\n")

        if item.get("summary"):
            lines.append(f"\n> {item['summary']}\n")

        if item.get("link"):
            lines.append(f"\n[阅读原文]({item['link']})\n")

        lines.append("\n---\n")
        return "\n".join(lines)
