"""DeepSeek 调用层。

设计：
- 模版字段从 template.md 用正则提取（{{field_name}}），所有字段都视为必填。
- 两阶段调用：前半（理解问题）→ 拿到 partial JSON；后半（理解方法/结果）→ 拿到剩余字段。
- 合并时后阶段覆盖前阶段的同名字段（method/experiment 类字段通常在后半才被填实）。
- response_format 强制 JSON，失败时由 validator 触发 retry，retry prompt 会指出缺失字段。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from config import Config

_FIELD_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

# 给 LLM 看的字段含义提示。模版里没有的字段不会出现在 prompt 里。
FIELD_HINTS: dict[str, str] = {
    "title": "论文标题（原文，不翻译）",
    "authors": "作者列表，用逗号分隔",
    "year": "发表年份（仅 4 位数字）",
    "venue": "发表来源/期刊/会议名，未知填 'Unknown'",
    "url": "论文链接（arXiv / DOI / 官网），未知填空字符串",
    "research_question": "本文要解决的核心研究问题（一两句话）",
    "motivation": "为什么这个问题重要、现有方法的不足",
    "method": "核心方法的简要描述，包含关键技术点",
    "contributions": "主要贡献，用列表形式（- xxx\\n- xxx）",
    "experiments": "实验设置 + 主要结果数字",
    "datasets": "使用的数据集名称及规模，逗号分隔",
    "limitations": "作者自述或可见的局限性 / 未来工作",
    "personal_notes": "留空（个人评价由用户后续手写）",
    "conclusions": "主要结论，一两句话",
}


def extract_template_fields(template_path: Path) -> list[str]:
    text = template_path.read_text(encoding="utf-8")
    seen: list[str] = []
    for m in _FIELD_RE.finditer(text):
        name = m.group(1)
        if name not in seen:
            seen.append(name)
    return seen


def _build_system_prompt(fields: list[str], known_metadata: dict[str, str]) -> str:
    field_lines = []
    for f in fields:
        hint = FIELD_HINTS.get(f, "请根据论文内容合理填写")
        field_lines.append(f"- `{f}`: {hint}")

    known_lines = (
        "\n已知的论文元数据（如果你抽取的字段缺失，请优先使用这些值）：\n"
        + "\n".join(f"- {k}: {v}" for k, v in known_metadata.items() if v)
        if known_metadata
        else ""
    )

    return (
        "你是一个学术论文阅读助手。请阅读用户提供的论文片段，"
        "从中抽取信息并以 JSON 形式返回。\n\n"
        "返回的 JSON 必须满足：\n"
        "1. 顶层是一个对象，key 必须是下列字段名之一，多余字段会被忽略；\n"
        "2. 所有字段的值都是字符串；\n"
        "3. 当本片段不包含某字段信息时，将其值设为空字符串，不要编造；\n"
        "4. 不要输出任何 JSON 之外的解释文字。\n\n"
        "字段定义：\n"
        + "\n".join(field_lines)
        + known_lines
    )


def _build_user_prompt(stage_label: str, paper_chunk: str) -> str:
    return (
        f"以下是论文的【{stage_label}】部分：\n\n"
        f"```\n{paper_chunk}\n```\n\n"
        "请按 system 中描述的 JSON schema 返回这一阶段你能确定的字段。"
    )


class LLMClient:
    def __init__(self, cfg: Config):
        self._client = OpenAI(api_key=cfg.deepseek_api_key, base_url=cfg.deepseek_base_url)
        self._model = cfg.deepseek_model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        reraise=True,
    )
    def _call_json(self, system: str, user: str) -> dict[str, str]:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError(f"LLM 未返回 JSON object，得到: {type(data).__name__}")
        # 只保留字符串值，去掉嵌套结构
        return {k: ("" if v is None else str(v)) for k, v in data.items()}

    def fill_template(
        self,
        fields: list[str],
        front_chunk: str,
        back_chunk: str,
        known_metadata: dict[str, str] | None = None,
        missing_fields: list[str] | None = None,
    ) -> dict[str, str]:
        """两阶段调用并合并结果。

        missing_fields 非空表示在做 retry：会附加一段指令告诉 LLM 重点补这些字段。
        """
        known = known_metadata or {}
        system = _build_system_prompt(fields, known)

        retry_hint = ""
        if missing_fields:
            retry_hint = (
                "\n\n注意：上一轮以下字段未能填写，请这次重点关注："
                + ", ".join(f"`{f}`" for f in missing_fields)
            )

        merged: dict[str, str] = {}

        if front_chunk:
            front_resp = self._call_json(
                system,
                _build_user_prompt("Abstract + Introduction + Related Work", front_chunk)
                + retry_hint,
            )
            merged.update({k: v for k, v in front_resp.items() if v})

        if back_chunk:
            back_resp = self._call_json(
                system,
                _build_user_prompt("Method + Experiments + Conclusion", back_chunk)
                + retry_hint,
            )
            # 后阶段优先覆盖：method/experiments 在这里才被填实
            for k, v in back_resp.items():
                if v:
                    merged[k] = v

        # 已知元数据作为兜底（仅在 LLM 没填时使用）
        for k, v in known.items():
            if v and not merged.get(k):
                merged[k] = v

        # 保证所有目标字段都存在 key（即使是空串）
        for f in fields:
            merged.setdefault(f, "")

        return merged
