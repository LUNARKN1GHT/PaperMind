"""Input Router：识别输入字符串的类型，分发到对应的 fetcher 标签。

返回值是一个 InputSpec，包含归一化后的标识符（例如 arXiv id），
具体的获取动作由 main.py 根据 kind 调用对应 fetcher。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

InputKind = Literal["pdf", "arxiv", "doi", "title"]

# arXiv: 新格式 YYMM.NNNNN(vN)? 或 旧格式 cs.CL/0701001
_ARXIV_NEW = re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?$")
_ARXIV_OLD = re.compile(r"^([a-z\-]+(\.[A-Z]{2})?/\d{7})(v\d+)?$")
_ARXIV_URL = re.compile(
    r"arxiv\.org/(?:abs|pdf)/([\w\-./]+?)(?:v\d+)?(?:\.pdf)?(?:[#?].*)?$",
    re.IGNORECASE,
)
_DOI = re.compile(r"^10\.\d{4,9}/[^\s]+$")
_DOI_URL = re.compile(r"(?:doi\.org|dx\.doi\.org)/(10\.\d{4,9}/[^\s?#]+)", re.IGNORECASE)


@dataclass(frozen=True)
class InputSpec:
    kind: InputKind
    identifier: str  # 归一化后的标识符：PDF 路径 / arXiv id / DOI / 原标题
    original: str   # 用户原始输入，便于日志和报错


def route(raw: str) -> InputSpec:
    """识别输入类型。"""
    s = raw.strip()
    if not s:
        raise ValueError("输入为空")

    is_url = s.lower().startswith(("http://", "https://"))

    # 1. 本地 PDF 文件路径（URL 不算）
    if not is_url and (s.lower().endswith(".pdf") or Path(s).expanduser().is_file()):
        path = Path(s).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"PDF 文件不存在: {s}")
        return InputSpec(kind="pdf", identifier=str(path.resolve()), original=raw)

    # 2. arXiv URL
    m = _ARXIV_URL.search(s)
    if m:
        return InputSpec(kind="arxiv", identifier=m.group(1), original=raw)

    # 3. arXiv 裸 id
    if _ARXIV_NEW.match(s) or _ARXIV_OLD.match(s):
        return InputSpec(kind="arxiv", identifier=s, original=raw)

    # 4. DOI URL
    m = _DOI_URL.search(s)
    if m:
        return InputSpec(kind="doi", identifier=m.group(1), original=raw)

    # 5. DOI 裸字符串
    if _DOI.match(s):
        return InputSpec(kind="doi", identifier=s, original=raw)

    # 6. fallback：当作标题做搜索
    return InputSpec(kind="title", identifier=s, original=raw)
