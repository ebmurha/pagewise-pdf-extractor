#!/usr/bin/env python3
"""Resumable PDF OCR pipeline with Marker primary and Ollama fallback."""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ocr_providers import (
    PageOCRFailure,
    get_total_pages,
    inspect_marker_cache,
    run_ocr_for_page,
    validate_environment,
)


OUTPUT_ROOT = Path("output")
LOW_TEXT_THRESHOLD = 50
PAGE_FILENAME_TEMPLATE = "page_{page:04d}.md"
LOG_FILE_NAME = "run.log"
PROGRESS_FILE_NAME = "progress.json"
FAILURE_PLACEHOLDER = "OCR FAILED"
PIPELINE_MODE = "marker_with_ollama_fallback"
DOTENV_PATH = Path(".env")


def setup_logger(output_dir: Path) -> logging.Logger:
    """Create a logger that writes to terminal and a persistent log file."""
    logger = logging.getLogger("ocr_tool")
    logger.setLevel(logging.INFO)
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)
    logger.propagate = False

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

    log_path = output_dir / LOG_FILE_NAME
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)

    try:
        from pythonjsonlogger import jsonlogger  # type: ignore

        file_handler.setFormatter(
            jsonlogger.JsonFormatter(
                "%(asctime)s %(levelname)s %(message)s %(page)s %(total_pages)s "
                "%(duration_seconds)s %(characters)s %(status)s"
            )
        )
    except Exception:
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(message)s "
                "page=%(page)s total_pages=%(total_pages)s "
                "duration_seconds=%(duration_seconds)s characters=%(characters)s "
                "status=%(status)s"
            )
        )

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    return logger


def close_logger(logger: logging.Logger) -> None:
    for handler in logger.handlers[:]:
        handler.flush()
        handler.close()
        logger.removeHandler(handler)


def log_event(logger: logging.Logger, level: str, message: str, **extra: Any) -> None:
    defaults = {
        "page": None,
        "total_pages": None,
        "duration_seconds": None,
        "characters": None,
        "status": None,
    }
    defaults.update(extra)
    getattr(logger, level)(message, extra=defaults)


