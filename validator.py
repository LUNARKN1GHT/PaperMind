"""字段完整性校验。

策略：
- 必填字段：除明显主观的字段外，其他都视为必填
- personal_notes / limitations 等允许为空（前者由用户写，后者不是所有论文都有）
- 仅校验「存在且非空白」，不做语义校验（语义靠 LLM prompt 约束）
"""

from __future__ import annotations

# 允许 LLM 留空的字段（不会触发 retry）
OPTIONAL_FIELDS = frozenset({"personal_notes", "limitations", "url"})


def validate(
    filled: dict[str, str],
    target_fields: list[str],
) -> tuple[bool, list[str]]:
    """返回 (是否通过, 缺失字段列表)。"""
    missing: list[str] = []
    for f in target_fields:
        if f in OPTIONAL_FIELDS:
            continue
        v = filled.get(f, "")
        if not v or not v.strip():
            missing.append(f)
    return (len(missing) == 0, missing)
