"""Ollama vision fallback provider."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..config import ExtractionConfig
from ..exceptions import ProviderError
from ..models import ProviderCapability, ProviderResult
from .base import PageExtractor, clean_console_output, markdown_layout_artifacts, snippet, text_quality_status

OLLAMA_CMD = "ollama"
PDFTOPPM_CMD = "pdftoppm"
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


class OllamaVisionExtractor(PageExtractor):
    name = "ollama"

    def validate(self, config: ExtractionConfig) -> ProviderCapability:
        missing = []
        if shutil.which(OLLAMA_CMD) is None:
            missing.append(OLLAMA_CMD)
        if shutil.which(PDFTOPPM_CMD) is None:
            missing.append(PDFTOPPM_CMD)
        fatal = []
        if missing and config.force_fallback:
            fatal.append("Forced Ollama fallback requires ollama and pdftoppm on PATH.")
        degraded = []
        if missing and config.fallback_enabled and not config.force_fallback:
            degraded.append("Ollama fallback is configured but not fully available.")
        return ProviderCapability(
            provider=self.name,
            available=not missing,
            missing_binaries=missing,
            degraded=degraded,
            fatal=fatal,
        )

    def extract_page(
        self,
        pdf_path: Path,
        page_number: int,
        total_pages: int,
        config: ExtractionConfig,
    ) -> ProviderResult:
        env = os.environ.copy()
        if config.ollama_endpoint:
            env["OLLAMA_HOST"] = config.ollama_endpoint

        with tempfile.TemporaryDirectory(prefix="pagewise_ollama_") as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            page_prefix = temp_dir / f"page-{page_number}"
            image_path = page_prefix.with_suffix(".png")
            render_cmd = [
                PDFTOPPM_CMD,
                "-r",
                str(config.render_dpi),
                "-f",
                str(page_number),
                "-l",
                str(page_number),
                "-singlefile",
                "-png",
                str(pdf_path),
                str(page_prefix),
            ]
            render = subprocess.run(
                render_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if render.returncode != 0:
                raise ProviderError(
                    f"pdftoppm exited with code {render.returncode}: "
                    f"{clean_console_output(render.stderr or render.stdout)}"
                )
            if not image_path.exists():
                raise ProviderError(f"pdftoppm did not create expected page image: {image_path.name}")

            prompt = f"{image_path}\n{config.ollama_prompt}"
            ocr_cmd = [OLLAMA_CMD, "run", config.ollama_model, "--hidethinking", prompt]
            result = subprocess.run(
                ocr_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                env=env,
            )
            if result.returncode != 0:
                raise ProviderError(
                    f"ollama run exited with code {result.returncode}. "
                    f"stdout={snippet(result.stdout or '')!r} stderr={snippet(result.stderr or '')!r}"
                )
            text = _normalize_ollama_output(result.stdout or "")

        status = text_quality_status(
            text,
            config.min_ocr_chars,
            ok_status="ollama_ok",
            empty_status="ollama_empty",
            low_status="ollama_low_quality",
        )
        return ProviderResult(
            text=text,
            status=status,
            characters=len(text),
            metadata={"model": config.ollama_model, "render_dpi": config.render_dpi},
            layout_artifacts=markdown_layout_artifacts(text, page_number),
        )


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
