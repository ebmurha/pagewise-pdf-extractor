# Integration Guide

This document describes how downstream applications such as `rag-engine` should consume the package.

## Dependency Declaration

Use a pinned tag:

```txt
pagewise-pdf-extractor @ git+https://github.com/ebmurha/pagewise-pdf-extractor.git@v0.1.2
```

Do not depend on `main`.

## Basic Integration

```python
from pathlib import Path

from pagewise_pdf_extractor import ExtractionConfig, ExtractionResult, process_pdf


def run_extraction(pdf_path: Path, work_dir: Path) -> ExtractionResult:
    return process_pdf(
        input_pdf=pdf_path,
        output_root=work_dir / "extracted",
        config=ExtractionConfig(
            text_provider="pymupdf",
            ocr_provider="marker",
            fallback_provider="ollama",
            fallback_enabled=True,
            ollama_model="deepseek-ocr",
        ),
    )
```

## Environment Preflight

```python
from pagewise_pdf_extractor import ExtractionConfig, validate_environment

config = ExtractionConfig()
report = validate_environment(config)
if report.has_fatal_errors:
    raise RuntimeError(report.summary)
```

Applications can store `report.to_dict()` in diagnostics or show it in an admin UI.

## Result Mapping

```python
for page in result.pages:
    metadata = {
        "fallback_used": page.fallback_used,
        "attempts": [attempt.model_dump() for attempt in page.attempts],
        "error": page.error,
    }
```

Use:

- `result.status` for run-level status
- `result.failed_pages` for quick failure checks
- `page.status` for page-level workflow state
- `page.output_file` for the Markdown file path
- `page.final_provider` for provider attribution

## Output Contract

The output directory is returned by `result.output_dir`. Do not reconstruct it from PDF names.

Default:

```text
<output_root>/<input_sha256>/
```

With `separate_runs=True`:

```text
<output_root>/<input_sha256>/<run_id>/
```

## Concurrency

Different PDFs can share an `output_root`. Same-PDF concurrent runs should use `separate_runs=True` or separate output roots.

If two runs target the same resolved output directory, the second run raises `ConcurrencyError`.

## Privacy

Local providers are the default. The package does not send document content to remote services unless the configured provider does so. Applications should document their own provider deployment and data-handling policies.
