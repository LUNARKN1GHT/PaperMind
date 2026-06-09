"""Digest 写出：把筛选 + 压缩后的论文渲染成每日清单 Markdown。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fetchers.arxiv_feed import FeedEntry


def write_digest(
    items: list[tuple[FeedEntry, dict[str, object]]],
    output_dir: Path,
    *,
    on_date: date | None = None,
    categories: list[str] | None = None,
    scanned: int = 0,
) -> Path:
    """items: (entry, 判定结果) 列表，已只含 relevant 项，调用方负责排序。"""
    on_date = on_date or date.today()
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"digest_{on_date.isoformat()}.md"

    lines: list[str] = [
        f"# arXiv 每日速读 · {on_date.isoformat()}",
        "",
        f"- 扫描分类：{', '.join(categories or [])}",
        f"- 扫描论文 {scanned} 篇，命中相关 {len(items)} 篇",
        "",
        "---",
        "",
    ]

    if not items:
        lines.append("_今天没有命中研究画像的新论文。_")
    else:
        for i, (entry, verdict) in enumerate(items, 1):
            score = verdict.get("score", 0)
            stars = "★" * int(score) + "☆" * (5 - int(score))
            lines.append(f"## {i}. {entry.title}")
            lines.append("")
            lines.append(f"- 相关度：{stars} ({score}/5)")
            lines.append(f"- 作者：{entry.authors_str}")
            lines.append(f"- 分类：{entry.primary_category} · [{entry.arxiv_id}]({entry.url})")
            reason = str(verdict.get("reason", "")).strip()
            if reason:
                lines.append(f"- 命中理由：{reason}")
            lines.append("")
            summary = str(verdict.get("summary", "")).strip()
            lines.append(summary or "_（无摘要）_")
            lines.append("")
            lines.append("---")
            lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
