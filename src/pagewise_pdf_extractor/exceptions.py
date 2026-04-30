"""Typed exceptions raised by pagewise-pdf-extractor."""


class ExtractionError(RuntimeError):
    """Base exception for extraction failures."""


class InvalidInputError(ExtractionError):
    """The input file is missing, unreadable, or not a PDF."""


class DependencyMissingError(ExtractionError):
    """A required Python package or external binary is unavailable."""


class ProviderError(ExtractionError):
    """A provider failed while extracting a page."""


class PageExtractionError(ExtractionError):
    """All configured providers failed for one page."""

    def __init__(self, message: str, attempts: list):
        super().__init__(message)
        self.attempts = attempts


class ProgressError(ExtractionError):
    """Progress state could not be read, validated, or written."""


class ConfigurationError(ExtractionError):
    """The extraction configuration is invalid."""


class ConcurrencyError(ExtractionError):
    """A conflicting extraction run is already using the target output."""
