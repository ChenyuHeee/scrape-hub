"""WeChat Reading (微信读书) backend — monitor a 公众号's latest articles.

Why WeChat Reading?
    No public search engine reliably indexes every WeChat article (Sogou's
    index is incomplete and lags; the demo article in this repo's tests was
    invisible to Sogou months after publishing). WeChat Reading, however,
    officially syncs public-account articles and exposes them through its
    web API — each 公众号 is a "book" whose ``bookId`` is ``MP_WXS_<digits>``.

Key trick (credit: https://github.com/Pengyf04/weread-mp-fetcher):
    ``bookId = "MP_WXS_" + base64decode(article.__biz)``
    ``__biz`` is public data present in ANY article URL/page of the account,
    so no search and no URL guessing is needed: give this module one article
    link of the account and it can list that account's latest articles.

Requires:
    - A WeChat Reading login (scan QR once with WeChat; session persists in
      the Playwright profile at .browser_data/weread).

Endpoints (same-origin fetch, credentials included):
    POST /mp/shelf/addToShelf           body {"bookIds": [...]}   — subscribe
    GET  /web/shelf/sync?...album=1     — subscribed accounts (+readerUrl)
    GET  /web/mp/articles?bookId=...    — article list; MUST run inside the
                                          reader page context
                                          (/web/mp/reader/<hash>), else -2041.
"""

from __future__ import annotations

import base64
import json
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any

WEREAD_HOME = "https://weread.qq.com/"
SHELF_URL = "/web/shelf/sync?synckey=0&teenmode=0&album=1"
ARTICLES_URL = "/web/mp/articles?bookId={book_id}&offset={offset}"


# ── bookId derivation ──────────────────────────────────────

def biz_to_book_id(biz: str) -> str | None:
    """Convert a WeChat account __biz (base64) to a WeChat Reading bookId."""
    biz = (biz or "").strip()
    if not biz:
        return None
    try:
        decoded = base64.b64decode(biz).decode("utf-8")
    except Exception:
        return None
    if not re.fullmatch(r"\d+", decoded):
        return None
    return f"MP_WXS_{decoded}"


def biz_from_text(text: str) -> str | None:
    """Extract __biz from an article URL or HTML page source."""
    m = (
        re.search(r"var\s+biz\s*=\s*[\"']([A-Za-z0-9+/=]+)[\"']", text)
        or re.search(r"__biz=([A-Za-z0-9+/=%]+)", text)
    )
    if not m:
        return None
    return urllib.parse.unquote(m.group(1))


def book_id_from_input(page: Any, raw: str) -> tuple[str, str]:
    """Resolve a user input (article URL / biz / bookId) to (bookId, label).

    For short article links without __biz in the query, the article page is
    fetched once to read ``var biz = '...'`` from the HTML.
    """
    s = (raw or "").strip()
    if re.fullmatch(r"MP_WXS_\d+", s):
        return s, "bookId"

    biz = biz_from_text(s)
    if biz:
        book_id = biz_to_book_id(biz)
        if book_id:
            return book_id, "biz"

    if s.startswith("http"):
        try:
            page.goto(s, wait_until="domcontentloaded", timeout=25000)
            time.sleep(1)
            html = page.content()
            biz = biz_from_text(html)
            if biz:
                book_id = biz_to_book_id(biz)
                if book_id:
                    return book_id, "article-url"
        except Exception:
            pass
        raise ValueError(f"无法从文章页提取 __biz: {s}（可能已删除或需要验证）")

    raise ValueError(f"无法识别输入: {s}（请给文章链接 / __biz / MP_WXS_ 开头的 bookId）")


# ── login ──────────────────────────────────────────────────

def _cookies(page: Any) -> dict[str, str]:
    try:
        pairs = page.evaluate("() => document.cookie").split(";")
    except Exception:
        return {}
    out = {}
    for p in pairs:
        if "=" in p:
            k, v = p.strip().split("=", 1)
            out[k] = v
    return out


def is_logged_in(page: Any) -> bool:
    """Login state = presence of the WeChat Reading auth cookie."""
    return "wr_vid" in _cookies(page)


