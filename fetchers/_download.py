"""共享的 PDF 下载器，支持可选磁盘缓存。

设计：
- 调用方传 cache_key（如 arxiv id / doi-hash）+ cache_dir
- cache_dir 为 None 时，下载到系统临时目录，调用方解析完应自行删除
- cache_dir 非 None 时，下载到 cache_dir/{cache_key}.pdf，命中即复用
- 返回 (路径, 是否来自缓存)。调用方据 is_cached 决定是否 unlink
"""

from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path

import httpx

_SAFE_KEY = re.compile(r"[^A-Za-z0-9._-]+")


def safe_cache_key(raw: str) -> str:
    """把任意标识符压成文件名安全的 key。过长时用 hash 兜底。"""
    s = _SAFE_KEY.sub("_", raw).strip("_") or "paper"
    if len(s) > 80:
        s = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return s


def download_pdf(
    url: str,
    *,
    cache_key: str | None = None,
    cache_dir: Path | None = None,
    timeout: float = 60.0,
) -> tuple[Path, bool]:
    """下载 PDF。返回 (路径, 是否命中缓存)。

    - 命中缓存：直接返回，不发起网络请求
    - 未命中且开启缓存：下载到 cache_dir/{cache_key}.pdf
    - 未开启缓存：下载到临时文件
    """
    if cache_dir is not None and cache_key:
        target = cache_dir / f"{cache_key}.pdf"
        if target.exists() and target.stat().st_size > 0:
            return target, True
    else:
        target = None

    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        resp = client.get(url)
        resp.raise_for_status()
        if not resp.content.startswith(b"%PDF"):
            raise RuntimeError(f"下载的内容不是 PDF: {url}")
        if target is None:
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.write(resp.content)
            tmp.close()
            return Path(tmp.name), False
        # 写入临时文件后原子改名，避免并发下两个线程写同一个目标
        tmp_path = target.with_suffix(target.suffix + ".part")
        tmp_path.write_bytes(resp.content)
        tmp_path.replace(target)
        return target, False