def compute_sha256(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as file_obj:
        while True:
            chunk = file_obj.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def configure_model_cache(logger: logging.Logger) -> Optional[str]:
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(dotenv_path=DOTENV_PATH, override=False)
    except Exception:
        pass

    cache_dir = os.environ.get("MODEL_CACHE_DIR", "").strip()
    if not cache_dir:
        log_event(
            logger,
            "info",
            "MODEL_CACHE_DIR not set; using Marker default cache location.",
            status="config",
        )
        return None

    resolved = Path(cache_dir).expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    os.environ["MODEL_CACHE_DIR"] = str(resolved)
    log_event(
        logger,
        "info",
        f"Using Marker model cache: {resolved}",
        status="config",
    )
    return str(resolved)


def log_marker_cache_status(logger: logging.Logger) -> None:
    cache_info = inspect_marker_cache()
    cache_root = cache_info["cache_root"]

    if cache_info["complete"]:
        log_event(
            logger,
            "info",
            f"Marker cache ready: {cache_root}",
            status="config",
        )
        return

    missing = [model["checkpoint"] for model in cache_info["models"] if model["status"] != "complete"]
    log_event(
        logger,
        "info",
        "Marker cache incomplete; Marker may download missing models during the first OCR page run.",
        status="config",
    )
    log_event(
        logger,
        "info",
        f"Missing Marker models: {', '.join(missing)}",
        status="config",
    )


def load_progress(progress_path: Path) -> Optional[Dict[str, Any]]:
    if not progress_path.exists():
        return None
    with progress_path.open("r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def save_progress(progress_path: Path, progress: Dict[str, Any]) -> None:
    progress["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp_path = progress_path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as file_obj:
        json.dump(progress, file_obj, indent=2)
    tmp_path.replace(progress_path)


def initialize_progress(
    input_pdf: Path,
    total_pages: int,
    progress_path: Path,
    logger: logging.Logger,
    ollama_model: str,
    force_ollama_fallback: bool,
) -> Tuple[Dict[str, Any], int]:
    input_sha256 = compute_sha256(input_pdf)
    existing = load_progress(progress_path)

    baseline = {
        "input_file": str(input_pdf.resolve()),
        "input_file_name": input_pdf.name,
        "input_sha256": input_sha256,
        "total_pages": total_pages,
        "last_completed_page": 0,
        "failed_pages": [],
        "pages": {},
        "pipeline": PIPELINE_MODE,
        "ollama_model": ollama_model,
        "force_ollama_fallback": force_ollama_fallback,
    }

    if not existing:
        save_progress(progress_path, baseline)
        return baseline, 1

    matches_file = existing.get("input_file") == str(input_pdf.resolve())
    matches_checksum = existing.get("input_sha256") == input_sha256
    matches_pages = existing.get("total_pages") == total_pages
    matches_pipeline = existing.get("pipeline") == PIPELINE_MODE
    matches_model = existing.get("ollama_model") == ollama_model
    matches_force_fallback = existing.get("force_ollama_fallback", False) == force_ollama_fallback

    if matches_file and matches_checksum and matches_pages and matches_pipeline and matches_model and matches_force_fallback:
        start_page = int(existing.get("last_completed_page", 0)) + 1
        return existing, start_page

    log_event(
        logger,
        "warning",
        "Progress file does not match input or OCR pipeline; restarting from page 1.",
        status="progress_reset",
    )
    save_progress(progress_path, baseline)
    return baseline, 1


def write_page_markdown(output_dir: Path, page_number: int, content: str) -> Path:
    page_path = output_dir / PAGE_FILENAME_TEMPLATE.format(page=page_number)
    body = f"# Page {page_number}\n\n{content.strip()}\n"
    page_path.write_text(body, encoding="utf-8")
    return page_path


def write_failure_markdown(output_dir: Path, page_number: int, error_message: str) -> Path:
    page_path = output_dir / PAGE_FILENAME_TEMPLATE.format(page=page_number)
    body = (
        f"# Page {page_number}\n\n"
        f"{FAILURE_PLACEHOLDER}\n\n"
        f"Error: {error_message}\n"
    )
    page_path.write_text(body, encoding="utf-8")
    return page_path


def process_pdf(input_pdf: Path, ollama_model: str, force_ollama_fallback: bool = False) -> int:
    if not input_pdf.exists() or not input_pdf.is_file():
        print(f"Input PDF not found: {input_pdf}", file=sys.stderr)
        return 2
    if input_pdf.suffix.lower() != ".pdf":
        print(f"Input file is not a PDF: {input_pdf}", file=sys.stderr)
        return 2

    output_dir = OUTPUT_ROOT / input_pdf.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logger(output_dir)
    progress_path = output_dir / PROGRESS_FILE_NAME

    try:
        configure_model_cache(logger)
        log_marker_cache_status(logger)
        try:
            validate_environment()
            total_pages = get_total_pages(input_pdf)
        except Exception as exc:
            log_event(logger, "error", f"Startup validation failed: {exc}", status="fatal")
            return 1

        progress, start_page = initialize_progress(
            input_pdf,
            total_pages,
            progress_path,
            logger,
            ollama_model,
            force_ollama_fallback,
        )

        log_event(logger, "info", f"PDF file: {input_pdf.name}", total_pages=total_pages, status="start")
        log_event(logger, "info", f"Pipeline: {PIPELINE_MODE}", total_pages=total_pages, status="start")
        log_event(logger, "info", f"Ollama model: {ollama_model}", total_pages=total_pages, status="start")
        if force_ollama_fallback:
            log_event(logger, "info", "Forced Ollama fallback enabled.", total_pages=total_pages, status="start")
        log_event(logger, "info", f"Total pages: {total_pages}", total_pages=total_pages, status="start")

        if start_page > total_pages:
            log_event(logger, "info", "All pages already processed.", total_pages=total_pages, status="done")
            return 0

        try:
            from tqdm import tqdm  # type: ignore

            page_iter = tqdm(
                range(start_page, total_pages + 1),
                initial=max(0, start_page - 1),
                total=total_pages,
                desc="OCR",
            )
        except Exception:
            page_iter = range(start_page, total_pages + 1)

        for page_number in page_iter:
            start_time = time.perf_counter()
            log_event(
                logger,
                "info",
                f"Processing page {page_number}/{total_pages}",
                page=page_number,
                total_pages=total_pages,
                status="processing",
            )

            try:
                result = run_ocr_for_page(
                    input_pdf,
                    page_number,
                    total_pages,
                    logger,
                    ollama_model,
                    force_ollama_fallback=force_ollama_fallback,
                )
                text = result.text
                char_count = len(text)
                duration = round(time.perf_counter() - start_time, 3)

                status = "ok"
                if result.fallback_used:
                    status = "fallback_ok"
                if char_count < LOW_TEXT_THRESHOLD:
                    status = "low_text_warning"
                    log_event(
                        logger,
                        "warning",
                        f"Page {page_number} low text detected ({char_count} chars)",
                        page=page_number,
                        total_pages=total_pages,
                        duration_seconds=duration,
                        characters=char_count,
                        status=status,
                    )

                write_page_markdown(output_dir, page_number, text)
                progress["last_completed_page"] = page_number
                progress.setdefault("failed_pages", [])
                progress.setdefault("pages", {})
                if page_number in progress["failed_pages"]:
                    progress["failed_pages"].remove(page_number)
                progress["pages"][str(page_number)] = {
                    "status": status,
                    "characters": char_count,
                    "duration_seconds": duration,
                    "output_file": PAGE_FILENAME_TEMPLATE.format(page=page_number),
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                    "final_provider": result.final_provider,
                    "fallback_used": result.fallback_used,
                    "attempts": result.attempts,
                }
                save_progress(progress_path, progress)

                log_event(
                    logger,
                    "info",
                    f"OCR completed for page {page_number} in {duration:.2f}s using {result.final_provider}",
                    page=page_number,
                    total_pages=total_pages,
                    duration_seconds=duration,
                    characters=char_count,
                    status=status,
                )
            except KeyboardInterrupt:
                save_progress(progress_path, progress)
                log_event(
                    logger,
                    "warning",
                    "Interrupted by user; progress saved.",
                    page=page_number,
                    total_pages=total_pages,
                    status="interrupted",
                )
                return 130
            except PageOCRFailure as exc:
                duration = round(time.perf_counter() - start_time, 3)
                write_failure_markdown(output_dir, page_number, str(exc))
                progress["last_completed_page"] = page_number
                progress.setdefault("failed_pages", [])
                progress.setdefault("pages", {})
                if page_number not in progress["failed_pages"]:
                    progress["failed_pages"].append(page_number)
                progress["pages"][str(page_number)] = {
                    "status": "failed",
                    "characters": 0,
                    "duration_seconds": duration,
                    "output_file": PAGE_FILENAME_TEMPLATE.format(page=page_number),
                    "error": str(exc),
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                    "final_provider": None,
                    "fallback_used": True,
                    "attempts": exc.attempts,
                }
                save_progress(progress_path, progress)

                log_event(
                    logger,
                    "error",
                    f"Page {page_number} OCR failed: {exc}",
                    page=page_number,
                    total_pages=total_pages,
                    duration_seconds=duration,
                    characters=0,
                    status="failed",
                )

        log_event(logger, "info", "Processing complete.", total_pages=total_pages, status="done")
        return 0
    finally:
        close_logger(logger)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run local OCR on a PDF file and output page-wise markdown files."
    )
    parser.add_argument("input_pdf", help="Path to the source PDF file")
    parser.add_argument(
        "--ollama-model",
        default="deepseek-ocr",
        help="Ollama model name used for fallback OCR",
    )
    parser.add_argument(
        "--force-ollama-fallback",
        action="store_true",
        help="Skip Marker and send every page directly to the Ollama fallback path",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    input_pdf = Path(args.input_pdf).expanduser().resolve()
    return process_pdf(input_pdf, args.ollama_model, force_ollama_fallback=args.force_ollama_fallback)


if __name__ == "__main__":
    raise SystemExit(main())
