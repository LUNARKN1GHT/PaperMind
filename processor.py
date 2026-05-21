"""文本清洗 + 章节识别 + Chunking。

设计取舍：
- 章节切分用宽松的同义词正则（Method 同时匹配 Approach / Materials and Methods 等）
- 切不出来时退化为「前半部分 / 后半部分」两段，保证 LLM 仍能两阶段处理
- token 估算用「中文 1 字 ≈ 1.5 token, 英文 4 字符 ≈ 1 token」的粗略上限
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 章节标题候选词。key = 我们对外暴露的逻辑名，value = 一组同义词。
SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "abstract": ("abstract", "summary"),
    "intro": ("introduction", "background"),
    "related_work": ("related work", "related works", "prior work", "literature review"),
    "method": (
        "method", "methods", "methodology", "approach", "approaches",
        "model", "proposed method", "our method",
        "materials and methods", "system design", "framework",
    ),
    "experiment": (
        "experiment", "experiments", "evaluation", "evaluations",
        "results", "results and analysis", "experimental setup",
        "experiments and results", "empirical study",
    ),
    "discussion": ("discussion", "analysis", "ablation", "ablations"),
    "conclusion": ("conclusion", "conclusions", "concluding remarks", "summary and future work"),
    "limitations": ("limitations", "limitation", "threats to validity"),
}

# 参考文献 / 致谢 / 附录之后通常都是噪声
_TAIL_MARKERS = (
    "references", "bibliography", "acknowledgements", "acknowledgments",
    "appendix", "appendices", "supplementary material",
)


@dataclass
class ProcessedText:
    sections: dict[str, str]
    full_text: str  # 清洗后的全文（去尾部噪声）
    estimated_tokens: int


def _build_section_pattern() -> re.Pattern[str]:
    """构造一个能识别『可能是章节标题的一行』的正则。"""
    all_words = sorted(
        {w for words in SECTION_ALIASES.values() for w in words},
        key=len, reverse=True,
    )
    escaped = [re.escape(w) for w in all_words]
    # 行首可选编号（数字 / 罗马 / 字母 + . 或空格），然后是同义词，行末可有冒号或空白
    pattern = (
        r"^[ \t]*(?:\d+(?:\.\d+)*[.)\s]+|[IVX]+[.)\s]+|[A-Z][.)\s]+)?"
        r"(" + "|".join(escaped) + r")[ \t:.\-—]*$"
    )
    return re.compile(pattern, re.IGNORECASE | re.MULTILINE)


_SECTION_RE = _build_section_pattern()


def _strip_tail(text: str) -> str:
    """砍掉 References / Appendix 之后的内容。"""
    lower = text.lower()
    cut = len(text)
    for marker in _TAIL_MARKERS:
        # 只匹配独占一行（前后是换行）的 marker，避免误删正文里出现的同名词
        for m in re.finditer(rf"(^|\n)\s*{re.escape(marker)}\s*\n", lower):
            cut = min(cut, m.start())
            break
    return text[:cut].rstrip()


def _normalize_whitespace(text: str) -> str:
    # 把 PDF 抽出来的「单词-\n换行续行」拼回去
    text = re.sub(r"-\n(\w)", r"\1", text)
    # 单个换行视为软换行 → 空格；连续两个以上保留为段落分隔
    text = re.sub(r"\n{2,}", "\n\n", text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _alias_to_logical(alias: str) -> str | None:
    alias_low = alias.lower().strip()
    for logical, words in SECTION_ALIASES.items():
        if alias_low in words:
            return logical
    return None


def _split_sections(text: str) -> dict[str, str]:
    """按章节标题切分，同名逻辑章节累加。"""
    matches = list(_SECTION_RE.finditer(text))
    if not matches:
        return {}

    sections: dict[str, list[str]] = {}
    for i, m in enumerate(matches):
        logical = _alias_to_logical(m.group(1))
        if logical is None:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.setdefault(logical, []).append(body)

    return {k: "\n\n".join(v) for k, v in sections.items()}


def _estimate_tokens(text: str) -> int:
    """粗略估算 token：中文按字符数，英文按 4 字符/token。"""
    cn = sum(1 for ch in text if "一" <= ch <= "鿿")
    other = len(text) - cn
    return int(cn * 1.5 + other / 4)


def process(raw_text: str) -> ProcessedText:
    """主入口：清洗 + 切章。

    顺序很重要：先切章（依赖换行作为分隔），再对每段归一化空白。
    """
    stripped = _strip_tail(raw_text)
    # 先做最轻的清洗：拼回断词，统一空白行
    pre = re.sub(r"-\n(\w)", r"\1", stripped)
    pre = re.sub(r"[ \t]+\n", "\n", pre)
    pre = re.sub(r"\n{3,}", "\n\n", pre)

    raw_sections = _split_sections(pre)
    sections = {k: _normalize_whitespace(v) for k, v in raw_sections.items()}

    full_text = _normalize_whitespace(pre)

    # 兜底：切不出章节但全文较短，把全文当 abstract
    if not sections and len(full_text) < 4000:
        sections = {"abstract": full_text}

    return ProcessedText(
        sections=sections,
        full_text=full_text,
        estimated_tokens=_estimate_tokens(full_text),
    )


def make_two_stage_chunks(p: ProcessedText) -> tuple[str, str]:
    """切成「前半 / 后半」两块供两阶段 LLM 调用。

    前半 = abstract + intro + related_work（理解问题与动机）
    后半 = method + experiment + discussion + conclusion + limitations
    切不出章节时按字符长度对半切。
    """
    front_keys = ("abstract", "intro", "related_work")
    back_keys = ("method", "experiment", "discussion", "conclusion", "limitations")

    def _join(keys: tuple[str, ...]) -> str:
        return "\n\n".join(
            f"## {k}\n{p.sections[k]}" for k in keys if k in p.sections
        ).strip()

    front, back = _join(front_keys), _join(back_keys)

    if not front and not back:
        mid = len(p.full_text) // 2
        return p.full_text[:mid], p.full_text[mid:]
    if not front:
        return back[: len(back) // 2], back[len(back) // 2 :]
    if not back:
        return front, ""
    return front, back
