"""Writer：把 LLM 填好的字段渲染回 template.md，写到输出目录。"""

from __future__ import annotations

import re
from pathlib import Path

from slugify import slugify

_FIELD_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def render(template_text: str, filled: dict[str, str]) -> str:
    """把所有 {{field}} 替换为 filled[field]，缺失字段渲染为空串。"""

    def repl(m: re.Match[str]) -> str:
        return filled.get(m.group(1), "").strip()

    return _FIELD_RE.sub(repl, template_text)


def _safe_short(s: str, max_len: int = 50) -> str:
    """slugify 后再截断，避免文件名过长 / 含奇怪字符。"""
    out = slugify(s, max_length=max_len, word_boundary=True, lowercase=False)
    return out or "untitled"


def make_filename(filled: dict[str, str]) -> str:
    """`{year}_{first_author_last_name}_{short_title}.md`"""
    year = (filled.get("year") or "n.d.").strip()[:4] or "n.d."

    authors = (filled.get("authors") or "").strip()
    first = authors.split(",")[0].strip() if authors else "anon"
    # 取最后一个空格后的部分作为 last name；中文名整体保留
    if " " in first:
        first = first.rsplit(" ", 1)[-1]
    first_slug = _safe_short(first, max_len=30) or "anon"

    title = (filled.get("title") or "untitled").strip()
    title_slug = _safe_short(title, max_len=50) or "untitled"

    return f"{year}_{first_slug}_{title_slug}.md"


def write_note(
    filled: dict[str, str],
    template_path: Path,
    output_dir: Path,
) -> Path:
    template_text = template_path.read_text(encoding="utf-8")
    rendered = render(template_text, filled)

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / make_filename(filled)

    # 若同名文件已存在，加 _1 / _2 后缀
    if out_path.exists():
        stem, suffix = out_path.stem, out_path.suffix
        i = 1
        while True:
            candidate = output_dir / f"{stem}_{i}{suffix}"
            if not candidate.exists():
                out_path = candidate
                break
            i += 1

    out_path.write_text(rendered, encoding="utf-8")
    return out_path
