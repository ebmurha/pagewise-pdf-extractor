"""PyMuPDF embedded-text extraction provider."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import Any

from ..config import ExtractionConfig
from ..exceptions import ProviderError
from ..models import LayoutArtifact, ProviderCapability, ProviderResult
from .base import PageExtractor, text_quality_status


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
        except Exception as exc:
            raise ProviderError(f"PyMuPDF text extraction failed: {exc}") from exc

        status = text_quality_status(
            text,
            config.min_text_chars,
            ok_status="text_ok",
            empty_status="text_empty",
            low_status="text_low_quality",
        )
        return ProviderResult(
            text=text,
            status=status,
            characters=len(text),
            metadata={"page_number": page_number, "total_pages": total_pages},
            layout_artifacts=layout_artifacts,
        )


def _extract_layout_artifacts(page: Any, page_number: int) -> list[LayoutArtifact]:
    artifacts: list[LayoutArtifact] = []
    artifacts.extend(_extract_table_artifacts(page, page_number))
    artifacts.extend(_extract_image_artifacts(page, page_number))
    artifacts.extend(_extract_drawing_artifacts(page, page_number))
    return artifacts


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
