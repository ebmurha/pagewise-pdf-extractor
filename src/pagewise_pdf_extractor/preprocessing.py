"""Visual preprocessing for OCR providers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import LayoutArtifact


@dataclass(slots=True)
class PreparedOCRPage:
    pdf_path: Path
    artifacts: list[LayoutArtifact]
    logical_pages: int
    split_ratio: float | None = None
    split_confidence: float = 0.0


def prepare_page_for_ocr(
    source_pdf: Path,
    page_number: int,
    output_pdf: Path,
    *,
    dpi: int,
    detect_two_up: bool,
) -> PreparedOCRPage:
    import fitz  # type: ignore
    import numpy as np  # type: ignore

    with fitz.open(str(source_pdf)) as document:
        page = document.load_page(page_number - 1)
        page_rect = page.rect
        scale = dpi / 72
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False)
        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, 3)

    split_ratio, confidence = detect_two_up_split(image) if detect_two_up else (None, 0.0)
    regions = [(0, pixmap.width)]
    if split_ratio is not None:
        split_x = round(pixmap.width * split_ratio)
        regions = [(0, split_x), (split_x, pixmap.width)]

    output = fitz.open()
    artifacts: list[LayoutArtifact] = []
    try:
        for logical_index, (x0, x1) in enumerate(regions, start=1):
            crop = image[:, x0:x1]
            height, width = crop.shape[:2]
            crop_pixmap = fitz.Pixmap(fitz.csRGB, width, height, crop.tobytes(), False)
            target_page = output.new_page(width=width / scale, height=height / scale)
            target_page.insert_image(target_page.rect, pixmap=crop_pixmap)
            source_bbox = (
                page_rect.x0 + page_rect.width * (x0 / pixmap.width),
                page_rect.y0,
                page_rect.x0 + page_rect.width * (x1 / pixmap.width),
                page_rect.y1,
            )
            artifacts.append(
                LayoutArtifact(
                    kind="logical_page",
                    page_number=page_number,
                    bbox=source_bbox,
                    metadata={
                        "source": "two_up_preprocessor" if len(regions) == 2 else "ocr_preprocessor",
                        "logical_index": logical_index,
                        "logical_pages": len(regions),
                        "coordinate_space": "pdf_points",
                        "render_dpi": dpi,
                        "split_confidence": round(confidence, 3),
                    },
                )
            )
        output.save(str(output_pdf), deflate=True)
    finally:
        output.close()

    return PreparedOCRPage(
        pdf_path=output_pdf,
        artifacts=artifacts,
        logical_pages=len(regions),
        split_ratio=split_ratio,
        split_confidence=confidence,
    )


def detect_two_up_split(image) -> tuple[float | None, float]:
    """Find a balanced center gutter or separator in a rendered RGB page."""
    import numpy as np  # type: ignore

    if image.ndim != 3 or image.shape[1] < 400 or image.shape[0] < 400:
        return None, 0.0

    gray = (
        image[:, :, 0].astype(np.float32) * 0.299
        + image[:, :, 1].astype(np.float32) * 0.587
        + image[:, :, 2].astype(np.float32) * 0.114
    )
    height, width = gray.shape
    ink = gray[int(height * 0.12) : int(height * 0.95)] < 200
    density = ink.mean(axis=0)

    left_density = float(ink[:, int(width * 0.08) : int(width * 0.42)].mean())
    right_density = float(ink[:, int(width * 0.58) : int(width * 0.92)].mean())
    if min(left_density, right_density) < 0.05:
        return None, 0.0

    low = int(width * 0.44)
    high = int(width * 0.56)
    window = max(3, int(width * 0.012))
    smoothed = np.convolve(density, np.ones(window) / window, mode="same")
    gutter_x = low + int(np.argmin(smoothed[low:high]))
    gutter_density = float(smoothed[gutter_x])

    rule_x = low + int(np.argmax(density[low:high]))
    rule_density = float(density[rule_x])
    neighbor_start = max(low, rule_x - max(8, window * 2))
    neighbor_end = min(high, rule_x + max(8, window * 2) + 1)
    neighbors = np.concatenate(
        (density[neighbor_start : max(neighbor_start, rule_x - 3)], density[min(rule_x + 4, neighbor_end) : neighbor_end])
    )
    neighbor_density = float(np.median(neighbors)) if neighbors.size else 1.0

    if gutter_density <= 0.025:
        balance = min(left_density, right_density) / max(left_density, right_density)
        confidence = min(0.99, 0.65 + balance * 0.25 + (0.025 - gutter_density) * 4)
        return round(gutter_x / width, 4), round(confidence, 3)

    if rule_density >= 0.55 and neighbor_density <= 0.08:
        confidence = min(0.99, 0.75 + (rule_density - neighbor_density) * 0.2)
        return round(rule_x / width, 4), round(confidence, 3)

    return None, 0.0