def login(page: Any, wait_seconds: int = 180, qr_png: str | None = None) -> bool:
    """Open the QR login modal and wait for the user to scan.

    Headless: saves a QR screenshot to ``qr_png`` so the user can scan it
    from another device. Headed: the user scans in the opened window.
    Returns True once ``wr_vid`` appears.
    """
    if is_logged_in(page):
        print("✓ 已登录微信读书")
        return True

    print("正在打开微信读书登录页...")
    page.goto(WEREAD_HOME, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)

    try:
        page.click("text=登录", timeout=5000)
    except Exception:
        # Modal may open via a different selector; try generic click.
        try:
            page.evaluate(
                "() => { const el = [...document.querySelectorAll('a,span,div')]"
                ".find(e => (e.innerText||'').trim() === '登录'); if (el) el.click(); }"
            )
        except Exception:
            pass
    time.sleep(4)

    # Wait for the WeChat QR iframe / image to render before screenshotting.
    for _ in range(6):
        qr_ready = page.evaluate(
            "() => !!(document.querySelector('iframe[src*=\"qrconnect\"]')"
            " || document.querySelector('img[src*=\"qr\"]'))"
        )
        if qr_ready:
            break
        time.sleep(2)
    else:
        print("⚠ 未检测到登录二维码元素，页面可能已改版；截图仍会保存供人工确认。")

    if qr_png:
        try:
            Path(qr_png).parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=qr_png, full_page=True)
            print(f"📱 请用微信扫描二维码（截图已保存）: {qr_png}")
        except Exception as e:
            print(f"截图失败: {e}")

    print(f"⏳ 等待扫码登录（最长 {wait_seconds}s，请在浏览器窗口/截图中完成）...")
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if is_logged_in(page):
            print("✓ 微信读书登录成功，会话已保存到 .browser_data/weread")
            return True
        time.sleep(3)
    print("✗ 登录超时。请重跑: python -m scrape_hub wechat watch login")
    return False


def require_login(page: Any) -> None:
    if not is_logged_in(page):
        raise RuntimeError(
            "未登录微信读书。请先扫码登录一次（会话会保存）:\n"
            "  python -m scrape_hub wechat watch login --headed"
        )


# ── shelf (subscriptions) ─────────────────────────────────

def add_to_shelf(page: Any, book_ids: list[str]) -> bool:
    """Subscribe the given bookIds on the WeChat Reading shelf (idempotent)."""
    js = (
        "fetch('/mp/shelf/addToShelf', {method:'POST', credentials:'include',"
        "headers:{'Content-Type':'application/json;charset=UTF-8'},"
        f"body: JSON.stringify({{bookIds: {json.dumps(book_ids)}}})"
        "}).then(r => r.text())"
    )
    body = page.evaluate(f"async () => await {js}")
    ok = '"succ":1' in body or '"errCode":0' in body
    if not ok:
        print(f"    [weread] 订阅返回: {str(body)[:200]}")
    return ok


def list_shelf(page: Any) -> list[dict]:
    """List subscribed 公众号: [{name, bookId, readerUrl}]."""
    js = (
        f"fetch('{SHELF_URL}', {{credentials:'include'}})"
        ".then(r => r.json())"
    )
    data = page.evaluate(f"async () => await {js}")
    if data.get("errCode"):
        raise RuntimeError(f"书架接口错误 errCode={data['errCode']}（-2010 表示登录已失效）")
    books = []
    for b in data.get("books", []) or []:
        book_id = str(b.get("bookId") or "")
        if not book_id.startswith("MP_WXS_"):
            continue
        m = re.search(r"[?&]v=([^&]+)", str(b.get("deepLink") or ""))
        books.append(
            {
                "name": b.get("title") or "",
                "bookId": book_id,
                "readerUrl": (
                    f"https://weread.qq.com/web/mp/reader/{m.group(1)}" if m else None
                ),
            }
        )
    return books


# ── articles ───────────────────────────────────────────────

