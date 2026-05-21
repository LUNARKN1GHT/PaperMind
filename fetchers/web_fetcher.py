"""Web Fetcher：arXiv 直接拿 PDF，DOI 走 Unpaywall。

注意：CLAUDE.md 提到 Sci-Hub fallback，本实现刻意未集成 —— 版权风险明确。
如确实需要，请在外部脚本中处理，不在主 pipeline 内置。
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx

from . import FetchResult
from ._download import download_pdf, safe_cache_key
from .pdf_parser import parse_pdf

_ARXIV_PDF_URL = "https://arxiv.org/pdf/{id}.pdf"
_ARXIV_ABS_API = "http://export.arxiv.org/api/query?id_list={id}&max_results=1"
_UNPAYWALL_URL = "https://api.unpaywall.org/v2/{doi}?email={email}"

_TITLE_RE = re.compile(r"<title>([^<]+)</title>", re.IGNORECASE | re.DOTALL)
_AUTHOR_RE = re.compile(
    r"<author>\s*<name>([^<]+)</name>", re.IGNORECASE | re.DOTALL
)
_PUBLISHED_RE = re.compile(r"<published>(\d{4})", re.IGNORECASE)


def _strip_version(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id)


def fetch_arxiv(arxiv_id: str, *, cache_dir: Path | None = None) -> FetchResult:
    """从 arXiv 拉 PDF + 元数据。"""
    bare = _strip_version(arxiv_id)
    pdf_url = _ARXIV_PDF_URL.format(id=bare)
    pdf_path, cached = download_pdf(
        pdf_url, cache_key=safe_cache_key(f"arxiv_{bare}"), cache_dir=cache_dir
    )
    try:
        result = parse_pdf(pdf_path)
    finally:
        if not cached and cache_dir is None:
            pdf_path.unlink(missing_ok=True)

    # arXiv Atom API 拿元数据（标题、作者、年份）
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(_ARXIV_ABS_API.format(id=bare))
            resp.raise_for_status()
            body = resp.text
    except Exception:
        body = ""

    titles = _TITLE_RE.findall(body)
    # 第一个 <title> 通常是 feed 自身标题，论文标题是后续的；找最长的更稳
    paper_title = max(titles, key=len, default="").strip().replace("\n", " ")
    paper_title = re.sub(r"\s+", " ", paper_title)
    authors = [a.strip() for a in _AUTHOR_RE.findall(body)]
    year_match = _PUBLISHED_RE.search(body)

    if paper_title and paper_title.lower() != "arxiv query":
        result.metadata.setdefault("title", paper_title)
    if authors:
        result.metadata.setdefault("authors", ", ".join(authors))
    if year_match:
        result.metadata.setdefault("year", year_match.group(1))
    result.metadata.setdefault("venue", "arXiv")
    result.metadata.setdefault("arxiv_id", bare)
    result.metadata.setdefault("url", f"https://arxiv.org/abs/{bare}")
    result.source = "arxiv_cache" if cached else "arxiv"
    return result


def fetch_doi(
    doi: str,
    *,
    email: str | None = None,
    cache_dir: Path | None = None,
) -> FetchResult:
    """通过 Unpaywall 查询 DOI 的 open-access PDF。"""
    if not email:
        raise RuntimeError(
            "Unpaywall 要求提供 email。请在 .env 设置 UNPAYWALL_EMAIL。"
        )

    cache_key = safe_cache_key(f"doi_{doi}")

    # 若 PDF 已缓存，可以跳过 Unpaywall 查询
    if cache_dir is not None:
        cached_pdf = cache_dir / f"{cache_key}.pdf"
        if cached_pdf.exists() and cached_pdf.stat().st_size > 0:
            result = parse_pdf(cached_pdf)
            result.metadata.setdefault("doi", doi)
            result.metadata.setdefault("url", f"https://doi.org/{doi}")
            result.source = "unpaywall_cache"
            return result

    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        resp = client.get(_UNPAYWALL_URL.format(doi=doi, email=email))
        resp.raise_for_status()
        data = resp.json()

    best = data.get("best_oa_location") or {}
    pdf_url = best.get("url_for_pdf") or best.get("url")
    if not pdf_url:
        raise RuntimeError(
            f"Unpaywall 没找到 {doi} 的 open-access PDF。"
            "请提供本地 PDF 或换一篇有 OA 版本的论文。"
        )

    pdf_path, cached = download_pdf(
        pdf_url, cache_key=cache_key, cache_dir=cache_dir
    )
    try:
        result = parse_pdf(pdf_path)
    finally:
        if not cached and cache_dir is None:
            pdf_path.unlink(missing_ok=True)

    if data.get("title"):
        result.metadata.setdefault("title", data["title"])
    authors = data.get("z_authors") or []
    if authors:
        names = [
            " ".join(filter(None, [a.get("given"), a.get("family")])).strip()
            for a in authors
        ]
        names = [n for n in names if n]
        if names:
            result.metadata.setdefault("authors", ", ".join(names))
    if data.get("year"):
        result.metadata.setdefault("year", str(data["year"]))
    if data.get("journal_name"):
        result.metadata.setdefault("venue", data["journal_name"])
    result.metadata.setdefault("doi", doi)
    result.metadata.setdefault("url", f"https://doi.org/{doi}")
    result.source = "unpaywall"
    return result
