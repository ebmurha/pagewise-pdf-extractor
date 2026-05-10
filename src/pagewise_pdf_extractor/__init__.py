"""Public API for pagewise-pdf-extractor."""

from .api import EXTRACTOR_VERSION, process_pdf
from .config import ExtractionConfig
from .environment import validate_environment
from .exceptions import (
    ConcurrencyError,
    ConfigurationError,
    DependencyMissingError,
    ExtractionError,
    InvalidInputError,
    PageExtractionError,
    ProgressError,
    ProviderError,
)
from .models import EnvironmentReport, ExtractionResult, LayoutArtifact, PageExtractionResult, ProviderAttempt

__version__ = EXTRACTOR_VERSION

__all__ = [
    "ExtractionConfig",
    "ExtractionResult",
    "PageExtractionResult",
    "LayoutArtifact",
    "ProviderAttempt",
    "EnvironmentReport",
    "process_pdf",
    "validate_environment",
    "ExtractionError",
    "InvalidInputError",
    "DependencyMissingError",
    "ProviderError",
    "PageExtractionError",
    "ProgressError",
    "ConfigurationError",
    "ConcurrencyError",
]
