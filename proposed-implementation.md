EB — yes. And for **your actual goal** (Markdown output with better handling of columns/tables), I’d use **Marker**, not raw Surya calls. Marker’s official CLI supports **per-page processing via `--page_range`**, **Markdown output**, **`--force_ocr`**, and **debug logging**, and it uses **Surya by default for OCR**. That makes the script smaller, more observable, and less janky than hand-stitching OCR/layout/table outputs yourself. ([PyPI][1])

Here is a **single-file script** that implements the end-to-end workflow:

```python
#!/usr/bin/env python3
"""
Book OCR CLI

Processes a PDF book page-by-page using Marker (which uses Surya by default),
writes one Markdown file per page, logs everything to terminal + file, supports
resume via progress.json, and never fails silently.

Usage:
    python ocr_book.py /path/to/book.pdf
"""

from __future__ import annotations

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
from pathlib import Path
from typing import Any

from pdf2image import pdfinfo_from_path
from tqdm import tqdm

OUTPUT_ROOT = Path("output")
PROGRESS_FILE = "progress.json"
LOG_FILE = "run.log"
LOW_TEXT_THRESHOLD = 80
MARKER_CMD = "marker_single"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OCR a PDF book into per-page markdown files.")
    parser.add_argument("input_path", help="Path to the input PDF file")
    parser.add_argument("--force-ocr", action="store_true", default=True, help="Force OCR on all pages")
    parser.add_argument("--debug", action="store_true", help="Enable marker debug mode")
    return parser.parse_args()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def get_total_pages(pdf_path: Path) -> int:
    info = pdfinfo_from_path(str(pdf_path))
    pages = info.get("Pages")
    if not isinstance(pages, int) or pages <= 0:
        raise RuntimeError(f"Could not determine page count for {pdf_path}")
    return pages


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def setup_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("book_ocr")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False
    return logger


def load_progress(progress_path: Path) -> dict[str, Any]:
    if not progress_path.exists():
        return {}
    with progress_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_progress(progress_path: Path, data: dict[str, Any]) -> None:
    tmp_path = progress_path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp_path.replace(progress_path)


def init_progress(pdf_path: Path, total_pages: int, output_dir: Path) -> dict[str, Any]:
    progress_path = output_dir / PROGRESS_FILE
    file_hash = sha256_file(pdf_path)
    existing = load_progress(progress_path)

    if existing:
        if existing.get("input_path") != str(pdf_path.resolve()):
            raise RuntimeError("Existing progress.json belongs to a different input path.")
        if existing.get("input_sha256") != file_hash:
            raise RuntimeError("Existing progress.json does not match the current PDF file.")
        if existing.get("total_pages") != total_pages:
            raise RuntimeError("Existing progress.json total_pages does not match current PDF.")
        return existing

    progress = {
        "input_path": str(pdf_path.resolve()),
        "input_sha256": file_hash,
        "total_pages": total_pages,
        "last_completed_page": 0,  # 1-based
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pages": {},
    }
    save_progress(progress_path, progress)
    return progress


def page_md_path(output_dir: Path, page_num: int) -> Path:
    return output_dir / f"page_{page_num:04d}.md"


def write_page_markdown(path: Path, page_num: int, content: str) -> None:
    text = f"# Page {page_num}\n\n{content.strip()}\n"
    path.write_text(text, encoding="utf-8")


def write_failure_markdown(path: Path, page_num: int, error_message: str) -> None:
    text = f"# Page {page_num}\n\nOCR FAILED\n\nError: {error_message.strip()}\n"
    path.write_text(text, encoding="utf-8")


def stream_subprocess(cmd: list[str], logger: logging.Logger) -> int:
    logger.info("Running command: %s", " ".join(cmd))
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
            logger.info("[marker] %s", line.rstrip())
    except KeyboardInterrupt:
        logger.warning("Keyboard interrupt received. Terminating child process.")
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        raise

    return process.wait()


def find_generated_markdown(temp_output_dir: Path) -> Path | None:
    md_files = list(temp_output_dir.rglob("*.md"))
    if not md_files:
        return None
    md_files.sort(key=lambda p: len(str(p)))
    return md_files[0]


def run_marker_for_page(
    pdf_path: Path,
    page_index_zero_based: int,
    debug: bool,
    force_ocr: bool,
    logger: logging.Logger,
) -> str:
    with tempfile.TemporaryDirectory(prefix="book_ocr_") as tmp:
        temp_dir = Path(tmp)

        cmd = [
            MARKER_CMD,
            str(pdf_path),
            "--output_format",
            "markdown",
            "--output_dir",
            str(temp_dir),
            "--page_range",
            str(page_index_zero_based),
            "--disable_image_extraction",
        ]

        if force_ocr:
            cmd.append("--force_ocr")
        if debug:
            cmd.append("--debug")

        rc = stream_subprocess(cmd, logger)
        if rc != 0:
            raise RuntimeError(f"marker_single exited with code {rc}")

        md_path = find_generated_markdown(temp_dir)
        if md_path is None or not md_path.exists():
            raise RuntimeError("marker_single completed but produced no markdown output")

        content = md_path.read_text(encoding="utf-8").strip()
        if not content:
            raise RuntimeError("marker_single produced an empty markdown file")

        return content


def validate_environment() -> None:
    if shutil.which(MARKER_CMD) is None:
        raise RuntimeError(
            "marker_single command not found. Install marker-pdf and ensure the CLI is on PATH."
        )


def main() -> int:
    args = parse_args()
    pdf_path = Path(args.input_path).expanduser().resolve()

    if not pdf_path.exists():
        print(f"ERROR: Input file does not exist: {pdf_path}", file=sys.stderr)
        return 1
    if pdf_path.suffix.lower() != ".pdf":
        print(f"ERROR: Input file is not a PDF: {pdf_path}", file=sys.stderr)
        return 1

    try:
        validate_environment()
        total_pages = get_total_pages(pdf_path)
    except Exception as exc:
        print(f"ERROR: Startup validation failed: {exc}", file=sys.stderr)
        return 1

    book_name = pdf_path.stem
    output_dir = OUTPUT_ROOT / book_name
    ensure_dir(output_dir)

    logger = setup_logger(output_dir / LOG_FILE)

    try:
        progress = init_progress(pdf_path, total_pages, output_dir)
    except Exception as exc:
        logger.error("Failed to initialize progress: %s", exc)
        return 1

    start_page = int(progress.get("last_completed_page", 0)) + 1

    logger.info("Input PDF: %s", pdf_path)
    logger.info("Book name: %s", book_name)
    logger.info("Total pages: %s", total_pages)
    logger.info("Resuming from page: %s", start_page)

    progress_bar = tqdm(range(start_page, total_pages + 1), desc="Pages", unit="page")

    try:
        for page_num in progress_bar:
            page_path = page_md_path(output_dir, page_num)
            page_start = time.perf_counter()

            logger.info("Processing page %s/%s", page_num, total_pages)

            try:
                markdown = run_marker_for_page(
                    pdf_path=pdf_path,
                    page_index_zero_based=page_num - 1,
                    debug=args.debug,
                    force_ocr=args.force_ocr,
                    logger=logger,
                )

                write_page_markdown(page_path, page_num, markdown)

                duration = round(time.perf_counter() - page_start, 3)
                char_count = len(markdown)

                status = "ok"
                if char_count < LOW_TEXT_THRESHOLD:
                    status = "low_text_warning"
                    logger.warning(
                        "Low text detected on page %s: chars=%s threshold=%s",
                        page_num,
                        char_count,
                        LOW_TEXT_THRESHOLD,
                    )

                progress["pages"][str(page_num)] = {
                    "status": status,
                    "chars": char_count,
                    "duration_seconds": duration,
                    "output_file": page_path.name,
                    "processed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }

                progress["last_completed_page"] = page_num
                progress["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                save_progress(output_dir / PROGRESS_FILE, progress)

                logger.info(
                    "Completed page %s/%s | status=%s | chars=%s | duration=%.3fs | output=%s",
                    page_num,
                    total_pages,
                    status,
                    char_count,
                    duration,
                    page_path,
                )

            except KeyboardInterrupt:
                logger.warning("Interrupted while processing page %s. Saving progress and exiting.", page_num)
                progress["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                save_progress(output_dir / PROGRESS_FILE, progress)
                return 130

            except Exception as exc:
                duration = round(time.perf_counter() - page_start, 3)
                error_message = str(exc)

                logger.error(
                    "Page %s failed | duration=%.3fs | error=%s",
                    page_num,
                    duration,
                    error_message,
                )

                write_failure_markdown(page_path, page_num, error_message)

                progress["pages"][str(page_num)] = {
                    "status": "failed",
                    "chars": 0,
                    "duration_seconds": duration,
                    "output_file": page_path.name,
                    "error": error_message,
                    "processed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                progress["last_completed_page"] = page_num
                progress["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                save_progress(output_dir / PROGRESS_FILE, progress)

                logger.info("Failure placeholder written for page %s: %s", page_num, page_path)
                continue

    except KeyboardInterrupt:
        logger.warning("Interrupted by user. Progress saved at page %s.", progress.get("last_completed_page", 0))
        progress["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_progress(output_dir / PROGRESS_FILE, progress)
        return 130

    logger.info("Run complete. Processed through page %s of %s.", progress.get("last_completed_page", 0), total_pages)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

## Recommended `requirements.txt`

Because this script shells out to Marker, I would use:

```txt
marker-pdf
pdf2image
tqdm
```

## Notes that matter

* This script is deliberately **simple and observable**, not clever.
* It writes a **failure placeholder page** instead of dying mysteriously.
* It resumes from the **last fully handled page**.
* It logs both the script’s own events and Marker’s stdout into `run.log`.
* It is better suited to **columns and tables** than a raw OCR-only script because Marker converts pages to **Markdown** and explicitly supports **formatted tables/forms/equations**. ([PyPI][1])

One important correction from earlier: Surya’s current code is GPL and its model weights have separate licensing terms, so if licensing is a business concern, check that before shipping this into a commercial product.

[1]: https://pypi.org/project/marker-pdf/ "marker-pdf · PyPI"
