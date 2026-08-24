"""
Scrape Hub CLI — AI-agent-friendly web scraping toolkit.

Clone → install → run. No web UI, no server, no accounts needed for the
default engines.

Usage:
    python -m scrape_hub doctor

    python -m scrape_hub wechat search --keywords "大模型定价" "AI Agent"
    python -m scrape_hub wechat search --accounts 量子位 --engine sogou
    python -m scrape_hub wechat search --keywords 大模型 --fetch-content

    python -m scrape_hub wechat fetch --urls https://mp.weixin.qq.com/s/xxx
    python -m scrape_hub wechat fetch --file urls.txt
    python -m scrape_hub wechat fetch --accounts 量子位 --keywords 大模型

    python -m scrape_hub wechat watch login               # 微信读书扫码登录（一次）
    python -m scrape_hub wechat watch add <文章链接>       # 用任意一篇该号文章订阅
    python -m scrape_hub wechat watch check --all         # 检查有没有发新文章

    python -m scrape_hub x search --keywords "LLM pricing" --accounts sama
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


# ── shared helpers ─────────────────────────────────────────

def _load_yaml_config(path: str | None) -> dict:
    if not path:
        return {}
    try:
        import yaml
    except ImportError:
        print("使用 --config 需要 PyYAML: pip install pyyaml", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _print_summary(results, output_paths: list, json_out: bool) -> None:
    """Print a human summary and, with --json, a machine-readable payload."""
    total = sum(len(r.items) for r in results)
    print("\n" + "=" * 60)
    print(f"完成: 共 {len(results)} 个查询，{total} 条结果")
    for p in output_paths:
        if p:
            print(f"输出: {p}")
    print("=" * 60)

    if json_out:
        payload = {
            "summary": {
                "queries": len(results),
                "total_items": total,
                "collected_at": datetime.now().isoformat(),
            },
            "outputs": [str(p) for p in output_paths if p],
            "results": [
                {
                    "query_type": r.query_type,
                    "query_value": r.query_value,
                    "items": r.items,
                    "collected_at": r.collected_at,
                    **({"error": r.error} if r.error else {}),
                }
                for r in results
            ],
        }
        print("\n__RESULT_JSON__")
        print(json.dumps(payload, ensure_ascii=False))


# ── wechat search ──────────────────────────────────────────

def cmd_wechat_search(args) -> None:
    from scrape_hub.platforms.wechat import WeChatScraper

    config = _load_yaml_config(getattr(args, "config", None))

    if getattr(args, "keywords", None):
        config["keywords"] = args.keywords
    if getattr(args, "accounts", None):
        config["accounts"] = args.accounts
    if getattr(args, "engine", None):
        config["engines"] = [args.engine] if args.engine != "all" else config.get(
            "engines", ["metasearch", "sogou"]
        )
    if getattr(args, "max_pages", None):
        config["max_pages"] = args.max_pages
    if getattr(args, "max_results", None):
        config["max_results_per_engine"] = args.max_results
    if getattr(args, "fetch_content", None):
        config["fetch_content"] = True
    if getattr(args, "page_pause", None):
        config["page_pause"] = args.page_pause

    if not config.get("keywords") and not config.get("accounts"):
        print("请提供至少一个关键词 (--keywords) 或公众号 (--accounts)。")
        sys.exit(1)

    print(f"引擎: {', '.join(config.get('engines', ['metasearch', 'sogou']))}")

    scraper = WeChatScraper(
        config=config,
        output_dir=args.output or "data/wechat",
        headless=not getattr(args, "headed", False),
    )
    results = scraper.run(save=False)
    total = sum(len(r.items) for r in results)
    if total == 0:
        engines = config.get("engines", [])
        print("\n⚠ 所有引擎均未返回结果。提示:")
        if engines != ["sogou"]:
            print("  - Sogou 引擎可能触发验证码；若当前网络下元搜索被拦截，")
            print("    试试: --engine sogou（或 --engine all）")
        if engines != ["metasearch"]:
            print("  - 搜狗验证码/无结果时可改用: --engine metasearch")
        print("  - 网络要求可访问 weixin.sogou.com / bing.com / baidu.com / so.com")
        print("  - 关键词建议用公众号文章常用语，避免过短或过泛")
        sys.exit(1)

    paths = []
    try:
        from scrape_hub.core.storage import Storage

        paths = list(
            Storage.save(
                results=results,
                output_dir=scraper.output_dir,
                platform_name="wechat",
                md_formatter=scraper.format_item_md,
            )
        )
    except Exception as e:
        print(f"保存结果失败: {e}")

    _print_summary(results, paths, getattr(args, "json", False))


# ── wechat fetch ───────────────────────────────────────────

def cmd_wechat_fetch(args) -> None:
    from scrape_hub.platforms.wechat import fetcher
    from scrape_hub.platforms.wechat.fetcher import ArticleFetcher

    urls: list[str] = []
    tag = ""

    if getattr(args, "urls", None):
        urls = args.urls
        tag = "urls"
    elif getattr(args, "file", None):
        urls = fetcher.read_urls_from_file(args.file)
        tag = args.file.split("/")[-1].split(".")[0][:20] or "file"
    elif getattr(args, "accounts", None):
        # Discover article links via search engines, then fetch content.
        from scrape_hub.platforms.wechat import WeChatScraper

        # Account discovery needs maximum coverage: default to all engines
        # (explicit --engine still overrides).
        if getattr(args, "engine", None):
            engines = [args.engine] if args.engine != "all" else ["metasearch", "sogou"]
        else:
            engines = ["metasearch", "sogou"]
        config = {
            "engines": engines,
            "accounts": args.accounts,
            "max_pages": 1,
            "max_results_per_engine": args.max_results,
            "resolve_links": True,
            "fetch_content": False,
        }
        if getattr(args, "keywords", None):
            config["keywords"] = args.keywords
        print(f"第一步：通过搜索引擎发现「{', '.join(args.accounts)}」的文章链接...")
        scraper = WeChatScraper(
            config=config, output_dir="data/wechat", headless=not getattr(args, "headed", False)
        )
        results = scraper.run(save=False)
        seen: set[str] = set()
        for r in results:
            for it in r.items:
                link = it.get("link") or ""
                if link and link not in seen:
                    seen.add(link)
                    urls.append(link)
        tag = "_".join(args.accounts)[:20] if args.accounts else "accounts"
        print(f"第二步：共发现 {len(urls)} 个链接，开始抓取正文...")
    else:
        print("请提供 --urls、--file 或 --accounts 之一。")
        sys.exit(1)

    if not urls:
        print("没有可抓取的链接。")
        sys.exit(1)

    fetcher_inst = ArticleFetcher(
        output_dir=args.output or "data/wechat_fetch",
        headless=not getattr(args, "headed", False),
    )
    results = fetcher_inst.fetch(
        urls,
        include_content=not getattr(args, "metadata_only", False),
        pause=args.pause,
        max_articles=args.max_articles,
    )

    ok = [r for r in results if not r.get("error") or r.get("content")]
    print(f"\n成功抓取 {len(ok)}/{len(results)} 篇")

    # With --accounts, keep only articles whose verified publisher matches
    # (fetched pages expose the real account name).
    if getattr(args, "accounts", None):
        wanted = set(args.accounts)
        filtered = []
        for r in ok:
            acc = (r.get("account") or "").strip()
            if not acc:
                continue  # unknown publisher → drop rather than mislabel
            if any(w in acc or acc in w for w in wanted):
                filtered.append(r)
        if filtered:
            print(f"按公众号来源过滤后保留 {len(filtered)} 篇")
            results = filtered

    paths = [fetcher_inst.save(results, tag=tag)]

    if getattr(args, "json", False):
        payload = {
            "summary": {
                "fetched": len(ok),
                "total": len(results),
                "collected_at": datetime.now().isoformat(),
            },
            "outputs": [str(p) for p in paths],
            "articles": results,
        }
        print("\n__RESULT_JSON__")
        print(json.dumps(payload, ensure_ascii=False))


# ── wechat watch (weread-based account monitoring) ─────────

WATCH_BROWSER_DIR = ".browser_data/weread"
WATCH_STATE_DIR = "data/wechat_watch"


def _watch_open_browser(args):
    from scrape_hub.core.browser import BrowserManager

    return BrowserManager(
        user_data_dir=WATCH_BROWSER_DIR,
        headless=not getattr(args, "headed", False),
        locale="zh-CN",
    )


def cmd_wechat_watch(args) -> None:
    from scrape_hub.platforms.wechat import weread

    sub = args.watch_command
    try:
        with _watch_open_browser(args) as bm:
            page = bm.page

            if sub == "login":
                qr_png = None
                if not getattr(args, "headed", False):
                    qr_png = f"{WATCH_STATE_DIR}/login_qr.png"
                weread.login(page, wait_seconds=args.wait, qr_png=qr_png)
                return

            weread.require_login(page)

            if sub == "add":
                book_ids = []
                for raw in args.inputs:
                    try:
                        book_id, via = weread.book_id_from_input(page, raw)
                        print(f"  {raw[:60]} → {book_id}（{via}）")
                        book_ids.append(book_id)
                    except ValueError as e:
                        print(f"  ✗ {e}")
                if not book_ids:
                    sys.exit(1)
                if weread.add_to_shelf(page, book_ids):
                    print(f"✓ 已加入微信读书书架: {len(book_ids)} 个公众号")
                _print_shelf(page, weread)

            elif sub == "list":
                _print_shelf(page, weread)

            elif sub == "check":
                _watch_check(bm, page, args)
    except RuntimeError as e:
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(1)


def _print_shelf(page, weread) -> None:
    books = weread.list_shelf(page)
    if not books:
        print("书架为空。先添加: python -m scrape_hub wechat watch add <文章链接>")
        return
    print(f"\n已订阅公众号（{len(books)} 个）:")
    for b in books:
        print(f"  - {b['name']:<20s} {b['bookId']}")


def _watch_check(bm, page, args) -> None:
    import time as _time

    from scrape_hub.platforms.wechat import article as article_mod
    from scrape_hub.platforms.wechat import weread

    # Collect target accounts
    targets: list[dict] = []
    if getattr(args, "all_accounts", False):
        targets = weread.list_shelf(page)
    else:
        inputs = getattr(args, "inputs", None) or []
        for raw in inputs:
            try:
                book_id, _ = weread.book_id_from_input(page, raw)
                targets.append({"bookId": book_id, "name": "", "readerUrl": None})
            except ValueError as e:
                print(f"  ✗ {e}")
    if not targets:
        print("请提供公众号的文章链接 / __biz / bookId（可多个），或用 --all 监控整个书架。")
        sys.exit(1)

    interval = args.interval
    max_checks = args.max_checks
    fetch_content = getattr(args, "fetch_content", False)

    check_no = 0
    while True:
        check_no += 1
        print(f"\n=== 第 {check_no} 次检查 {_time.strftime('%Y-%m-%d %H:%M:%S')} ===")

        all_new: list[dict] = []
        fetch_page = None

        for t in targets:
            book_id = t["bookId"]
            name = t.get("name") or f"({book_id})"
            print(f"\n▸ 检查 {name} ...")

            # Ensure subscribed, then locate the reader page for this account.
            weread.add_to_shelf(page, [book_id])
            books = {b["bookId"]: b for b in weread.list_shelf(page)}
            book = books.get(book_id)
            if not book or not book.get("readerUrl"):
                print("  ✗ 书架里没有该公众号的阅读器页，跳过")
                continue
            t["name"] = book["name"] or t["name"]

            try:
                weread.ensure_reader_page(page, book["readerUrl"])
                articles = weread.get_articles(page, book_id, offset=0)
            except RuntimeError as e:
                print(f"  ✗ {e}")
                continue

            state = weread.load_state(WATCH_STATE_DIR, book_id)
            new_items = weread.diff_new(state, articles)
            weread.save_state(WATCH_STATE_DIR, book_id, t["name"], articles)

            print(f"  → 最近文章 {len(articles)} 篇，其中新文章 {len(new_items)} 篇")
            for a in new_items[:10]:
                ts = _time.strftime(
                    "%Y-%m-%d %H:%M", _time.localtime(a["time"])
                ) if a.get("time") else "?"
                print(f"    🆕 [{ts}] {a['title'][:50]}")
                print(f"        {a.get('url', '')[:80]}")
                all_new.append(
                    {
                        **a,
                        "account": t["name"],
                        "book_id": book_id,
                        "published_at": ts,
                    }
                )

            if fetch_content and new_items:
                if fetch_page is None:
                    fetch_page = bm.new_page()
                for a in new_items[:5]:
                    if not a.get("url"):
                        continue
                    full = article_mod.fetch_article(
                        fetch_page, a["url"], resolve=True, include_content=True
                    )
                    a["full"] = full
                    body = full.get("content") or ""
                    if not body and full.get("content_type") == "images":
                        body = f"[纯图片文章 {full.get('image_count', 0)} 张]"
                    print(f"    ↳ 正文: {body[:80]}")

        # Persist this check's output
        if all_new:
            _save_watch_output(all_new)
        elif check_no == 1:
            print("\n没有新文章（首次运行会建立基线，后续才报告新增）。")

        if max_checks is not None and check_no >= max_checks:
            break
        if interval <= 0:
            break
        print(f"\n⏳ {interval}s 后进行下一次检查...")
        _time.sleep(interval)


def _save_watch_output(new_articles: list[dict]) -> None:
    import json as _json
    from datetime import datetime

    out_dir = Path(WATCH_STATE_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = out_dir / f"watch_new_{ts}.json"
    json_path.write_text(
        _json.dumps(new_articles, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n✓ 新文章 JSON 已保存: {json_path}")

    md_path = out_dir / f"watch_new_{ts}.md"
    lines = [
        "# 公众号新文章\n",
        f"> 检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        f"共 {len(new_articles)} 篇\n\n---\n",
    ]
    for i, a in enumerate(new_articles, 1):
        lines.append(f"### {i}. {a.get('title', 'N/A')}\n")
        meta = []
        if a.get("account"):
            meta.append(f"**公众号**: {a['account']}")
        if a.get("published_at"):
            meta.append(f"**时间**: {a['published_at']}")
        if meta:
            lines.append("  |  ".join(meta) + "\n")
        full = a.get("full") or {}
        if full.get("content"):
            lines.append("\n" + full["content"] + "\n")
        elif full.get("content_type") == "images":
            lines.append(f"\n*（纯图片文章，共 {full.get('image_count', 0)} 张图）*\n")
        if a.get("url"):
            lines.append(f"\n[阅读原文]({a['url']})\n")
        lines.append("\n---\n")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✓ 新文章 Markdown 已保存: {md_path}")


# ── x search ───────────────────────────────────────────────

def cmd_x_search(args) -> None:
    from scrape_hub.platforms.x_twitter import XTwitterScraper

    config = _load_yaml_config(getattr(args, "config", None))
    if getattr(args, "keywords", None):
        config["keywords"] = args.keywords
    if getattr(args, "accounts", None):
        config["accounts"] = args.accounts
    if getattr(args, "max_scroll", None):
        config["max_scroll"] = args.max_scroll

    if not config.get("keywords") and not config.get("accounts"):
        print("请提供至少一个关键词 (--keywords) 或账号 (--accounts)。")
        sys.exit(1)

    scraper = XTwitterScraper(
        config=config,
        output_dir=args.output or "data/x_twitter",
        headless=not getattr(args, "headed", False),
    )
    results = scraper.run(save=False)
    total = sum(len(r.items) for r in results)
    if total == 0:
        print("\n⚠ 未获取到推文。X 搜索需要登录态：")
        print("  首次请运行: python -m scrape_hub x search --headed --keywords test")
        print("  完成登录后，会话会保存到 .browser_data/ 供后续使用。")
        sys.exit(1)

    paths = []
    try:
        from scrape_hub.core.storage import Storage

        paths = list(
            Storage.save(
                results=results,
                output_dir=scraper.output_dir,
                platform_name="x_twitter",
                md_formatter=scraper.format_item_md,
            )
        )
    except Exception as e:
        print(f"保存结果失败: {e}")

    _print_summary(results, paths, getattr(args, "json", False))


# ── doctor ─────────────────────────────────────────────────

def cmd_doctor(args) -> None:
    """Check the environment and report what is ready / missing."""
    import platform
    import subprocess

    print("Scrape Hub 环境检查 (doctor)\n")

    checks = []

    # Python
    py = platform.python_version()
    checks.append(("Python 版本", py, tuple(map(int, py.split("."))) >= (3, 10)))

    # Playwright
    try:
        import playwright

        pw_version = getattr(playwright, "__version__", "unknown")
        checks.append(("Playwright 包", pw_version, True))
    except ImportError:
        checks.append(("Playwright 包", "未安装 → pip install -e .", False))

    # Chromium browser binary (check the Playwright cache, no launch needed)
    import os
    from pathlib import Path

    cache_dirs = [
        Path.home() / "Library/Caches/ms-playwright",   # macOS
        Path.home() / ".cache/ms-playwright",           # Linux
        Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright",  # Windows
    ]
    chromium_found = []
    for d in cache_dirs:
        if d.exists():
            chromium_found = sorted(d.glob("chromium-*"))
            if chromium_found:
                break
    checks.append((
        "Chromium 浏览器",
        str(chromium_found[0]) if chromium_found else "未安装 → playwright install chromium",
        bool(chromium_found),
    ))

    # Network reachability to engines
    import urllib.request

    for name, url in [
        ("Bing", "https://www.bing.com"),
        ("Baidu", "https://www.baidu.com"),
        ("360 搜索", "https://www.so.com"),
        ("搜狗微信", "https://weixin.sogou.com"),
        ("公众号文章页", "https://mp.weixin.qq.com"),
    ]:
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=6) as resp:
                ok = resp.status < 500
        except Exception:
            ok = False
        checks.append((f"网络: {name}", url, ok))

    # Optional: gh CLI (for GitHub Actions cloud scraping)
    try:
        subprocess.run(
            ["gh", "--version"], capture_output=True, check=True, timeout=5
        )
        checks.append(("gh CLI（可选，云端抓取）", "已安装", True))
    except Exception:
        checks.append(("gh CLI（可选，云端抓取）", "未安装（可跳过）", True))

    for name, detail, ok in checks:
        mark = "✓" if ok else "✗"
        print(f"  {mark} {name}: {detail}")

    failed = [c for c in checks if not c[2]]
    print()
    if failed:
        print("存在未就绪项。安装指引:")
        print("  pip install -e .")
        print("  playwright install chromium")
        sys.exit(1)
    else:
        print("✓ 环境就绪，可以开始搜索。示例:")
        print('  python -m scrape_hub wechat search --keywords "大模型" --fetch-content')
        print("  python -m scrape_hub wechat fetch --urls <文章链接>")
        sys.exit(0)


# ── parser ─────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scrape-hub",
        description="AI-Agent 友好的网页抓取 CLI（X/Twitter、微信公众号）",
    )
    sub = parser.add_subparsers(dest="command")

    # doctor
    p = sub.add_parser("doctor", help="环境自检（Python/Playwright/网络）")
    p.set_defaults(func=cmd_doctor)

    # wechat search
    p = sub.add_parser("wechat", help="微信公众号文章")
    wsub = p.add_subparsers(dest="subcommand")

    ws = wsub.add_parser("search", help="多引擎搜索公众号文章")
    ws.add_argument("--keywords", nargs="+", help="搜索关键词（可多个）")
    ws.add_argument("--accounts", nargs="+", help="公众号名称（可多个）")
    ws.add_argument(
        "--engine",
        choices=["metasearch", "sogou", "all"],
        default=None,
        help="搜索引擎: metasearch(Bing/Baidu/360) | sogou(搜狗微信) | all(全部合并, 默认)",
    )
    ws.add_argument("--max-pages", type=int, help="搜狗引擎每关键词最大翻页数")
    ws.add_argument("--max-results", type=int, default=10, help="每引擎每查询最大结果数")
    ws.add_argument("--page-pause", type=float, help="页面加载等待秒数")
    ws.add_argument(
        "--fetch-content",
        action="store_true",
        help="抓取每篇文章完整正文（慢，但可校验公众号来源）",
    )
    ws.add_argument("--headed", action="store_true", help="显示浏览器窗口（默认无头）")
    ws.add_argument("-o", "--output", help="输出目录")
    ws.add_argument("--config", help="YAML 配置文件路径")
    ws.add_argument("--json", action="store_true", help="结尾输出机器可读 JSON")
    ws.set_defaults(func=cmd_wechat_search)

    wf = wsub.add_parser("fetch", help="直接抓取文章正文（绕过搜索引擎）")
    wf.add_argument("--urls", nargs="+", help="文章链接（可多个）")
    wf.add_argument("--file", help="每行一个链接的文本文件（或 JSON 数组）")
    wf.add_argument("--accounts", nargs="+", help="公众号名称：先搜索发现链接再抓正文")
    wf.add_argument("--keywords", nargs="+", help="配合 --accounts 使用的关键词")
    wf.add_argument(
        "--engine",
        choices=["metasearch", "sogou", "all"],
        default=None,
        help="发现链接用的引擎（配合 --accounts；默认全部引擎合并）",
    )
    wf.add_argument("--max-results", type=int, default=10, help="每公众号最多抓取篇数")
    wf.add_argument("--max-articles", type=int, help="全局最多抓取篇数")
    wf.add_argument("--metadata-only", action="store_true", help="只抓元数据不抓正文")
    wf.add_argument("--pause", type=float, default=1.5, help="每篇文章间隔秒数")
    wf.add_argument("--headed", action="store_true", help="显示浏览器窗口")
    wf.add_argument("-o", "--output", help="输出目录")
    wf.add_argument("--json", action="store_true", help="结尾输出机器可读 JSON")
    wf.set_defaults(func=cmd_wechat_fetch)

    ww = wsub.add_parser(
        "watch",
        help="监控公众号新文章（基于微信读书，需先 watch login 扫码一次）",
    )
    wwsub = ww.add_subparsers(dest="watch_command")

    wl = wwsub.add_parser("login", help="微信读书扫码登录（会话持久保存）")
    wl.add_argument("--wait", type=int, default=180, help="等待扫码秒数")
    wl.add_argument("--headed", action="store_true", help="显示浏览器窗口扫码")
    wl.set_defaults(func=cmd_wechat_watch)

    wa = wwsub.add_parser(
        "add", help="订阅公众号（给任意一篇它的文章链接 / __biz / bookId）"
    )
    wa.add_argument("inputs", nargs="+", help="文章链接 / __biz / MP_WXS_ 开头的 bookId")
    wa.add_argument("--headed", action="store_true", help="显示浏览器窗口")
    wa.set_defaults(func=cmd_wechat_watch)

    wls = wwsub.add_parser("list", help="列出已订阅的公众号")
    wls.add_argument("--headed", action="store_true", help="显示浏览器窗口")
    wls.set_defaults(func=cmd_wechat_watch)

    wc = wwsub.add_parser("check", help="检查公众号最新文章并报告新增")
    wc.add_argument(
        "inputs",
        nargs="*",
        help="文章链接 / __biz / bookId（可多个）；不填则配合 --all",
    )
    wc.add_argument("--all", dest="all_accounts", action="store_true",
                    help="检查书架上全部公众号")
    wc.add_argument("--interval", type=int, default=0,
                    help="持续监控：每隔 N 秒检查一次（0=只查一次）")
    wc.add_argument("--max-checks", type=int, default=1, help="最大检查次数")
    wc.add_argument("--fetch-content", action="store_true",
                    help="新文章同时抓取正文（纯图片文章会收集图片链接）")
    wc.add_argument("--headed", action="store_true", help="显示浏览器窗口")
    wc.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    wc.set_defaults(func=cmd_wechat_watch)

    # x search
    p = sub.add_parser("x", help="X / Twitter 推文")
    xsub = p.add_subparsers(dest="subcommand")
    xs = xsub.add_parser("search", help="按账号/关键词搜索推文")
    xs.add_argument("--keywords", nargs="+", help="搜索关键词（可多个）")
    xs.add_argument("--accounts", nargs="+", help="X 账号（可多个，不含 @）")
    xs.add_argument("--max-scroll", type=int, help="最大滚动次数")
    xs.add_argument("--headed", action="store_true", help="显示浏览器窗口")
    xs.add_argument("-o", "--output", help="输出目录")
    xs.add_argument("--config", help="YAML 配置文件路径")
    xs.add_argument("--json", action="store_true", help="结尾输出机器可读 JSON")
    xs.set_defaults(func=cmd_x_search)

    # Backward-compat alias: `run <platform> ...`
    p = sub.add_parser("run", help="（兼容旧版）运行爬虫")
    p.add_argument("platform", choices=["wechat", "weixin", "x", "x_twitter", "twitter"])
    p.add_argument("--keywords", nargs="+")
    p.add_argument("--accounts", nargs="+")
    p.add_argument("--engine", choices=["metasearch", "sogou", "all"], default=None)
    p.add_argument("--max-pages", type=int)
    p.add_argument("--max-scroll", type=int)
    p.add_argument("--max-results", type=int, default=10)
    p.add_argument("--fetch-content", action="store_true")
    p.add_argument("--headless", action="store_true", help="（兼容旧版，默认即无头）")
    p.add_argument("-o", "--output")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_run_compat)

    return parser


def cmd_run_compat(args) -> None:
    """Map the legacy `run <platform>` syntax onto the new subcommands."""
    argv = []
    if args.platform in ("wechat", "weixin"):
        argv = ["wechat", "search"]
        if args.keywords:
            argv += ["--keywords", *args.keywords]
        if args.accounts:
            argv += ["--accounts", *args.accounts]
        if args.engine:
            argv += ["--engine", args.engine]
        if args.max_pages:
            argv += ["--max-pages", str(args.max_pages)]
        if args.max_results:
            argv += ["--max-results", str(args.max_results)]
        if args.fetch_content:
            argv += ["--fetch-content"]
    else:
        argv = ["x", "search"]
        if args.keywords:
            argv += ["--keywords", *args.keywords]
        if args.accounts:
            argv += ["--accounts", *args.accounts]
        if args.max_scroll:
            argv += ["--max-scroll", str(args.max_scroll)]
    if args.output:
        argv += ["-o", args.output]
    if args.json:
        argv += ["--json"]

    parser = build_parser()
    ns = parser.parse_args(argv)
    ns.func(ns)


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        sys.exit(0)
    if not getattr(args, "func", None):
        parser.parse_args([args.command, "--help"])
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
