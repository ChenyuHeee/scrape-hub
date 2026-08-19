"""Standalone article fetcher — used by the ``wechat fetch`` CLI command.

Give it any list of WeChat article URLs (from a search engine, RSS, an
exported bookmark file, …) and it fetches full metadata + body text straight
from mp.weixin.qq.com, bypassing search-engine index delays entirely.
"""

from __future__ import annotations

import json
from pathlib import Path

from scrape_hub.core.browser import BrowserManager


class ArticleFetcher:
    """Batch-fetch WeChat article content with a persistent browser."""

    def __init__(
        self,
        output_dir: str | Path = "data/wechat_fetch",
        headless: bool = True,
        browser_data_dir: str | Path | None = None,
    ):
        self.output_dir = Path(output_dir)
        self.headless = headless
        self.browser_data_dir = Path(
            browser_data_dir or ".browser_data/wechat_fetch"
        )

    def fetch(
        self,
        urls: list[str],
        include_content: bool = True,
        pause: float = 1.5,
        max_articles: int | None = None,
    ) -> list[dict]:
        """Fetch all URLs; returns item dicts (with ``error`` on failure)."""
        from scrape_hub.platforms.wechat.article import fetch_many

        with BrowserManager(
            user_data_dir=self.browser_data_dir,
            headless=self.headless,
            locale="zh-CN",
        ) as bm:
            results = fetch_many(
                bm.page,
                urls,
                resolve=True,
                include_content=include_content,
                pause=pause,
                max_articles=max_articles,
            )
        return results

    def save(self, results: list[dict], tag: str = "") -> Path:
        """Save results to JSON (and Markdown) in the output directory."""
        from datetime import datetime

        self.output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"wechat_fetch_{tag}_{ts}" if tag else f"wechat_fetch_{ts}"

        json_path = self.output_dir / f"{name}.json"
        json_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"✓ JSON 已保存: {json_path}")

        md_path = self.output_dir / f"{name}.md"
        lines = [
            "# 微信公众号文章正文抓取\n",
            f"> 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            f"共 {len(results)} 篇\n\n---\n",
        ]
        for i, item in enumerate(results, 1):
            if item.get("error") and not item.get("content"):
                lines.append(f"### {i}. ❌ {item.get('url', '')}\n")
                lines.append(f"*{item['error']}*\n\n---\n")
                continue
            lines.append(f"### {i}. {item.get('title', 'N/A')}\n")
            meta = []
            if item.get("account"):
                meta.append(f"**来源**: {item['account']}")
            if item.get("author"):
                meta.append(f"**作者**: {item['author']}")
            if item.get("publish_time"):
                meta.append(f"**时间**: {item['publish_time']}")
            if meta:
                lines.append("  |  ".join(meta) + "\n")
            if item.get("content"):
                lines.append("\n" + item["content"] + "\n")
            elif item.get("content_type") == "images":
                lines.append(
                    f"\n*（纯图片文章，共 {item.get('image_count', 0)} 张图）*\n"
                )
                for u in item.get("image_urls", []):
                    lines.append(f"![image]({u})\n")
            lines.append(f"\n[原文链接]({item.get('url', '')})\n\n---\n")
        md_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"✓ Markdown 已保存: {md_path}")

        return json_path


def read_urls_from_file(path: str | Path) -> list[str]:
    """Read article URLs from a text file (one per line, or JSON array)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            return [u for u in json.loads(text) if isinstance(u, str)]
        except json.JSONDecodeError:
            pass
    return [line.strip() for line in text.splitlines() if line.strip()]
