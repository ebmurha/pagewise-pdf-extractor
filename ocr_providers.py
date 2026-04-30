"""Legacy compatibility shims for the old flat-script provider module.

New code should import from `pagewise_pdf_extractor`.
"""

from dataclasses import dataclass
from pathlib import Path

from pagewise_pdf_extractor import ExtractionConfig, validate_environment as _validate_environment
from pagewise_pdf_extractor.api import get_total_pages
from pagewise_pdf_extractor.models import ProviderAttempt
from pagewise_pdf_extractor.providers.marker_ocr import MARKER_CMD, MarkerOCRExtractor
from pagewise_pdf_extractor.providers.ollama_vision import OLLAMA_CMD, PDFTOPPM_CMD, OllamaVisionExtractor


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


def validate_environment() -> None:
    report = _validate_environment(ExtractionConfig(force_ocr=True))
    if report.has_fatal_errors:
        raise RuntimeError(report.summary)


def inspect_marker_cache() -> dict:
    return {
        "cache_root": "",
        "complete": False,
        "models": [],
        "note": "Marker cache inspection moved to pagewise_pdf_extractor provider validation.",
    }


def run_ocr_for_page(
    pdf_path: Path,
    page_number: int,
    total_pages: int,
    logger,
    ollama_model: str,
    force_ollama_fallback: bool = False,
) -> PageOCRResult:
    config = ExtractionConfig(
        force_fallback=force_ollama_fallback,
        ollama_model=ollama_model,
    )
    attempts: list[ProviderAttempt] = []
    try:
        if force_ollama_fallback:
            result = OllamaVisionExtractor().extract_page(pdf_path, page_number, total_pages, config)
            provider = "ollama"
            fallback_used = True
        else:
            result = MarkerOCRExtractor().extract_page(pdf_path, page_number, total_pages, config)
            provider = "marker"
            fallback_used = False
        attempts.append(ProviderAttempt(provider=provider, status="ok", characters=result.characters))
        return PageOCRResult(
            text=result.text,
            final_provider=provider,
            fallback_used=fallback_used,
            attempts=[attempt.to_dict() for attempt in attempts],
        )
    except Exception as exc:
        attempts.append(ProviderAttempt(provider="ocr", status="failed", error=str(exc), characters=0))
        raise PageOCRFailure(str(exc), [attempt.to_dict() for attempt in attempts]) from exc
