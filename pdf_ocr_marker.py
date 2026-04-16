#!/usr/bin/env python3
"""Simple resumable PDF OCR pipeline using Marker CLI."""

# 1. imports
import argparse
import hashlib
import json
import logging
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


# 2. config constants
OUTPUT_ROOT = Path("output")
LOW_TEXT_THRESHOLD = 50
PAGE_FILENAME_TEMPLATE = "page_{page:04d}.md"
LOG_FILE_NAME = "run.log"
PROGRESS_FILE_NAME = "progress.json"
FAILURE_PLACEHOLDER = "OCR FAILED"
MARKER_CMD = "marker_single"


# 3. logging setup
def setup_logger(output_dir: Path) -> logging.Logger:
    """Create a logger that writes to terminal and a persistent log file."""
    logger = logging.getLogger("pdf_ocr_marker")
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
    """Log with stable metadata fields to avoid KeyError in formatters."""
    defaults = {
        "page": None,
        "total_pages": None,
        "duration_seconds": None,
        "characters": None,
        "status": None,
    }
    defaults.update(extra)
    getattr(logger, level)(message, extra=defaults)


# 4. progress management
def compute_sha256(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as file_obj:
        while True:
            chunk = file_obj.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


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
    }

    if not existing:
        save_progress(progress_path, baseline)
        return baseline, 1

    matches_file = existing.get("input_file") == str(input_pdf.resolve())
    matches_checksum = existing.get("input_sha256") == input_sha256
    matches_pages = existing.get("total_pages") == total_pages

    if matches_file and matches_checksum and matches_pages:
        start_page = int(existing.get("last_completed_page", 0)) + 1
        return existing, start_page

    log_event(
        logger,
        "warning",
        "Progress file does not match input; restarting from page 1.",
        status="progress_reset",
    )
    save_progress(progress_path, baseline)
    return baseline, 1


# 5. OCR functions
def validate_marker_cli() -> None:
    if shutil.which(MARKER_CMD) is None:
        raise RuntimeError(
            "marker_single not found. Install marker-pdf and ensure CLI is on PATH."
        )


def get_total_pages(pdf_path: Path) -> int:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:
        raise RuntimeError("pypdf is required to count PDF pages.") from exc

    try:
        reader = PdfReader(str(pdf_path))
        pages = len(reader.pages)
    except Exception as exc:
        raise RuntimeError(f"Unable to read PDF pages from {pdf_path}: {exc}") from exc

    if pages <= 0:
        raise RuntimeError(f"Unable to determine total pages for {pdf_path}")
    return pages


def stream_subprocess(cmd: list[str], logger: logging.Logger, page_number: int, total_pages: int) -> int:
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    assert process.stdout is not None

    try:
        for line in process.stdout:
            line = line.rstrip()
            if line:
                log_event(
                    logger,
                    "info",
                    f"[marker] {line}",
                    page=page_number,
                    total_pages=total_pages,
                    status="marker",
                )
    except KeyboardInterrupt:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        raise

    return process.wait()


def run_marker_for_page(
    pdf_path: Path,
    page_number: int,
    total_pages: int,
    logger: logging.Logger,
) -> str:
    page_index = page_number - 1

    with tempfile.TemporaryDirectory(prefix="pdf_ocr_marker_") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        cmd = [
            MARKER_CMD,
            str(pdf_path),
            "--output_format",
            "markdown",
            "--output_dir",
            str(temp_dir),
            "--page_range",
            str(page_index),
            "--force_ocr",
        ]

        exit_code = stream_subprocess(cmd, logger, page_number, total_pages)
        if exit_code != 0:
            raise RuntimeError(f"marker_single exited with code {exit_code}")

        markdown_files = sorted(temp_dir.rglob("*.md"), key=lambda path: len(str(path)))
        if not markdown_files:
            raise RuntimeError("marker_single produced no markdown output")

        content = markdown_files[0].read_text(encoding="utf-8").strip()
        if not content:
            raise RuntimeError("marker_single produced empty markdown output")

        return content


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


# 6. main processing loop
def process_pdf(input_pdf: Path, output_root: Path = OUTPUT_ROOT) -> int:
    if not input_pdf.exists() or not input_pdf.is_file():
        print(f"Input PDF not found: {input_pdf}", file=sys.stderr)
        return 2
    if input_pdf.suffix.lower() != ".pdf":
        print(f"Input file is not a PDF: {input_pdf}", file=sys.stderr)
        return 2

    output_dir = output_root / input_pdf.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logger(output_dir)
    progress_path = output_dir / PROGRESS_FILE_NAME

    try:
        try:
            validate_marker_cli()
            total_pages = get_total_pages(input_pdf)
        except Exception as exc:
            log_event(logger, "error", f"Startup validation failed: {exc}", status="fatal")
            return 1

        progress, start_page = initialize_progress(input_pdf, total_pages, progress_path, logger)

        log_event(
            logger,
            "info",
            f"PDF file: {input_pdf.name}",
            total_pages=total_pages,
            status="start",
        )
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
                text = run_marker_for_page(input_pdf, page_number, total_pages, logger)
                char_count = len(text)
                duration = round(time.perf_counter() - start_time, 3)

                status = "ok"
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
                }
                save_progress(progress_path, progress)

                log_event(
                    logger,
                    "info",
                    f"OCR completed for page {page_number} in {duration:.2f}s",
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
            except Exception as exc:
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


# 7. CLI entrypoint
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run local OCR on a PDF file and output page-wise markdown files."
    )
    parser.add_argument("input_pdf", help="Path to the source PDF file")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    input_pdf = Path(args.input_pdf).expanduser().resolve()
    return process_pdf(input_pdf)


if __name__ == "__main__":
    raise SystemExit(main())
