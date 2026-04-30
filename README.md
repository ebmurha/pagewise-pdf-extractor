# pagewise-pdf-extractor

Standalone Python package for converting PDFs into one Markdown file per page with structured metadata, atomic progress tracking, and provider-level observability.

It handles text-native PDFs through PyMuPDF, scanned pages through Marker, and optional Ollama vision fallback when OCR fails.

## Install

Development install:

```powershell
pip install -e D:\Developer\Projects\pagewise-pdf-extractor
```

Runtime dependencies are declared in `pyproject.toml`. External tools are still required for OCR paths:

- `marker_single` for Marker OCR
- `ollama` for Ollama fallback
- `pdftoppm` for rendering pages passed to Ollama

See [docs/PACKAGING.md](docs/PACKAGING.md) for naming, installation, and dependency-check guidance.

## CLI Usage

```powershell
pagewise-pdf-extractor document.pdf --output-root output
```

Useful flags:

```powershell
pagewise-pdf-extractor document.pdf --force-ocr
pagewise-pdf-extractor document.pdf --force-fallback --ollama-model deepseek-ocr
pagewise-pdf-extractor document.pdf --marker-model-cache-dir D:\DevTools\marker-model-cache
pagewise-pdf-extractor --validate-environment
```

Exit codes:

- `0`: completed, including partial page failures
- `1`: startup or fatal failure
- `2`: invalid input
- `130`: interrupted

## Library Usage

```python
from pathlib import Path

from pagewise_pdf_extractor import ExtractionConfig, process_pdf, validate_environment

config = ExtractionConfig(
    text_provider="pymupdf",
    ocr_provider="marker",
    fallback_provider="ollama",
    fallback_enabled=True,
    ollama_model="deepseek-ocr",
)

report = validate_environment(config)
if report.has_fatal_errors:
    raise RuntimeError(report.summary)

result = process_pdf(
    input_pdf=Path("document.pdf"),
    output_root=Path("output"),
    config=config,
)
```

The public import contract is:

```python
from pagewise_pdf_extractor import (
    ExtractionConfig,
    ExtractionResult,
    process_pdf,
    validate_environment,
)
```

## Provider Behavior

Default page-level routing:

1. Try embedded text extraction with PyMuPDF.
2. Accept embedded text when it meets `min_text_chars` and basic cleanliness checks.
3. Use Marker OCR when embedded text is absent, low quality, or `force_ocr=True`.
4. Use Ollama fallback when Marker fails or returns unusable output and fallback is enabled.
5. Write failure Markdown for a page if all configured providers fail.

Local providers are the default. Document content is not sent to remote services unless you configure a provider endpoint that does so.

## Output Layout

The caller controls `output_root`. By default each source PDF writes under its SHA-256 hash, so same-stem PDFs from different folders do not collide:

```text
output/
  <input_sha256>/
    page_0001.md
    page_0002.md
    progress.json
```

Set `ExtractionConfig(separate_runs=True)` or `--separate-runs` to write under:

```text
output/<input_sha256>/<run_id>/
```

## Markdown Contract

Success:

```markdown
# Page N

<provider markdown content>
```

Failure:

```markdown
# Page N

OCR FAILED

Error: <error_message>
```

Page files are UTF-8. Empty provider output is rejected as a failed/low-quality attempt.

## progress.json

`progress.json` is written after startup validation and after every page. It is written atomically with a run-specific temp file.

Top-level fields include:

- `schema_version`
- `extractor_version`
- `input_file`
- `input_file_name`
- `input_sha256`
- `total_pages`
- `pipeline`
- `config_hash`
- `config_used`
- `run_id`
- `started_at`
- `updated_at`
- `completed_at`
- `status`
- `last_completed_page`
- `failed_pages`
- `pages`

Each page record includes status, character count, duration, output file, final provider, fallback flag, attempts, and error when failed.

## Resume and Concurrency

Resume is enabled by default when `progress.json` matches source path, source hash, page count, extractor version, schema version, and config hash. Mismatches start a clean baseline for that output directory.

Concurrent extractions of different PDFs are safe when given the same `output_root` because outputs are SHA-256 isolated. The package creates an exclusive `.pagewise-extractor.lock` in the resolved output directory, so concurrent extractions of the same PDF/output directory fail fast with `ConcurrencyError`. Use `separate_runs=True` or distinct run-scoped output directories when same-PDF parallelism is needed.

## Tests

```powershell
python -m unittest discover -s tests -p "test_*.py"
python -c "from pagewise_pdf_extractor import ExtractionConfig, process_pdf, validate_environment; print('ok')"
pagewise-pdf-extractor --help
```

## Manual Release Steps

The package name is currently implemented as:

- distribution: `pagewise-pdf-extractor`
- import: `pagewise_pdf_extractor`

Manual steps before external consumption:

- confirm the package name
- rename/update the GitHub repository if needed
- tag a known-good commit, for example `v0.1.0`
- have `rag-engine` pin the GitHub dependency to that tag or commit SHA
- publish to PyPI later only after the public API stabilizes

The collaborator release workflow is documented in [docs/RELEASE.md](docs/RELEASE.md).
