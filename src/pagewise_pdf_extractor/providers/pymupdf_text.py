"""PyMuPDF embedded-text extraction provider."""

from __future__ import annotations

from pathlib import Path

from ..config import ExtractionConfig
from ..exceptions import ProviderError
from ..models import ProviderCapability, ProviderResult
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
        )
