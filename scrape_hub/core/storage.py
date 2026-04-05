"""Storage helpers: save scraping results as JSON + Markdown."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from scrape_hub.core.base_scraper import ScrapeResult


class Storage:
    """Utility class for persisting scraping results."""

    @staticmethod
    def save(
        results: list[ScrapeResult],
        output_dir: str | Path,
        platform_name: str,
        md_formatter: Callable[[dict, int], str] | None = None,
    ) -> tuple[Path, Path]:
        """
        Save results to JSON and Markdown files.

        Returns (json_path, md_path).
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # ── JSON ────────────────────────────────────────────
        json_path = output_dir / f"{platform_name}_{timestamp}.json"
        payload = [
            {
                "query_type": r.query_type,
                "query_value": r.query_value,
                "collected_at": r.collected_at,
                "items": r.items,
                **({"error": r.error} if r.error else {}),
            }
            for r in results
        ]
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n✓ JSON 已保存: {json_path}")

        # ── Markdown ────────────────────────────────────────
        md_path = output_dir / f"{platform_name}_{timestamp}.md"
        total = sum(len(r.items) for r in results)

        lines: list[str] = [
            f"# {platform_name} 搜索结果\n",
            f"> 搜索时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            f"共执行 {len(results)} 个查询，收集 {total} 条结果\n",
            "---\n",
        ]

        for r in results:
            lines.append(f"## {r.query_type}: {r.query_value}\n")
            if r.error:
                lines.append(f"*错误: {r.error}*\n\n")
            if not r.items:
                lines.append("*（无结果）*\n\n")
                continue
            for i, item in enumerate(r.items, 1):
                if md_formatter:
                    lines.append(md_formatter(item, i))
                else:
                    lines.append(Storage._default_md_format(item, i))

        md_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"✓ Markdown 已保存: {md_path}")

        return json_path, md_path

    @staticmethod
    def _default_md_format(item: dict, index: int) -> str:
        title = item.get("title") or item.get("text", "N/A")[:80]
        parts = [f"### {index}. {title}\n"]
        for k, v in item.items():
            if k not in ("title", "text") and v:
                parts.append(f"**{k}**: {v}\n")
        if text := item.get("text"):
            parts.append(f"\n{text}\n")
        parts.append("\n---\n")
        return "\n".join(parts)

    @staticmethod
    def load_json(path: str | Path) -> list[dict]:
        """Load previously saved JSON results."""
        path = Path(path)
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def list_saved(output_dir: str | Path, platform_name: str = "") -> list[Path]:
        """List saved JSON files in the output directory."""
        output_dir = Path(output_dir)
        if not output_dir.exists():
            return []
        pattern = f"{platform_name}_*.json" if platform_name else "*.json"
        return sorted(output_dir.glob(pattern), reverse=True)
