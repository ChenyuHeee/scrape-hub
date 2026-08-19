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

    python -m scrape_hub x search --keywords "LLM pricing" --accounts sama
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime


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
