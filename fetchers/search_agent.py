"""Title 搜索：调用 Semantic Scholar Graph API。

策略：
1. 用 /paper/search 拿到最匹配的论文及其 openAccessPdf 链接（若有）。
2. 若有 open-access PDF，下载并解析全文。
3. 否则只用 abstract 作为正文（信息有限，LLM 仍能填部分字段）。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import httpx

from . import FetchResult
from .pdf_parser import parse_pdf

_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_FIELDS = (
    "title,authors,year,venue,abstract,openAccessPdf,externalIds,url"
)


def _headers(api_key: str | None) -> dict[str, str]:
    return {"x-api-key": api_key} if api_key else {}


def search_title(title: str, *, api_key: str | None = None) -> FetchResult:
    params = {"query": title, "limit": 1, "fields": _FIELDS}
    with httpx.Client(timeout=20.0, headers=_headers(api_key)) as client:
        resp = client.get(_SEARCH_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    papers = data.get("data") or []
    if not papers:
        raise RuntimeError(f"Semantic Scholar 未找到匹配论文: {title!r}")
    p = papers[0]

    metadata: dict[str, str] = {}
    if p.get("title"):
        metadata["title"] = p["title"]
    authors = p.get("authors") or []
    if authors:
        metadata["authors"] = ", ".join(a.get("name", "") for a in authors if a.get("name"))
    if p.get("year"):
        metadata["year"] = str(p["year"])
    if p.get("venue"):
        metadata["venue"] = p["venue"]
    if p.get("url"):
        metadata["url"] = p["url"]
    ext = p.get("externalIds") or {}
    if ext.get("DOI"):
        metadata["doi"] = ext["DOI"]
    if ext.get("ArXiv"):
        metadata["arxiv_id"] = ext["ArXiv"]

    abstract = p.get("abstract") or ""
    oa = p.get("openAccessPdf") or {}
    pdf_url = oa.get("url")

    raw_text = abstract
    source = "semantic_scholar_abstract"

    if pdf_url:
        try:
            with httpx.Client(timeout=60.0, follow_redirects=True) as client:
                pdf_resp = client.get(pdf_url)
                pdf_resp.raise_for_status()
                if pdf_resp.content.startswith(b"%PDF"):
                    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                    tmp.write(pdf_resp.content)
                    tmp.close()
                    pdf_path = Path(tmp.name)
                    try:
                        full = parse_pdf(pdf_path)
                        raw_text = full.raw_text or abstract
                        source = "semantic_scholar_pdf"
                    finally:
                        pdf_path.unlink(missing_ok=True)
        except Exception:
            # 下载失败就退化到 abstract，不让搜索流程整体失败
            pass

    if not raw_text:
        raise RuntimeError(
            f"论文 {p.get('title')!r} 既无 abstract 也无可下载 PDF，跳过。"
        )

    return FetchResult(raw_text=raw_text, metadata=metadata, source=source)
