"""Meta-search backend for WeChat articles.

Sogou's WeChat index is incomplete and updates slowly. General-purpose
search engines (Bing, Baidu, 360) crawl ``mp.weixin.qq.com`` continuously,
so ``site:mp.weixin.qq.com <keyword>`` queries surface articles that Sogou
misses or has not indexed yet.

Strategy per engine:
- **Bing**  — official RSS output (``format=rss``): machine-readable XML
             with the real article URL, no HTML parsing needed.
- **Baidu** — HTML parsing: result links are ``baidu.com/link?url=...``
             redirects, the real URL lives in the ``mu`` attribute and is
             resolved server-side via Playwright's API request context.
- **360**   — HTML parsing: direct links to ``mp.weixin.qq.com``.
"""

from __future__ import annotations

import time
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any

from scrape_hub.platforms.wechat.backends.base import WeChatBackend

WECHAT_DOMAIN = "mp.weixin.qq.com"


class MetaSearchBackend(WeChatBackend):
    name = "metasearch"

    #: sub-engines to query, in order; override via config ``metasearch_engines``
    SUB_ENGINES = ("bing", "baidu", "so360")

    BING_RSS_URL = "https://www.bing.com/search?q={query}&format=rss&count=30&setlang=zh-CN"
    BAIDU_URL = "https://www.baidu.com/s?wd={query}&rn=30"
    SO360_URL = "https://www.so.com/s?q={query}"

    # ── public interface ────────────────────────────────────

    def search_keyword(
        self, page: Any, keyword: str, limit: int = 10, **kwargs
    ) -> list[dict]:
        sub_engines = kwargs.get(
            "metasearch_engines", self.SUB_ENGINES
        )
        page_pause = float(kwargs.get("page_pause", 2.5))
        per_engine = max(limit, 10)

        merged: list[dict] = []
        for engine in sub_engines:
            try:
                items = self._run_sub_engine(
                    page, engine, self._site_query(keyword), per_engine, page_pause
                )
            except Exception as e:
                print(f"    [metasearch:{engine}] 失败: {e}")
                continue
            if items:
                print(f"    [metasearch:{engine}] 找到 {len(items)} 篇")
            else:
                print(f"    [metasearch:{engine}] 0 篇")
            merged.extend(items)

        merged = self._dedup(merged, key="link")
        return merged[:limit]

    def search_account(
        self, page: Any, account: str, limit: int = 10, **kwargs
    ) -> list[dict]:
        """Account search ≈ keyword search for the account name.

        General engines cannot filter by publisher, so we query the account
        name and let the orchestrator optionally verify the real publisher
        by fetching article content (``fetch_content``).
        """
        return self.search_keyword(page, account, limit=limit, **kwargs)

    # ── sub-engine runners ──────────────────────────────────

    @staticmethod
    def _site_query(keyword: str) -> str:
        return f"site:{WECHAT_DOMAIN} {keyword}".strip()

    def _run_sub_engine(
        self, page: Any, engine: str, query: str, limit: int, page_pause: float
    ) -> list[dict]:
        if engine == "bing":
            return self._search_bing_rss(page, query, limit)
        if engine == "baidu":
            return self._search_baidu(page, query, limit, page_pause)
        if engine == "so360":
            return self._search_so360(page, query, limit, page_pause)
        print(f"    [metasearch] 未知子引擎: {engine}（可用: bing, baidu, so360）")
        return []

    def _search_bing_rss(self, page: Any, query: str, limit: int) -> list[dict]:
        # Try site: first; some regions (e.g. cn.bing.com) silently ignore
        # the site: operator, so fall back to the domain-as-keyword trick and
        # rely on the URL filter in _finalize.
        kw = query.split(":", 1)[-1].strip()
        attempts = [
            self.BING_RSS_URL.format(
                query=urllib.parse.quote(f"site:{WECHAT_DOMAIN} {kw}")
            ),
            self.BING_RSS_URL.format(
                query=urllib.parse.quote(f"{WECHAT_DOMAIN}/s {kw}")
            ),
        ]
        for url in attempts:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                time.sleep(1)
                root = ET.fromstring(page.content())
            except Exception as e:
                print(f"    [metasearch:bing] 解析失败: {e}")
                continue

            items: list[dict] = []
            for node in root.iter("item"):
                title = (node.findtext("title") or "").strip()
                link = (node.findtext("link") or "").strip()
                if WECHAT_DOMAIN not in link or "/s" not in link:
                    continue
                summary = (node.findtext("description") or "").strip()
                if summary:
                    summary = _strip_html(summary)
                time_text = (node.findtext("pubDate") or "").strip()
                items.append(
                    {
                        "title": title,
                        "link": link,
                        "summary": summary[:500],
                        "account": "",
                        "time_text": time_text,
                        "engine": f"{self.name}:bing",
                    }
                )
                if len(items) >= limit:
                    break
            if items:
                return items
        return []

    @staticmethod
    def _is_captcha(page: Any) -> bool:
        try:
            return page.evaluate(
                """
                () => {
                    const u = window.location.href;
                    const b = document.body ? document.body.innerText : '';
                    return u.includes('wappass.baidu.com') ||
                           u.includes('captcha') ||
                           b.includes('安全验证') ||
                           b.includes('请输入验证码');
                }
                """
            )
        except Exception:
            return False

    def _search_baidu(
        self, page: Any, query: str, limit: int, page_pause: float
    ) -> list[dict]:
        url = self.BAIDU_URL.format(query=urllib.parse.quote(query))
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        time.sleep(page_pause)

        if self._is_captcha(page):
            print("    [metasearch:baidu] 触发百度安全验证，跳过（换网络/IP 可恢复）")
            return []

        raw = page.evaluate(
            """
            () => {
                const results = [];
                const seen = new Set();
                const anchors = document.querySelectorAll(
                    'h3 a, div.result a, div.c-container a'
                );
                for (const a of anchors) {
                    const href = a.getAttribute('href') || '';
                    // Real URL is often stored in the "mu" attribute on Baidu.
                    const mu = a.getAttribute('mu') || '';
                    const hit = href.includes('mp.weixin.qq.com')
                        || mu.includes('mp.weixin.qq.com');
                    if (!hit) continue;

                    const title = (a.innerText || '').trim();
                    if (!title || title.length < 4 || seen.has(title)) continue;
                    seen.add(title);

                    let container = a.closest('div.result')
                        || a.closest('div.c-container') || a.parentElement;
                    let summary = '';
                    if (container) {
                        const abs = container.querySelector(
                            '[class*="abstract"], [class*="content-right"], '
                            + '.c-abstract, .c-span-last'
                        );
                        if (abs) summary = (abs.innerText || '').trim();
                    }
                    let timeText = '';
                    if (container) {
                        const t = container.querySelector(
                            '[class*="color-gray"], [class*="time"], .c-color-gray2'
                        );
                        if (t) timeText = (t.innerText || '').trim();
                    }
                    results.push({
                        title, link: mu || href, summary,
                        account: '', time_text: timeText,
                    });
                }
                return results;
            }
            """
        )

        return self._finalize(raw, page, limit, "baidu")

    def _search_so360(
        self, page: Any, query: str, limit: int, page_pause: float
    ) -> list[dict]:
        url = self.SO360_URL.format(query=urllib.parse.quote(query))
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        time.sleep(page_pause)

        if self._is_captcha(page):
            print("    [metasearch:so360] 触发安全验证，跳过（换网络/IP 可恢复）")
            return []

        raw = page.evaluate(
            """
            () => {
                const results = [];
                const seen = new Set();
                for (const a of document.querySelectorAll(
                    'h3 a, li.res-list h3 a, li.res-list a'
                )) {
                    let href = a.getAttribute('href') || '';
                    // so.com sometimes stores the real URL in data-mdurl.
                    const md = a.getAttribute('data-mdurl') || '';
                    if (md.includes('mp.weixin.qq.com')) href = md;
                    if (!href.includes('mp.weixin.qq.com')) continue;
                    const title = (a.innerText || '').trim();
                    if (!title || title.length < 4 || seen.has(title)) continue;
                    seen.add(title);
                    let container = a.closest('li') || a.parentElement;
                    let summary = '';
                    if (container) {
                        const p = container.querySelector(
                            'p.res-desc, p[class*="desc"], .res-desc'
                        );
                        if (p) summary = (p.innerText || '').trim();
                    }
                    let timeText = '';
                    if (container) {
                        const t = container.querySelector(
                            'p.res-linkinfo, span[class*="info"], '
                            + 'cite, .res-linkinfo'
                        );
                        if (t) timeText = (t.innerText || '').trim();
                    }
                    results.push({
                        title, link: href, summary,
                        account: '', time_text: timeText,
                    });
                }
                return results;
            }
            """
        )

        return self._finalize(raw, page, limit, "so360")

    # ── shared post-processing ──────────────────────────────

    def _finalize(
        self, raw: list[dict], page: Any, limit: int, sub_name: str
    ) -> list[dict]:
        """Resolve redirect links server-side and normalize items."""
        from scrape_hub.platforms.wechat.article import canonicalize

        items: list[dict] = []
        for it in raw:
            link = it.get("link") or ""
            if WECHAT_DOMAIN not in link:
                resolved = self._resolve_redirect(page, link)
                if resolved and WECHAT_DOMAIN in resolved:
                    link = resolved
                elif not resolved:
                    continue
            # Drop non-canonical query params (timestamps, shares) for dedup.
            link = canonicalize(link)
            if not link or WECHAT_DOMAIN not in link:
                continue
            # Only keep article pages, not platform/home pages.
            if "/s" not in link:
                continue
            it["link"] = link
            it["engine"] = f"{self.name}:{sub_name}"
            items.append(it)
            if len(items) >= limit:
                break
        return items

    @staticmethod
    def _resolve_redirect(page: Any, url: str) -> str:
        """Follow redirects without loading pages in the browser.

        Playwright's API request context follows redirects server-side, so
        ``baidu.com/link?url=...`` resolves to the real article URL for free.
        """
        if not url:
            return ""
        try:
            resp = page.context.request.get(url, max_redirects=5, timeout=15000)
            return str(resp.url)
        except Exception:
            return ""


def _strip_html(text: str) -> str:
    import re

    return re.sub(r"<[^>]+>", " ", text).replace("&nbsp;", " ").strip()
