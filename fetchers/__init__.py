"""Fetcher 子包：负责从不同来源拿到论文全文 + 元数据。

每个 fetcher 都返回 FetchResult，由上层 processor 进一步处理。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FetchResult:
    """统一的获取结果。raw_text 是论文正文，metadata 是已知字段。

    metadata 可能包含的 key（都可选）：title / authors / year / venue / url / doi / arxiv_id。
    后续模块不应假设任何字段一定存在。
    """

    raw_text: str
    metadata: dict[str, str] = field(default_factory=dict)
    source: str = ""  # 用于日志：'pdf' / 'arxiv' / 'unpaywall' / 'semantic_scholar'
