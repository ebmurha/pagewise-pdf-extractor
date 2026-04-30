"""Environment validation for configured providers."""

from __future__ import annotations

from .config import ExtractionConfig
from .models import EnvironmentReport, ProviderCapability
from .providers.marker_ocr import MarkerOCRExtractor
from .providers.ollama_vision import OllamaVisionExtractor
from .providers.pymupdf_text import PyMuPDFTextExtractor


def validate_environment(config: ExtractionConfig | None = None) -> EnvironmentReport:
    config = config or ExtractionConfig()
    providers: dict[str, ProviderCapability] = {}

    if config.text_provider == "pymupdf":
        providers["pymupdf"] = PyMuPDFTextExtractor().validate(config)

    if config.ocr_provider == "marker":
        providers["marker"] = MarkerOCRExtractor().validate(config)

    if config.fallback_provider == "ollama":
        providers["ollama"] = OllamaVisionExtractor().validate(config)

    missing_python_packages: list[str] = []
    missing_binaries: list[str] = []
    degraded: list[str] = []
    fatal: list[str] = []

    for capability in providers.values():
        missing_python_packages.extend(capability.missing_python_packages)
        missing_binaries.extend(capability.missing_binaries)
        degraded.extend(capability.degraded)
        fatal.extend(capability.fatal)

    return EnvironmentReport(
        providers=providers,
        missing_python_packages=sorted(set(missing_python_packages)),
        missing_binaries=sorted(set(missing_binaries)),
        degraded_capabilities=degraded,
        fatal_blockers=fatal,
    )
