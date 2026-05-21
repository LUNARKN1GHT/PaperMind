"""PaperMind 入口：串联 Router → Fetcher → Processor → LLM → Validator → Writer。

用法：
    python main.py --input "2401.12345"
    python main.py --input "./paper.pdf"
    python main.py --batch papers.txt
    python main.py --batch papers.txt --output ./notes/2024/
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from config import Config
from fetchers import FetchResult
from fetchers.pdf_parser import parse_pdf
from fetchers.search_agent import search_title
from fetchers.web_fetcher import fetch_arxiv, fetch_doi
from llm import LLMClient, extract_template_fields
from processor import make_two_stage_chunks, process
from router import InputSpec, route
from validator import validate
from writer import write_note

logger = logging.getLogger("papermind")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(threadName)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _fetch(spec: InputSpec, cfg: Config) -> FetchResult:
    cache_dir = cfg.pdf_cache_dir  # None 时即关闭缓存
    if spec.kind == "pdf":
        return parse_pdf(spec.identifier)
    if spec.kind == "arxiv":
        return fetch_arxiv(spec.identifier, cache_dir=cache_dir)
    if spec.kind == "doi":
        return fetch_doi(
            spec.identifier, email=cfg.unpaywall_email, cache_dir=cache_dir
        )
    if spec.kind == "title":
        return search_title(
            spec.identifier,
            api_key=cfg.semantic_scholar_api_key,
            cache_dir=cache_dir,
        )
    raise ValueError(f"未知的输入类型: {spec.kind}")


def process_one(raw_input: str, cfg: Config, llm: LLMClient, output_dir: Path) -> Path:
    """处理单篇论文。返回写入的笔记路径。"""
    logger.info("处理输入: %s", raw_input)
    spec = route(raw_input)
    logger.info("识别为 %s: %s", spec.kind, spec.identifier)

    fetched = _fetch(spec, cfg)
    logger.info("获取成功 (source=%s, %d chars)", fetched.source, len(fetched.raw_text))

    processed = process(fetched.raw_text)
    logger.info(
        "切分到 %d 个章节 (~%d tokens): %s",
        len(processed.sections),
        processed.estimated_tokens,
        list(processed.sections.keys()),
    )

    front, back = make_two_stage_chunks(processed)
    fields = extract_template_fields(cfg.template_path)

    filled = llm.fill_template(
        fields=fields,
        front_chunk=front,
        back_chunk=back,
        known_metadata=fetched.metadata,
    )

    # Retry：缺字段就再调一次，最多 cfg.max_retries 次
    for attempt in range(cfg.max_retries):
        ok, missing = validate(filled, fields)
        if ok:
            break
        logger.warning("字段不全, retry %d/%d: 缺 %s", attempt + 1, cfg.max_retries, missing)
        retry_filled = llm.fill_template(
            fields=fields,
            front_chunk=front,
            back_chunk=back,
            known_metadata=fetched.metadata,
            missing_fields=missing,
        )
        # 只用 retry 的结果补缺失字段，不覆盖原有内容
        for f in missing:
            if retry_filled.get(f, "").strip():
                filled[f] = retry_filled[f]
    else:
        ok, missing = validate(filled, fields)
        if not ok:
            logger.warning("retry 用尽，仍缺字段: %s（将以空串写入）", missing)

    out_path = write_note(filled, cfg.template_path, output_dir)
    logger.info("写入笔记: %s", out_path)
    return out_path


def _read_batch(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(description="PaperMind: 论文笔记自动化 Agent")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", help="单篇论文：PDF 路径 / arXiv id / DOI / 标题")
    src.add_argument("--batch", type=Path, help="批量文件，每行一个输入")
    parser.add_argument("--output", type=Path, help="输出目录（覆盖 .env 中的 OUTPUT_DIR）")
    parser.add_argument(
        "--workers", type=int, default=4,
        help="并发线程数（仅对 --batch 生效；过高会触发 API 限速，默认 4）",
    )
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers 必须 >= 1")

    cfg = Config.load()
    output_dir = (args.output or cfg.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    llm = LLMClient(cfg)

    inputs = [args.input] if args.input else _read_batch(args.batch)
    workers = 1 if args.input else max(1, min(args.workers, len(inputs)))
    logger.info(
        "待处理 %d 篇，并发 %d，输出目录: %s", len(inputs), workers, output_dir
    )

    error_log = output_dir / "errors.log"
    error_lock = threading.Lock()
    succeeded, failed = 0, 0

    def _work(idx: int, raw: str) -> tuple[str, bool, str]:
        # 给每个线程一个可读的名字，结合 %(threadName)s 让日志能区分论文
        threading.current_thread().name = f"paper-{idx:02d}"
        try:
            process_one(raw, cfg, llm, output_dir)
            return raw, True, ""
        except Exception as e:
            tb = traceback.format_exc()
            with error_lock, error_log.open("a", encoding="utf-8") as f:
                f.write(f"INPUT: {raw}\nERROR: {e}\n{tb}\n---\n")
            return raw, False, str(e)

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="paper") as pool:
        futures = [pool.submit(_work, i + 1, raw) for i, raw in enumerate(inputs)]
        for fut in as_completed(futures):
            raw, ok, err = fut.result()
            if ok:
                succeeded += 1
            else:
                failed += 1
                logger.error("处理失败 %r: %s", raw, err)

    logger.info("完成。成功 %d 篇，失败 %d 篇。", succeeded, failed)
    if failed:
        logger.info("失败详情见 %s", error_log)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
