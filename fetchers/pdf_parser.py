"""PDF 解析：用 PyMuPDF 提取文本，保留段落顺序，尝试剥离页眉页脚。"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import fitz  # PyMuPDF

from . import FetchResult


def _strip_running_headers(pages: list[str]) -> list[str]:
    """若多页首/末行重复出现，认为是页眉页脚，去掉。"""
    if len(pages) < 3:
        return pages

    first_lines: Counter[str] = Counter()
    last_lines: Counter[str] = Counter()
    for p in pages:
        lines = [ln.strip() for ln in p.splitlines() if ln.strip()]
        if not lines:
            continue
        first_lines[lines[0]] += 1
        last_lines[lines[-1]] += 1

    threshold = max(3, len(pages) // 2)
    headers = {ln for ln, c in first_lines.items() if c >= threshold}
    footers = {ln for ln, c in last_lines.items() if c >= threshold}

    cleaned: list[str] = []
    for p in pages:
        lines = p.splitlines()
        # 砍掉首行/末行如果是公共页眉页脚（仅检查首尾各一行，避免误删正文）
        if lines and lines[0].strip() in headers:
            lines = lines[1:]
        if lines and lines[-1].strip() in footers:
            lines = lines[:-1]
        cleaned.append("\n".join(lines))
    return cleaned


def parse_pdf(path: str | Path) -> FetchResult:
    path = Path(path)
    with fitz.open(path) as doc:
        pages_raw = [page.get_text("text") for page in doc]
        meta = doc.metadata or {}

    pages = _strip_running_headers(pages_raw)
    text = "\n\n".join(pages).strip()

    metadata: dict[str, str] = {}
    if meta.get("title"):
        metadata["title"] = meta["title"].strip()
    if meta.get("author"):
        metadata["authors"] = meta["author"].strip()

    return FetchResult(raw_text=text, metadata=metadata, source="pdf")