def _on_reader_page(page: Any) -> bool:
    try:
        return page.evaluate("() => location.pathname.indexOf('/web/mp/reader/') === 0")
    except Exception:
        return False


def _captcha_visible(page: Any) -> bool:
    try:
        return page.evaluate(
            """
            () => {
                const nodes = document.querySelectorAll(
                    '[id*="captcha"], iframe[src*="captcha"], [class*="tcaptcha"]'
                );
                for (const n of nodes) {
                    for (let cur = n; cur; cur = cur.parentElement) {
                        const s = getComputedStyle(cur);
                        if (s.display === 'none' || s.visibility === 'hidden'
                            || Number(s.opacity) === 0) return false;
                    }
                    const r = n.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) return true;
                }
                return false;
            }
            """
        )
    except Exception:
        return False


def ensure_reader_page(page: Any, reader_url: str, timeout_s: int = 60) -> None:
    """Open the reader page and wait until it is ready (or report captcha)."""
    if _on_reader_page(page):
        return
    page.goto(reader_url, wait_until="domcontentloaded", timeout=30000)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _on_reader_page(page) and "公众号" in (page.title() or ""):
            return
        if _captcha_visible(page):
            raise RuntimeError(
                "微信读书弹出了验证码，请在浏览器中手动完成后再运行 "
                "（--headed 模式下窗口可见）"
            )
        time.sleep(3)
    raise RuntimeError(f"阅读器页未就绪: {page.url}")


def get_articles(page: Any, book_id: str, offset: int = 0) -> list[dict]:
    """List latest articles of one 公众号 (must be on the reader page).

    Returns [{title, url, time(unix s), rid}] sorted newest-first.
    """
    url = ARTICLES_URL.format(book_id=urllib.parse.quote(str(book_id)), offset=offset)
    js = (
        f"fetch('{url}', {{credentials:'include'}})"
        ".then(r => r.json()).then(o => JSON.stringify(o))"
    )
    raw = page.evaluate(f"async () => await {js}")
    data = json.loads(raw) if isinstance(raw, str) else raw
    if data.get("errCode"):
        raise RuntimeError(
            f"文章接口错误 errCode={data['errCode']}（-2041 上下文错误 / -2010 登录失效）"
        )

    items: list[dict] = []
    for grp in data.get("reviews") or []:
        for s in grp.get("subReviews") or []:
            r = s.get("review") or {}
            mi = r.get("mpInfo") or {}
            title = mi.get("title")
            if not title:
                continue
            original_id = (mi.get("originalId") or "").replace("~", "_")
            items.append(
                {
                    "title": title,
                    "url": (
                        "https://mp.weixin.qq.com/s/" + original_id
                        if original_id else ""
                    ),
                    "time": r.get("createTime") or grp.get("createTime") or 0,
                    "rid": r.get("reviewId") or "",
                }
            )
    items.sort(key=lambda x: x["time"], reverse=True)
    return items


# ── watch state / diff ─────────────────────────────────────

def _state_path(state_dir: str | Path, book_id: str) -> Path:
    return Path(state_dir) / f"state_{book_id}.json"


def load_state(state_dir: str | Path, book_id: str) -> dict:
    p = _state_path(state_dir, book_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"book_id": book_id, "account": "", "known": {}}


def save_state(state_dir: str | Path, book_id: str, account: str, articles: list[dict]) -> Path:
    state = load_state(state_dir, book_id)
    state["account"] = account or state.get("account", "")
    state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    known: dict = state.setdefault("known", {})
    for a in articles:
        if a.get("url"):
            known[a["url"]] = {"title": a.get("title", ""), "time": a.get("time", 0)}
    # Cap stored history to the latest 200 entries.
    if len(known) > 200:
        sorted_urls = sorted(known, key=lambda u: known[u].get("time", 0), reverse=True)
        known = {u: known[u] for u in sorted_urls[:200]}
        state["known"] = known
    p = _state_path(state_dir, book_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def diff_new(state: dict, articles: list[dict]) -> list[dict]:
    """Articles in the latest list that we have not seen before."""
    known = state.get("known", {})
    return [a for a in articles if a.get("url") and a["url"] not in known]
