"""arXiv 发现式抓取：按分类 + 时间窗拉最近论文的元数据。

与 web_fetcher.fetch_arxiv 的区别：
- fetch_arxiv 是「按 id 下载 PDF 解析全文」，用于单篇详细笔记。
- 这里只取 title / authors / abstract，**不下载 PDF**，用于每日 digest 的相关性过滤。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET

import httpx

_API_URL = "https://export.arxiv.org/api/query"
_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV_NS = "{http://arxiv.org/schemas/atom}"


@dataclass
class FeedEntry:
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    published: str  # ISO 时间戳
    primary_category: str
    url: str  # abs 页面链接

    @property
    def authors_str(self) -> str:
        return ", ".join(self.authors)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _parse_entry(entry: ET.Element) -> FeedEntry:
    raw_id = (entry.findtext(f"{_ATOM}id") or "").strip()
    # id 形如 http://arxiv.org/abs/2401.12345v2 → 取 2401.12345
    bare = re.sub(r"v\d+$", "", raw_id.rsplit("/", 1)[-1])

    authors = [
        _clean(a.findtext(f"{_ATOM}name") or "")
        for a in entry.findall(f"{_ATOM}author")
    ]
    authors = [a for a in authors if a]

    prim = entry.find(f"{_ARXIV_NS}primary_category")
    primary_category = prim.get("term", "") if prim is not None else ""

    return FeedEntry(
        arxiv_id=bare,
        title=_clean(entry.findtext(f"{_ATOM}title") or ""),
        authors=authors,
        abstract=_clean(entry.findtext(f"{_ATOM}summary") or ""),
        published=(entry.findtext(f"{_ATOM}published") or "").strip(),
        primary_category=primary_category,
        url=f"https://arxiv.org/abs/{bare}",
    )


def fetch_recent(
    categories: list[str],
    *,
    days: int = 1,
    max_results: int = 200,
    timeout: float = 30.0,
) -> list[FeedEntry]:
    """拉取指定分类下最近 `days` 天提交的论文（按提交时间倒序）。

    arXiv API 不支持直接按日期范围过滤 listing，所以策略是：
    按 submittedDate 倒序拉 max_results 条，再用 published 时间在本地裁剪。
    """
    query = " OR ".join(f"cat:{c.strip()}" for c in categories if c.strip())
    params = {
        "search_query": query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": str(max_results),
    }

    # arXiv 偶发 503，简单重试几次
    last_exc: Exception | None = None
    body = ""
    for attempt in range(3):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(_API_URL, params=params)
                resp.raise_for_status()
                body = resp.text
            break
        except Exception as e:  # noqa: BLE001
            last_exc = e
            time.sleep(2 * (attempt + 1))
    else:
        raise RuntimeError(f"arXiv API 请求失败: {last_exc}")

    root = ET.fromstring(body)
    entries = [_parse_entry(e) for e in root.findall(f"{_ATOM}entry")]

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    fresh: list[FeedEntry] = []
    for e in entries:
        if not e.abstract or not e.title:
            continue
        try:
            pub = datetime.fromisoformat(e.published.replace("Z", "+00:00"))
        except ValueError:
            fresh.append(e)  # 解析不出时间就保留，交给后续判断
            continue
        if pub >= cutoff:
            fresh.append(e)

    return fresh
