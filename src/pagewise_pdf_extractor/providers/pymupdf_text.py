"""PyMuPDF embedded-text extraction provider."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import Any

from ..config import ExtractionConfig
from ..exceptions import ProviderError
from ..models import LayoutArtifact, ProviderCapability, ProviderResult
from ..quality import assess_embedded_text
from .base import PageExtractor


class PyMuPDFTextExtractor(PageExtractor):
    name = "pymupdf"

    def validate(self, config: ExtractionConfig) -> ProviderCapability:
        try:
            import fitz  # type: ignore  # noqa: F401
        except Exception:
            return ProviderCapability(
                provider=self.name,
                available=False,
                missing_python_packages=["PyMuPDF"],
                fatal=["PyMuPDF is required when text_provider='pymupdf'."],
            )
        return ProviderCapability(provider=self.name, available=True)

    def extract_page(
        self,
        pdf_path: Path,
        page_number: int,
        total_pages: int,
        config: ExtractionConfig,
    ) -> ProviderResult:
        try:
            import fitz  # type: ignore

            with fitz.open(str(pdf_path)) as document:
                page = document.load_page(page_number - 1)
                text = page.get_text("text", sort=True).strip()
                layout_artifacts = _extract_layout_artifacts(page, page_number)
                fonts = page.get_fonts(full=True)
                spacing_ratio, spacing_pairs = _suspicious_word_spacing(page)
        except Exception as exc:
            raise ProviderError(f"PyMuPDF text extraction failed: {exc}") from exc

        quality = assess_embedded_text(
            text,
            min_chars=config.min_text_chars,
            fonts=fonts,
            table_count=sum(artifact.kind == "table" for artifact in layout_artifacts),
            suspicious_spacing_ratio=spacing_ratio,
            suspicious_spacing_pairs=spacing_pairs,
            prefer_visual_tables=config.prefer_visual_tables,
        )
        if not text.strip():
            status = "text_empty"
        elif not config.validate_text_quality:
            status = "text_ok" if len(text) >= config.min_text_chars else "text_low_quality"
        else:
            status = "text_ok" if quality.accepted else "text_low_quality"
        return ProviderResult(
            text=text,
            status=status,
            characters=len(text),
            metadata={
                "page_number": page_number,
                "total_pages": total_pages,
                "quality_score": quality.score,
                "quality_reasons": quality.reasons,
                "quality_metrics": quality.metrics,
            },
            layout_artifacts=layout_artifacts,
        )


def _extract_layout_artifacts(page: Any, page_number: int) -> list[LayoutArtifact]:
    artifacts: list[LayoutArtifact] = []
    artifacts.extend(_extract_table_artifacts(page, page_number))
    artifacts.extend(_extract_image_artifacts(page, page_number))
    artifacts.extend(_extract_drawing_artifacts(page, page_number))
    return artifacts


def _suspicious_word_spacing(page: Any) -> tuple[float, int]:
    try:
        words = page.get_text("words", sort=True)
    except Exception:
        return 0.0, 0

    lines: dict[tuple[int, int], list[Any]] = {}
    for word in words:
        if len(word) >= 7:
            lines.setdefault((int(word[5]), int(word[6])), []).append(word)

    suspicious = 0
    pairs = 0
    for line_words in lines.values():
        ordered = sorted(line_words, key=lambda word: float(word[0]))
        for left, right in zip(ordered, ordered[1:]):
            left_text = str(left[4])
            right_text = str(right[4])
            if not left_text.isalpha() or not right_text.isalpha():
                continue
            left_width = (float(left[2]) - float(left[0])) / max(len(left_text), 1)
            right_width = (float(right[2]) - float(right[0])) / max(len(right_text), 1)
            typical_width = max(min(left_width, right_width), 0.1)
            gap_ratio = (float(right[0]) - float(left[2])) / typical_width
            pairs += 1
            if gap_ratio < 0.3:
                suspicious += 1
    return suspicious / max(pairs, 1), suspicious


def _extract_table_artifacts(page: Any, page_number: int) -> list[LayoutArtifact]:
    find_tables = getattr(page, "find_tables", None)
    if find_tables is None:
        return []
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            table_finder = find_tables()
    except Exception:
        return []

    artifacts = []
    for table_index, table in enumerate(getattr(table_finder, "tables", []), start=1):
        try:
            rows = _normalize_table_rows(table.extract())
        except Exception:
            rows = []
        if not _usable_table_rows(rows):
            continue
        artifacts.append(
            LayoutArtifact(
                kind="table",
                page_number=page_number,
                bbox=_rect_tuple(getattr(table, "bbox", None)),
                rows=rows,
                text=_rows_to_markdown(rows) if rows else None,
                metadata={"source": "pymupdf", "table_index": table_index},
            )
        )
    return artifacts


def _extract_image_artifacts(page: Any, page_number: int) -> list[LayoutArtifact]:
    artifacts = []
    seen: set[tuple[int, tuple[float, float, float, float] | None]] = set()
    try:
        images = page.get_images(full=True)
    except Exception:
        return artifacts

    for image_index, image in enumerate(images, start=1):
        xref = int(image[0])
        try:
            rects = page.get_image_rects(xref)
        except Exception:
            rects = []
        for rect in rects or [None]:
            bbox = _rect_tuple(rect)
            key = (xref, bbox)
            if key in seen:
                continue
            seen.add(key)
            artifacts.append(
                LayoutArtifact(
                    kind="figure",
                    page_number=page_number,
                    bbox=bbox,
                    metadata={
                        "source": "pymupdf",
                        "image_index": image_index,
                        "xref": xref,
                        "width": image[2] if len(image) > 2 else None,
                        "height": image[3] if len(image) > 3 else None,
                    },
                )
            )
    return artifacts


def _extract_drawing_artifacts(page: Any, page_number: int) -> list[LayoutArtifact]:
    try:
        drawings = page.get_drawings()
    except Exception:
        return []

    artifacts = []
    for drawing_index, drawing in enumerate(drawings, start=1):
        bbox = _rect_tuple(drawing.get("rect"))
        if bbox is None or _rect_area(bbox) < 100:
            continue
        artifacts.append(
            LayoutArtifact(
                kind="drawing",
                page_number=page_number,
                bbox=bbox,
                metadata={
                    "source": "pymupdf",
                    "drawing_index": drawing_index,
                    "items": len(drawing.get("items", [])),
                    "fill": _serializable_color(drawing.get("fill")),
                    "stroke": _serializable_color(drawing.get("color")),
                },
            )
        )
        if len(artifacts) >= 50:
            break
    return artifacts


def _normalize_table_rows(rows: Any) -> list[list[str]]:
    return [["" if cell is None else str(cell).strip() for cell in row] for row in rows or []]


def _usable_table_rows(rows: list[list[str]]) -> bool:
    if len(rows) < 2 or max((len(row) for row in rows), default=0) < 2:
        return False
    cells = [cell for row in rows for cell in row]
    nonempty = sum(bool(cell) for cell in cells)
    return nonempty >= 4 and nonempty / max(len(cells), 1) >= 0.15


def _rows_to_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    header = normalized[0]
    body = normalized[1:]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def _rect_tuple(rect: Any) -> tuple[float, float, float, float] | None:
    if rect is None:
        return None
    try:
        return (float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))
    except Exception:
        try:
            return (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))
        except Exception:
            return None


def _rect_area(bbox: tuple[float, float, float, float]) -> float:
    return max(bbox[2] - bbox[0], 0) * max(bbox[3] - bbox[1], 0)


def _serializable_color(color: Any) -> list[float] | None:
    if color is None:
        return None
    try:
        return [float(value) for value in color]
    except Exception:
        return None
