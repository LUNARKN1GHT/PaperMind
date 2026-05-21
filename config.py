"""全局配置：从 .env 读取，集中暴露给其他模块使用。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Config:
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str

    semantic_scholar_api_key: str | None
    unpaywall_email: str | None

    output_dir: Path
    template_path: Path
    cache_dir: Path

    max_retries: int
    max_input_tokens: int

    @classmethod
    def load(cls) -> "Config":
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not api_key or api_key.startswith("sk-your"):
            raise RuntimeError(
                "DEEPSEEK_API_KEY 未配置。请复制 .env.example 为 .env 并填写真实 key。"
            )

        output_dir = Path(os.getenv("OUTPUT_DIR", "./outputs")).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        cache_dir = (PROJECT_ROOT / ".cache").resolve()
        cache_dir.mkdir(parents=True, exist_ok=True)

        return cls(
            deepseek_api_key=api_key,
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            semantic_scholar_api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY") or None,
            unpaywall_email=os.getenv("UNPAYWALL_EMAIL") or None,
            output_dir=output_dir,
            template_path=PROJECT_ROOT / "template.md",
            cache_dir=cache_dir,
            max_retries=int(os.getenv("MAX_RETRIES", "2")),
            max_input_tokens=int(os.getenv("MAX_INPUT_TOKENS", "12000")),
        )
