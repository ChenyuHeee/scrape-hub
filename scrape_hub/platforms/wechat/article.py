"""Fetch full article content from WeChat article pages.

Search engines never index 100% of WeChat articles, and what they do index
is delayed. Once you have an article URL — from any source: a search engine,
RSS, a friend, another crawler — this module reads the full article directly:
title, account, author, publish time and body text.

Two page shapes are supported:

1. **Canonical article pages** — ``https://mp.weixin.qq.com/s?...`` (both the
   ``__biz/.../sn`` form and the ``src/timestamp/signature`` share form).
2. **Sogou link/reader pages** — ``weixin.sogou.com/link?url=...`` renders the
   full article inline (anti-leech reader). The same fields are extracted and
   a share URL from the page (or ``window.biz/mid/idx/sn``) is used as the
   canonical link.
"""

from __future__ import annotations

import re
import time
import urllib.parse
from typing import Any

WECHAT_DOMAIN = "mp.weixin.qq.com"


# ── link helpers ───────────────────────────────────────────

def is_wechat_article_url(url: str) -> bool:
    return WECHAT_DOMAIN in (url or "") and "/s" in (url or "")


def is_sogou_link_url(url: str) -> bool:
    return "weixin.sogou.com" in (url or "") and "/link" in (url or "")


def canonicalize(url: str) -> str:
    """Keep only the identifying params of an mp.weixin.qq.com article URL.

    Both URL families are valid:
    - ``__biz`` + ``mid`` + ``idx`` + ``sn``
    - ``src`` + ``timestamp`` + ``signature`` (+ ``ver``) — share links
    """
    if not url:
        return url
    parsed = urllib.parse.urlsplit(url)
    qs = urllib.parse.parse_qsl(parsed.query)
    keep = ("__biz", "mid", "idx", "sn", "src", "timestamp", "signature", "ver")
    qs = [(k, v) for k, v in qs if k in keep]
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(qs), "")
    )


def resolve_article_url(page: Any, url: str, timeout_ms: int = 20000) -> str:
    """Follow a link (incl. Sogou's) to its canonical article URL.

    Returns the canonical ``mp.weixin.qq.com/s?...`` URL when one can be
    determined; otherwise the original URL (which may still open a reader
    page with the full article).
    """
    if is_wechat_article_url(url):
        return canonicalize(url)

    original = url
    try:
        # Sogou bounces cold visits to /link pages back to the homepage.
        # Seed a session: first the homepage, then the matching search page
        # (reconstructed from the link's own query/type params), then the link.
        if is_sogou_link_url(url):
            try:
                page.goto("https://weixin.sogou.com/", wait_until="domcontentloaded", timeout=15000)
                time.sleep(1)
            except Exception:
                pass
            search_url = _sogou_search_url_for_link(url)
            if search_url:
                try:
                    page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
                    time.sleep(1.5)
                except Exception:
                    pass

        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        deadline = time.time() + 8
        while time.time() < deadline:
            current = page.url
            if is_wechat_article_url(current):
                return canonicalize(current)

            # Sogou link pages build the target URL with JS: `url += '...'`
            built = page.evaluate(
                "() => { try { return window.url || ''; } catch (e) { return ''; } }"
            )
            if built and is_wechat_article_url(built):
                return canonicalize(built)

            # Sogou reader page: a share link may already be present.
            found = _find_share_link(page)
            if found:
                return canonicalize(found)
            time.sleep(0.5)

        # Post-loop: accept a share link found on the final page.
        found = _find_share_link(page)
        if found:
            return canonicalize(found)
        return original
    except Exception:
        return original


def _sogou_search_url_for_link(link_url: str) -> str:
    """Reconstruct the Sogou search page a /link URL came from.

    Sogou /link URLs carry ``type`` and ``query`` params; visiting the same
    search page first makes the subsequent /link visit acceptable to Sogou's
    anti-leech check.
    """
    qs = urllib.parse.parse_qs(urllib.parse.urlsplit(link_url).query)
    query = (qs.get("query") or [""])[0]
    stype = (qs.get("type") or ["2"])[0]
    if not query:
        return ""
    params = {"type": stype, "query": query, "ie": "utf8", "s_from": "input"}
    return "https://weixin.sogou.com/weixin?" + urllib.parse.urlencode(params)


def _find_share_link(page: Any) -> str:
    """Find an mp.weixin.qq.com/s share link in the current page."""
    try:
        return page.evaluate(
            """
            () => {
                for (const a of document.querySelectorAll('a[href]')) {
                    const h = a.getAttribute('href') || '';
                    if (h.includes('mp.weixin.qq.com/s')) {
                        if (h.startsWith('//')) return 'https:' + h;
                        return h;
                    }
                }
                return '';
            }
            """
        )
    except Exception:
        return ""


def _biz_params(page: Any) -> dict[str, str]:
    """Read window.biz/mid/idx/sn from a Sogou reader page."""
    try:
        return page.evaluate(
            """
            () => {
                const g = (k) => typeof window[k] !== 'undefined' ? String(window[k]) : '';
                return { biz: g('biz'), mid: g('mid'), idx: g('idx'), sn: g('sn') };
            }
            """
        )
    except Exception:
        return {"biz": "", "mid": "", "idx": "", "sn": ""}


