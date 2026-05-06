# pagewise-pdf-extractor

Page-wise PDF to Markdown extraction with text extraction, OCR, LLM fallback, and progress metadata.

`pagewise-pdf-extractor` is a Python package and CLI for converting PDFs into deterministic page-level Markdown files. It routes each page through embedded-text extraction, scanned-page OCR, and optional vision-model fallback, then returns structured results for RAG and document-processing pipelines.

## What It Does

- Extracts text-native PDF pages with PyMuPDF.
- Extracts scanned/image pages with Marker.
- Falls back to Ollama vision OCR when configured OCR fails.
- Writes one UTF-8 Markdown file per page.
- Writes atomic `progress.json` with provider attempts, status, config hash, source hash, and page metadata.
- Exposes a library API for applications and a CLI for operators.
- Keeps local processing as the default; remote services are only used if explicitly configured.

## Status

`v0.1.1` is the current public release. The public API is intended for early downstream use by applications that need page-wise PDF extraction, but the project is still pre-`1.0`.

## Install

From PyPI after publication:

```powershell
python -m pip install pagewise-pdf-extractor
```

Pinned Git dependency:

```txt
pagewise-pdf-extractor @ git+https://github.com/ebmurha/pagewise-pdf-extractor.git@v0.1.1
```

Local development:

```powershell
python -m pip install -e D:\Developer\Projects\pagewise-pdf-extractor
```

Runtime dependencies are declared in `pyproject.toml`. OCR providers also require local binaries:

- `marker_single` for Marker OCR
- `ollama` for Ollama fallback
- `pdftoppm` for rendering pages passed to Ollama

Check the local environment:

```powershell
pagewise-pdf-extractor --validate-environment
```

## Quickstart

CLI:

```powershell
pagewise-pdf-extractor document.pdf --output-root output
```

Python:

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

Public import contract:

```python
from pagewise_pdf_extractor import (
    ExtractionConfig,
    ExtractionResult,
    process_pdf,
    validate_environment,
)
```

## Output

Default layout:

```text
output/
  <input_sha256>/
    page_0001.md
    page_0002.md
    progress.json
```

Successful page:

```markdown
# Page N

<provider markdown content>
```

Failed page:

```markdown
# Page N

OCR FAILED

Error: <error_message>
```

## Provider Routing

Default page-level routing:

1. Try embedded text extraction with PyMuPDF.
2. Accept embedded text when it meets configured quality thresholds.
3. Use Marker OCR when embedded text is absent, low quality, or `force_ocr=True`.
4. Use Ollama fallback when Marker fails or returns unusable output and fallback is enabled.
5. Write failure Markdown if all configured providers fail.

## Documentation

- [API reference](docs/API.md)
- [Configuration reference](docs/CONFIGURATION.md)
- [Environment and provider setup](docs/ENVIRONMENT.md)
- [Integration guide](docs/INTEGRATION.md)
- [Packaging and naming guide](docs/PACKAGING.md)
- [Releases and versioning](docs/RELEASE.md)
- [Changelog](CHANGELOG.md)
- [Release notes](docs/releases/v0.1.0.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

## Tests

```powershell
python -m unittest discover -s tests -p "test_*.py"
python -c "from pagewise_pdf_extractor import ExtractionConfig, process_pdf, validate_environment; print('ok')"
pagewise-pdf-extractor --help
```

## Future Goals

Future work should preserve the public API, keep provider behavior explicit, and add new providers or extraction quality improvements behind documented configuration.
