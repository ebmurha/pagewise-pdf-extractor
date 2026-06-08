"""Marker OCR provider."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

from ..config import ExtractionConfig
from ..exceptions import ProviderError
from ..models import ProviderCapability, ProviderResult
from ..preprocessing import prepare_page_for_ocr
from .base import PageExtractor, clean_console_output, markdown_layout_artifacts, text_quality_status

MARKER_CMD = "marker_single"
PAGE_BREAK = "PAGEWISE_LOGICAL_PAGE_BREAK"


class MarkerOCRExtractor(PageExtractor):
    name = "marker"

    def validate(self, config: ExtractionConfig) -> ProviderCapability:
        missing = [] if shutil.which(MARKER_CMD) else [MARKER_CMD]
        fatal = []
        if missing and config.force_ocr:
            fatal.append("marker_single is required when OCR provider 'marker' may be used.")
        degraded = _marker_cache_warnings(config)
        if missing and not config.force_ocr:
            degraded.append("Marker OCR is unavailable; scanned pages will need fallback OCR or will fail.")
        return ProviderCapability(
            provider=self.name,
            available=not missing,
            missing_binaries=missing,
            fatal=fatal,
            degraded=degraded,
        )

    def extract_page(
        self,
        pdf_path: Path,
        page_number: int,
        total_pages: int,
        config: ExtractionConfig,
    ) -> ProviderResult:
        if config.marker_model_cache_dir is not None:
            config.marker_model_cache_dir.mkdir(parents=True, exist_ok=True)
            os.environ["MODEL_CACHE_DIR"] = str(config.marker_model_cache_dir.resolve())

        with tempfile.TemporaryDirectory(prefix="pagewise_marker_") as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            prepared = prepare_page_for_ocr(
                pdf_path,
                page_number,
                temp_dir / "prepared-page.pdf",
                dpi=config.marker_render_dpi,
                detect_two_up=config.detect_two_up,
            )
            cmd = [
                MARKER_CMD,
                str(prepared.pdf_path),
                "--output_format",
                "markdown",
                "--output_dir",
                str(temp_dir),
                "--force_ocr",
                "--paginate_output",
                "--page_separator",
                PAGE_BREAK,
            ]
            result = _run_streamed(cmd)
            if result.returncode != 0:
                raise ProviderError(
                    f"marker_single exited with code {result.returncode}: "
                    f"{clean_console_output(result.output)}"
                )
            markdown_files = sorted(temp_dir.rglob("*.md"), key=lambda path: len(str(path)))
            if not markdown_files:
                raise ProviderError("marker_single produced no markdown output")
            text = _logical_page_headings(
                markdown_files[0].read_text(encoding="utf-8").strip(),
                prepared.logical_pages,
            )

        status = text_quality_status(
            text,
            config.min_ocr_chars,
            ok_status="marker_ok",
            empty_status="marker_empty",
            low_status="marker_low_quality",
        )
        return ProviderResult(
            text=text,
            status=status,
            characters=len(text),
            metadata={
                "stdout_stderr": clean_console_output(result.output),
                "render_dpi": config.marker_render_dpi,
                "logical_pages": prepared.logical_pages,
                "two_up_detected": prepared.logical_pages == 2,
                "split_ratio": prepared.split_ratio,
                "split_confidence": prepared.split_confidence,
            },
            layout_artifacts=prepared.artifacts + markdown_layout_artifacts(text, page_number),
        )


class _ProcessResult:
    def __init__(self, returncode: int, output: str):
        self.returncode = returncode
        self.output = output


def _run_streamed(cmd: list[str]) -> _ProcessResult:
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    output_lines: list[str] = []
    assert process.stdout is not None
    try:
        for line in process.stdout:
            output_lines.append(line.rstrip())
    except KeyboardInterrupt:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        raise
    return _ProcessResult(process.wait(), "\n".join(output_lines))


def _marker_cache_warnings(config: ExtractionConfig) -> list[str]:
    if config.marker_model_cache_dir:
        return [f"Marker model cache: {config.marker_model_cache_dir}"]
    return ["Marker may download/cache models during the first OCR run."]


def _logical_page_headings(text: str, logical_pages: int) -> str:
    if logical_pages <= 1:
        return text.replace(PAGE_BREAK, "").strip()
    import re

    index = 0

    def replace_break(_match) -> str:
        nonlocal index
        index += 1
        return f"\n\n## Logical Page {index}\n\n"

    normalized = re.sub(r"\{\d+\}" + re.escape(PAGE_BREAK), replace_break, text)
    if index == 0:
        normalized = f"## Logical Page 1\n\n{normalized}"
    return normalized.strip()