# ── article content ────────────────────────────────────────

_DELETED_MARKERS = (
    "该内容已被发布者删除",
    "此内容因违规无法查看",
    "此内容被投诉且经审核涉嫌侵权",
    "该公众号已迁移",
    "涉嫌违反相关法律法规和政策",
    "此内容因违规无法查看",
)


def fetch_article(
    page: Any,
    url: str,
    resolve: bool = True,
    include_content: bool = True,
    timeout_ms: int = 25000,
) -> dict:
    """Fetch one article's metadata and (optionally) full text.

    Returns a dict with at least ``url``; on failure ``error`` explains why.
    Works on both canonical mp.weixin.qq.com pages and Sogou reader pages.
    """
    item: dict[str, Any] = {"url": url}
    try:
        if resolve:
            resolved = resolve_article_url(page, url, timeout_ms=timeout_ms)
            if resolved != url and is_wechat_article_url(resolved):
                item["url"] = resolved
                url = resolved
            # If we ended on a reader page, stay there — content is below.

        if is_wechat_article_url(url):
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        time.sleep(1)

        body_text = page.evaluate("() => document.body ? document.body.innerText : ''")

        for marker in _DELETED_MARKERS:
            if marker in body_text:
                item["error"] = marker
                return item

        # Environment-check interstitial ("环境异常") — cannot bypass.
        if "环境异常" in body_text and "验证" in body_text:
            item["error"] = "页面要求环境验证（微信风控），请稍后重试或更换网络"
            return item

        meta = page.evaluate(
            """
            () => {
                const pick = (sels) => {
                    for (const s of sels) {
                        const el = document.querySelector(s);
                        if (el) return (el.innerText || el.textContent || '').trim();
                    }
                    return '';
                };
                const meta = (name) => {
                    const el = document.querySelector(
                        `meta[property="${name}"], meta[name="${name}"]`
                    );
                    return el ? (el.getAttribute('content') || '') : '';
                };
                return {
                    title: pick([
                        '#activity-name', 'h1.rich_media_title',
                        'h2.rich_media_title', '.rich_media_title',
                    ]) || meta('og:title'),
                    account: pick([
                        '#js_name', '.rich_media_meta_nickname a',
                        '.rich_media_meta_nickname',
                    ]),
                    author: pick(['#js_author', '#meta_content .rich_media_meta_text']),
                    publish_time: pick(['#publish_time', 'em#publish_time', '#meta_content em']),
                };
            }
            """
        )

        item["title"] = meta.get("title") or ""
        item["account"] = meta.get("account") or ""
        item["author"] = meta.get("author") or ""
        item["publish_time"] = _normalize_time(meta.get("publish_time") or "")
        if not item["publish_time"]:
            item["publish_time"] = _date_from_url(item["url"])

        biz = _extract_biz(item["url"])
        if not biz:
            p = _biz_params(page)
            biz = p.get("biz", "")
        if biz:
            item["biz"] = biz

        if include_content:
            content = page.evaluate(
                """
                () => {
                    const el = document.querySelector('#js_content')
                        || document.querySelector('.rich_media_content');
                    if (!el) return '';
                    return el.innerText || '';
                }
                """
            )
            item["content"] = content.strip()
            item["content_length"] = len(item["content"])
            if not item["content"] and not item.get("title"):
                item["error"] = "页面未包含文章正文（可能需要验证或内容已删除）"
                return item

        # Canonical link recovery (Sogou reader pages): the share link or
        # window.biz/mid/idx/sn may only be ready after the content renders.
        if not is_wechat_article_url(item["url"]):
            share = ""
            for _ in range(8):
                share = _find_share_link(page)
                if share:
                    break
                time.sleep(1)
            if share and is_wechat_article_url(share):
                item["url"] = canonicalize(share)
                if not item.get("biz"):
                    item["biz"] = _extract_biz(share)
            else:
                p = _biz_params(page)
                if p.get("biz") and p.get("sn"):
                    item["url"] = canonicalize(
                        "https://mp.weixin.qq.com/s?__biz={biz}&mid={mid}&idx={idx}&sn={sn}".format(**p)
                    )

        return item
    except Exception as e:
        item["error"] = f"抓取失败: {e}"
        return item


def _normalize_time(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"^(发布于|发布时间：?|创建时间：?)\s*", "", t).strip()
    return t


def _date_from_url(url: str) -> str:
    m = re.search(r"(\d{4})[-_](\d{2})[-_](\d{2})", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


def _extract_biz(url: str) -> str:
    qs = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    return (qs.get("__biz") or [""])[0]


# ── batch fetching ─────────────────────────────────────────

def fetch_many(
    page: Any,
    urls: list[str],
    resolve: bool = True,
    include_content: bool = True,
    pause: float = 1.5,
    max_articles: int | None = None,
) -> list[dict]:
    """Fetch a list of article URLs sequentially with a politeness delay."""
    results: list[dict] = []
    for i, url in enumerate(urls):
        if max_articles is not None and len(results) >= max_articles:
            break
        print(f"    [{i + 1}/{len(urls)}] {url[:80]}")
        results.append(
            fetch_article(page, url, resolve=resolve, include_content=include_content)
        )
        time.sleep(pause)
    return results
