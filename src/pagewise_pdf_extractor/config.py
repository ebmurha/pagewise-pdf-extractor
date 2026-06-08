"""Configuration for PDF extraction."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ExtractionConfig:
    text_provider: str = "pymupdf"
    ocr_provider: str = "marker"
    fallback_provider: str | None = "ollama"
    fallback_enabled: bool = True
    force_ocr: bool = False
    force_fallback: bool = False
    min_text_chars: int = 50
    min_ocr_chars: int = 20
    validate_text_quality: bool = True
    prefer_visual_tables: bool = True
    detect_two_up: bool = True
    marker_render_dpi: int = 350
    output_format: str = "markdown"
    marker_model_cache_dir: Path | None = None
    ollama_model: str = "deepseek-ocr"
    ollama_endpoint: str | None = None
    ollama_prompt: str = "<|grounding|>Convert the document to markdown."
    render_dpi: int = 200
    fail_fast: bool = False
    resume: bool = True
    separate_runs: bool = False

    @classmethod
    def from_env(cls) -> "ExtractionConfig":
        cache_dir = os.environ.get("MODEL_CACHE_DIR")
        endpoint = os.environ.get("OLLAMA_ENDPOINT")
        return cls(
            marker_model_cache_dir=Path(cache_dir).expanduser() if cache_dir else None,
            ollama_endpoint=endpoint or None,
            ollama_model=os.environ.get("OLLAMA_MODEL", "deepseek-ocr"),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, Path):
                data[key] = str(value)
        return data

    def model_dump(self) -> dict[str, Any]:
        return self.to_dict()

    def hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
