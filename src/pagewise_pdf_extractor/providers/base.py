"""Provider protocol and shared helpers."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path

from ..config import ExtractionConfig
from ..models import LayoutArtifact, ProviderCapability, ProviderResult


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


MARKDOWN_IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<target>[^)]+)\)")


def markdown_layout_artifacts(text: str, page_number: int) -> list[LayoutArtifact]:
    artifacts: list[LayoutArtifact] = []
    artifacts.extend(_markdown_table_artifacts(text, page_number))
    for match in MARKDOWN_IMAGE_RE.finditer(text):
        artifacts.append(
            LayoutArtifact(
                kind="figure",
                page_number=page_number,
                text=match.group("alt").strip() or None,
                metadata={"target": match.group("target").strip()},
            )
        )
    return artifacts


def _markdown_table_artifacts(text: str, page_number: int) -> list[LayoutArtifact]:
    artifacts: list[LayoutArtifact] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines) - 1:
        header = lines[index].strip()
        separator = lines[index + 1].strip()
        if _is_markdown_table_row(header) and _is_markdown_table_separator(separator):
            table_lines = [header, separator]
            index += 2
            while index < len(lines) and _is_markdown_table_row(lines[index].strip()):
                table_lines.append(lines[index].strip())
                index += 1
            rows = [_split_markdown_table_row(line) for line in table_lines if not _is_markdown_table_separator(line)]
            artifacts.append(
                LayoutArtifact(
                    kind="table",
                    page_number=page_number,
                    text="\n".join(table_lines),
                    rows=rows,
                    metadata={"source": "markdown"},
                )
            )
            continue
        index += 1
    return artifacts


def _is_markdown_table_row(line: str) -> bool:
    return line.startswith("|") and line.endswith("|") and line.count("|") >= 2


def _is_markdown_table_separator(line: str) -> bool:
    if not _is_markdown_table_row(line):
        return False
    cells = _split_markdown_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def _split_markdown_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]
