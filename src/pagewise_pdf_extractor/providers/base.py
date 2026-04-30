"""Provider protocol and shared helpers."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path

from ..config import ExtractionConfig
from ..models import ProviderCapability, ProviderResult


class PageExtractor(ABC):
    name: str

    @abstractmethod
    def validate(self, config: ExtractionConfig) -> ProviderCapability:
        raise NotImplementedError

    @abstractmethod
    def extract_page(
        self,
        pdf_path: Path,
        page_number: int,
        total_pages: int,
        config: ExtractionConfig,
    ) -> ProviderResult:
        raise NotImplementedError


def text_quality_status(text: str, min_chars: int, ok_status: str, empty_status: str, low_status: str) -> str:
    stripped = text.strip()
    if not stripped:
        return empty_status
    if len(stripped) < min_chars:
        return low_status
    non_whitespace = sum(1 for char in stripped if not char.isspace())
    if non_whitespace / max(len(stripped), 1) < 0.25:
        return low_status
    return ok_status


def snippet(text: str, limit: int = 200) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + "..."


ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
ANSI_ESCAPE_RE_ALT = re.compile(r"\x1B\][^\x07]*(?:\x07|\x1B\\)")


def clean_console_output(text: str, limit: int = 300) -> str:
    text = ANSI_ESCAPE_RE_ALT.sub("", text or "")
    text = ANSI_ESCAPE_RE.sub("", text).replace("\r", "\n")
    lines = []
    for raw_line in text.splitlines():
        line = "".join(ch for ch in raw_line if ch.isprintable() and ord(ch) < 128).strip()
        if line:
            lines.append(line)
    return snippet(" | ".join(lines), limit=limit)
