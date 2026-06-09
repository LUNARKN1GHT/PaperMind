"""Digest 写出：把筛选 + 压缩后的论文渲染成每日清单 Markdown + HTML。"""

from __future__ import annotations

from datetime import date
from html import escape
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

    # 同步生成 HTML：当天一份 + latest.html（双击即看最新，断网也能开）
    html = _render_html(items, on_date, categories or [], scanned)
    (output_dir / f"digest_{on_date.isoformat()}.html").write_text(html, encoding="utf-8")
    (output_dir / "latest.html").write_text(html, encoding="utf-8")

    return out_path


_CSS = """
:root { color-scheme: light dark; }
body { max-width: 820px; margin: 40px auto; padding: 0 20px;
  font: 16px/1.7 -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; }
h1 { font-size: 24px; margin-bottom: 4px; }
.meta { color: #888; font-size: 14px; margin-bottom: 28px; }
.card { border: 1px solid #8883; border-radius: 12px; padding: 18px 22px;
  margin-bottom: 18px; }
.card h2 { font-size: 18px; margin: 0 0 10px; line-height: 1.4; }
.stars { color: #f5a623; letter-spacing: 2px; }
.row { color: #888; font-size: 13px; margin: 2px 0; }
.row a { color: #4a90e2; text-decoration: none; }
.reason { color: #888; font-size: 13px; font-style: italic; margin: 6px 0 10px; }
.summary { margin-top: 8px; }
.empty { color: #888; }
"""


def _render_html(
    items: list[tuple[FeedEntry, dict[str, object]]],
    on_date: date,
    categories: list[str],
    scanned: int,
) -> str:
    cards = []
    if not items:
        cards.append('<p class="empty">今天没有命中研究画像的新论文。</p>')
    else:
        for i, (entry, verdict) in enumerate(items, 1):
            score = int(verdict.get("score", 0) or 0)
            stars = "★" * score + "☆" * (5 - score)
            reason = escape(str(verdict.get("reason", "")).strip())
            summary = escape(str(verdict.get("summary", "")).strip()) or "（无摘要）"
            cards.append(
                f'<div class="card">'
                f'<h2>{i}. {escape(entry.title)}</h2>'
                f'<div class="row"><span class="stars">{stars}</span> ({score}/5)</div>'
                f'<div class="row">作者：{escape(entry.authors_str)}</div>'
                f'<div class="row">{escape(entry.primary_category)} · '
                f'<a href="{escape(entry.url)}">{escape(entry.arxiv_id)}</a></div>'
                + (f'<div class="reason">命中理由：{reason}</div>' if reason else "")
                + f'<div class="summary">{summary}</div></div>'
            )
    return (
        f'<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>arXiv 速读 · {on_date.isoformat()}</title><style>{_CSS}</style></head>"
        f"<body><h1>arXiv 每日速读 · {on_date.isoformat()}</h1>"
        f'<div class="meta">扫描分类：{escape(", ".join(categories))}　|　'
        f"扫描 {scanned} 篇，命中 {len(items)} 篇</div>"
        + "".join(cards)
        + "</body></html>"
    )
