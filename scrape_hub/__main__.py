"""
Command-line interface for scrape-hub.

Usage:
    python -m scrape_hub run x_twitter --keywords "LLM pricing" "token cost"
    python -m scrape_hub run wechat --keywords "大模型定价" --accounts "量子位"
    python -m scrape_hub app x          # launch X Streamlit app
    python -m scrape_hub app wechat     # launch WeChat Streamlit app
"""

import argparse
import subprocess
import sys
from pathlib import Path


def cmd_run(args):
    """Run a scraper from CLI."""
    platform = args.platform

    if platform in ("x", "x_twitter", "twitter"):
        from scrape_hub.platforms.x_twitter import XTwitterScraper

        config = {}
        if args.keywords:
            config["keywords"] = args.keywords
        if args.accounts:
            config["accounts"] = args.accounts
        if args.max_scroll:
            config["max_scroll"] = args.max_scroll

        scraper = XTwitterScraper(
            config=config,
            output_dir=args.output or "data/x_twitter",
            headless=args.headless,
        )
        results = scraper.run()
        total = sum(len(r.items) for r in results)
        print(f"\n完成: 共 {total} 条推文")

    elif platform in ("wechat", "weixin"):
        from scrape_hub.platforms.wechat import WeChatScraper

        config = {}
        if args.keywords:
            config["keywords"] = args.keywords
        if args.accounts:
            config["accounts"] = args.accounts
        if args.max_pages:
            config["max_pages"] = args.max_pages

        scraper = WeChatScraper(
            config=config,
            output_dir=args.output or "data/wechat",
            headless=args.headless,
        )
        results = scraper.run()
        total = sum(len(r.items) for r in results)
        print(f"\n完成: 共 {total} 篇文章")

    else:
        print(f"未知平台: {platform}")
        print("支持的平台: x_twitter, wechat")
        sys.exit(1)


def cmd_app(args):
    """Launch the Streamlit multi-page app."""
    port = args.port or 8501
    app_file = Path(__file__).resolve().parent.parent / "app.py"

    if not app_file.exists():
        print(f"未找到入口文件: {app_file}")
        sys.exit(1)

    print(f"启动 Scrape Hub Streamlit app (端口 {port})...")
    subprocess.run(
        [
            sys.executable, "-m", "streamlit", "run", str(app_file),
            "--server.port", str(port),
        ],
        check=True,
    )


def cmd_api(args):
    """Launch the FastAPI backend server."""
    port = args.port or 8000
    print(f"启动 Scrape Hub API 后端 (端口 {port})...")
    subprocess.run(
        [
            sys.executable, "-m", "uvicorn",
            "scrape_hub.api.server:app",
            "--host", "0.0.0.0",
            "--port", str(port),
        ],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser(
        prog="scrape-hub",
        description="通用 Web 内容抓取框架",
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # ── run ──────────────────────────────────────────────────
    run_parser = subparsers.add_parser("run", help="运行爬虫")
    run_parser.add_argument("platform", help="平台名称 (x_twitter / wechat)")
    run_parser.add_argument("--keywords", nargs="+", help="搜索关键词")
    run_parser.add_argument("--accounts", nargs="+", help="搜索账号/公众号")
    run_parser.add_argument("--headless", action="store_true", help="无头模式")
    run_parser.add_argument("--output", "-o", help="输出目录")
    run_parser.add_argument("--max-scroll", type=int, help="(X) 最大滚动次数")
    run_parser.add_argument("--max-pages", type=int, help="(WeChat) 最大翻页数")
    run_parser.set_defaults(func=cmd_run)

    # ── app ──────────────────────────────────────────────────
    app_parser = subparsers.add_parser("app", help="启动 Streamlit App")
    app_parser.add_argument("--port", type=int, default=8501, help="端口号")
    app_parser.set_defaults(func=cmd_app)

    # ── api ──────────────────────────────────────────────────
    api_parser = subparsers.add_parser("api", help="启动 API 后端服务")
    api_parser.add_argument("--port", type=int, default=8000, help="端口号")
    api_parser.set_defaults(func=cmd_api)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
