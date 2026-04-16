"""OCR provider implementations for the OCR tool."""

from dataclasses import dataclass
import json
import logging
import re
import shutil
import signal
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from platformdirs import user_cache_dir

MARKER_CMD = "marker_single"
OLLAMA_CMD = "ollama"
PDFTOPPM_CMD = "pdftoppm"
MIN_ACCEPTABLE_TEXT_LENGTH = 20
DEFAULT_MARKER_CACHE_DIR = Path(user_cache_dir("datalab")) / "models"
REQUIRED_CHECKPOINT_SETTING_NAMES = [
    "RECOGNITION_MODEL_CHECKPOINT",
    "DETECTOR_MODEL_CHECKPOINT",
    "LAYOUT_MODEL_CHECKPOINT",
    "TABLE_REC_MODEL_CHECKPOINT",
    "OCR_ERROR_MODEL_CHECKPOINT",
]
ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
ANSI_ESCAPE_RE_ALT = re.compile(r"\x1B\][^\x07]*(?:\x07|\x1B\\)")
DEEPSEEK_TAG_RE = re.compile(r"<\|/?(?:ref|det)\|>")
DEEPSEEK_DET_BLOCK_RE = re.compile(r"<\|det\|>\[\[[^\]]+\]\]<\|/det\|>")
DEEPSEEK_LABEL_LINES = {
    "text",
    "title",
    "section_header",
    "sub_title",
    "caption",
    "footnote",
    "formula",
    "list_item",
    "table",
}


@dataclass
class PageOCRResult:
    text: str
    final_provider: str
    fallback_used: bool
    attempts: list[dict]


class PageOCRFailure(RuntimeError):
    def __init__(self, message: str, attempts: list[dict]):
        super().__init__(message)
        self.attempts = attempts


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


def validate_environment() -> None:
    _require_command(MARKER_CMD, "marker_single not found. Install marker-pdf and ensure CLI is on PATH.")


def inspect_marker_cache() -> dict[str, Any]:
    cache_root = Path(
        os.environ.get("MODEL_CACHE_DIR", str(DEFAULT_MARKER_CACHE_DIR))
    ).expanduser().resolve()

    checkpoints = _required_marker_checkpoints()
    models: list[dict[str, Any]] = []

    for checkpoint in checkpoints:
        relative_path = checkpoint.replace("s3://", "", 1)
        model_dir = cache_root / Path(relative_path)
        manifest_path = model_dir / "manifest.json"

        status = "missing"
        missing_files: list[str] = []
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                missing_files = [
                    file_name
                    for file_name in manifest.get("files", [])
                    if not (model_dir / file_name).exists()
                ]
                status = "complete" if not missing_files else "incomplete"
            except Exception:
                status = "incomplete"
        models.append(
            {
                "checkpoint": relative_path,
                "path": str(model_dir),
                "status": status,
                "missing_files": missing_files,
            }
        )

    return {
        "cache_root": str(cache_root),
        "complete": all(model["status"] == "complete" for model in models),
        "models": models,
    }


def run_ocr_for_page(
    pdf_path: Path,
    page_number: int,
    total_pages: int,
    logger: logging.Logger,
    ollama_model: str,
    force_ollama_fallback: bool = False,
) -> PageOCRResult:
    attempts: list[dict] = []

    if not force_ollama_fallback:
        try:
            marker_text = _run_marker_for_page(pdf_path, page_number, total_pages, logger)
            _validate_text_quality(marker_text, "marker")
            attempts.append(_attempt_record("marker", "ok", len(marker_text)))
            return PageOCRResult(
                text=marker_text,
                final_provider="marker",
                fallback_used=False,
                attempts=attempts,
            )
        except Exception as exc:
            attempts.append(_attempt_record("marker", "failed", 0, str(exc)))
            _log_provider_event(
                logger,
                logging.WARNING,
                page_number,
                total_pages,
                "fallback",
                f"Marker failed for page {page_number}; trying Ollama fallback: {exc}",
            )
    else:
        attempts.append(_attempt_record("marker", "skipped", 0, "forced_ollama_fallback"))
        _log_provider_event(
            logger,
            logging.INFO,
            page_number,
            total_pages,
            "fallback",
            f"Marker skipped for page {page_number}; using forced Ollama fallback.",
        )

    try:
        _require_command(OLLAMA_CMD, "ollama not found. Install Ollama and ensure it is on PATH.")
        _require_command(PDFTOPPM_CMD, "pdftoppm not found. Install Poppler and ensure it is on PATH.")
        ollama_text = _run_ollama_for_page(pdf_path, page_number, total_pages, logger, ollama_model)
        _validate_text_quality(ollama_text, "ollama")
        attempts.append(_attempt_record("ollama", "ok", len(ollama_text)))
        return PageOCRResult(
            text=ollama_text,
            final_provider="ollama",
            fallback_used=True,
            attempts=attempts,
        )
    except Exception as exc:
        attempts.append(_attempt_record("ollama", "failed", 0, str(exc)))
        raise PageOCRFailure(f"Marker and Ollama both failed for page {page_number}.", attempts) from exc


def _attempt_record(provider: str, status: str, characters: int, error: str | None = None) -> dict:
    record = {
        "provider": provider,
        "status": status,
        "characters": characters,
    }
    if error:
        record["error"] = error
    return record


def _require_command(command: str, message: str) -> None:
    if shutil.which(command) is None:
        raise RuntimeError(message)


