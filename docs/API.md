# API Reference

This document describes the stable public API intended for application integrations.

## Public Imports

```python
from pagewise_pdf_extractor import (
    ExtractionConfig,
    ExtractionResult,
    LayoutArtifact,
    PageExtractionResult,
    ProviderAttempt,
    process_pdf,
    validate_environment,
)
```

Do not import from repository-root scripts or private provider modules. The public package import is the supported API boundary.

## process_pdf

```python
def process_pdf(
    input_pdf: Path,
    output_root: Path,
    *,
    config: ExtractionConfig | None = None,
    run_id: str | None = None,
    logger: logging.Logger | None = None,
) -> ExtractionResult:
    ...
```

Parameters:

- `input_pdf`: source PDF path.
- `output_root`: caller-controlled root directory for extracted page Markdown and `progress.json`.
- `config`: extraction settings. Defaults to `ExtractionConfig()`.
- `run_id`: optional caller-provided run identifier.
- `logger`: optional caller-owned logger. Library mode does not configure global handlers.

Startup/fatal failures raise typed exceptions. Page-level failures are recorded as failed page results by default. CLI exit codes are only for CLI use.

## ExtractionConfig

```python
ExtractionConfig(
    text_provider="pymupdf",
    ocr_provider="marker",
    fallback_provider="ollama",
    fallback_enabled=True,
    force_ocr=False,
    force_fallback=False,
    min_text_chars=50,
    min_ocr_chars=20,
    marker_model_cache_dir=None,
    ollama_model="deepseek-ocr",
    ollama_endpoint=None,
    ollama_prompt="<|grounding|>Convert the document to markdown.",
    render_dpi=200,
    fail_fast=False,
    resume=True,
    separate_runs=False,
)
```

## ExtractionResult

Fields:

- `input_pdf`
- `output_dir`
- `progress_path`
- `extractor_version`
- `input_sha256`
- `total_pages`
- `pages`
- `failed_pages`
- `status`: `ok`, `partial_failure`, `failed`, or `interrupted`
- `run_id`
- `schema_version`
- `started_at`
- `completed_at`
- `config_hash`
- `config_used`

## PageExtractionResult

Fields:

- `page_number`
- `status`: `ok`, `fallback_ok`, `low_text_warning`, or `failed`
- `output_file`
- `characters`
- `duration_seconds`
- `final_provider`
- `fallback_used`
- `attempts`
- `layout_artifacts`
- `error`

## LayoutArtifact

Fields:

- `kind`: `table`, `figure`, `drawing`, or provider-specific artifact type
- `page_number`
- `bbox`: optional PDF-space bounding box `[x0, y0, x1, y1]`
- `text`: optional Markdown/text representation or caption
- `rows`: table rows when available
- `metadata`: provider-specific details such as source, image dimensions, or vector drawing attributes

## ProviderAttempt

Fields:

- `provider`
- `status`: `ok`, `skipped`, `failed`, or `low_quality`
- `characters`
- `duration_seconds`
- `error`
- `metadata`

## Exceptions

Typed exceptions exported by the package:

- `ExtractionError`
- `InvalidInputError`
- `DependencyMissingError`
- `ProviderError`
- `PageExtractionError`
- `ProgressError`
- `ConfigurationError`
- `ConcurrencyError`

Use these in application code instead of catching broad `Exception` where possible.