def _required_marker_checkpoints() -> list[str]:
    try:
        from surya.settings import settings as surya_settings  # type: ignore

        checkpoints = []
        for name in REQUIRED_CHECKPOINT_SETTING_NAMES:
            checkpoint = getattr(surya_settings, name, None)
            if isinstance(checkpoint, str) and checkpoint.startswith("s3://"):
                checkpoints.append(checkpoint)
        if checkpoints:
            return checkpoints
    except Exception:
        pass

    return [
        "s3://text_recognition/2025_09_23",
        "s3://text_detection/2025_05_07",
        "s3://layout/2025_09_23",
        "s3://table_recognition/2025_02_18",
        "s3://ocr_error_detection/2025_02_18",
    ]


def _validate_text_quality(text: str, provider: str) -> None:
    stripped = text.strip()
    if not stripped:
        raise RuntimeError(f"{provider} produced empty OCR output")
    if len(stripped) < MIN_ACCEPTABLE_TEXT_LENGTH:
        raise RuntimeError(
            f"{provider} OCR output below minimum acceptable length "
            f"({len(stripped)} < {MIN_ACCEPTABLE_TEXT_LENGTH}). output={_snippet(stripped)!r}"
        )


def _log_provider_event(
    logger: logging.Logger,
    level: int,
    page_number: int,
    total_pages: int,
    status: str,
    message: str,
) -> None:
    logger.log(
        level,
        message,
        extra={
            "page": page_number,
            "total_pages": total_pages,
            "duration_seconds": None,
            "characters": None,
            "status": status,
        },
    )


def _stream_subprocess(
    cmd: list[str],
    logger: logging.Logger,
    page_number: int,
    total_pages: int,
    status: str,
    prefix: str,
) -> int:
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    assert process.stdout is not None

    try:
        for line in process.stdout:
            line = line.rstrip()
            if line:
                _log_provider_event(
                    logger,
                    logging.INFO,
                    page_number,
                    total_pages,
                    status,
                    f"[{prefix}] {line}",
                )
    except KeyboardInterrupt:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        raise

    return process.wait()


def _run_marker_for_page(
    pdf_path: Path,
    page_number: int,
    total_pages: int,
    logger: logging.Logger,
) -> str:
    page_index = page_number - 1

    with tempfile.TemporaryDirectory(prefix="ocr_marker_") as temp_dir_str:
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

        exit_code = _stream_subprocess(cmd, logger, page_number, total_pages, "marker", "marker")
        if exit_code != 0:
            raise RuntimeError(f"marker_single exited with code {exit_code}")

        markdown_files = sorted(temp_dir.rglob("*.md"), key=lambda path: len(str(path)))
        if not markdown_files:
            raise RuntimeError("marker_single produced no markdown output")

        content = markdown_files[0].read_text(encoding="utf-8").strip()
        if not content:
            raise RuntimeError("marker_single produced empty markdown output")

        return content


def _run_ollama_for_page(
    pdf_path: Path,
    page_number: int,
    total_pages: int,
    logger: logging.Logger,
    ollama_model: str,
) -> str:
    with tempfile.TemporaryDirectory(prefix="ocr_ollama_") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        page_prefix = temp_dir / f"page-{page_number}"
        image_path = page_prefix.with_suffix(".png")

        render_cmd = [
            PDFTOPPM_CMD,
            "-f",
            str(page_number),
            "-l",
            str(page_number),
            "-singlefile",
            "-png",
            str(pdf_path),
            str(page_prefix),
        ]

        render_exit_code = _stream_subprocess(
            render_cmd,
            logger,
            page_number,
            total_pages,
            "render",
            "pdftoppm",
        )
        if render_exit_code != 0:
            raise RuntimeError(f"pdftoppm exited with code {render_exit_code}")
        if not image_path.exists():
            raise RuntimeError(f"pdftoppm did not create the expected page image: {image_path.name}")

        prompt = f"{image_path}\n<|grounding|>Convert the document to markdown."
        ocr_cmd = [OLLAMA_CMD, "run", ollama_model, "--hidethinking", prompt]

        _log_provider_event(
            logger,
            logging.INFO,
            page_number,
            total_pages,
            "ollama",
            f"[ollama] Running model {ollama_model}",
        )

        result = subprocess.run(
            ocr_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        stderr_text = (result.stderr or "").strip()
        cleaned_stderr = _clean_console_output(stderr_text)
        if cleaned_stderr:
            _log_provider_event(
                logger,
                logging.INFO,
                page_number,
                total_pages,
                "ollama",
                f"[ollama] {cleaned_stderr}",
            )

        if result.returncode != 0:
            stdout_text = (result.stdout or "").strip()
            raise RuntimeError(
                f"ollama run exited with code {result.returncode}. "
                f"stdout={_snippet(stdout_text)!r} stderr={_snippet(stderr_text)!r}"
            )

        content = _normalize_ollama_output((result.stdout or "").strip())
        if not content:
            raise RuntimeError("ollama returned empty OCR output")

        return content


def _snippet(text: str, limit: int = 200) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _clean_console_output(text: str) -> str:
    if not text:
        return ""

    text = ANSI_ESCAPE_RE_ALT.sub("", text)
    text = ANSI_ESCAPE_RE.sub("", text)
    text = text.replace("\r", "\n")

    cleaned_lines = []
    for raw_line in text.splitlines():
        line = "".join(ch for ch in raw_line if ch.isprintable() and ord(ch) < 128).strip()
        if line:
            cleaned_lines.append(line)

    if not cleaned_lines:
        return ""

    return _snippet(" | ".join(cleaned_lines), limit=300)


def _normalize_ollama_output(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    text = DEEPSEEK_DET_BLOCK_RE.sub("", text)
    text = DEEPSEEK_TAG_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    cleaned_lines = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.strip().lower() in DEEPSEEK_LABEL_LINES:
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()
