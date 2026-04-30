# PDF Tool Project Overview

## Current Shape

The project is now an installable package:

```text
pagewise-pdf-extractor/
  pyproject.toml
  LICENSE
  README.md
  implementation-plan.md
  src/
    pagewise_pdf_extractor/
      __init__.py
      api.py
      cli.py
      config.py
      environment.py
      exceptions.py
      markdown.py
      models.py
      progress.py
      providers/
        base.py
        pymupdf_text.py
        marker_ocr.py
        ollama_vision.py
  tests/
```

Legacy `ocr_tool.py` and `pdf_ocr_marker.py` remain only as compatibility wrappers. New integrations should import `pagewise_pdf_extractor` or use the `pagewise-pdf-extractor` CLI.

## Public API

```python
from pagewise_pdf_extractor import (
    ExtractionConfig,
    ExtractionResult,
    process_pdf,
    validate_environment,
)
```

Primary call:

```python
result = process_pdf(
    input_pdf=pdf_path,
    output_root=work_dir / "extracted",
    config=ExtractionConfig(),
)
```

`process_pdf()` returns an `ExtractionResult` with input path, output directory, progress path, extractor version, source hash, total pages, page results, failed pages, run ID, schema version, config hash, and resolved config.

## Extraction Pipeline

Routing is per page:

1. PyMuPDF extracts embedded text unless `force_ocr` or `force_fallback` is set.
2. Text is accepted when it meets quality thresholds.
3. Marker OCR handles pages without usable embedded text.
4. Ollama fallback handles Marker failure or unusable OCR output when fallback is enabled.
5. Page-level failures write failure Markdown and are recorded without aborting the whole document by default.

Provider attempts are recorded with provider name, status, character count, duration, error, and metadata.

## Configuration

`ExtractionConfig` supports:

- provider selection
- fallback enable/disable
- forced OCR/fallback modes
- text/OCR quality thresholds
- Marker model cache directory
- Ollama model, endpoint, prompt, and render DPI
- fail-fast and resume behavior
- per-run output isolation

Environment variables are limited to appropriate external provider defaults such as `MODEL_CACHE_DIR`, `OLLAMA_ENDPOINT`, and `OLLAMA_MODEL`.

## Output

The caller controls `output_root`. Default output directory:

```text
<output_root>/<input_sha256>/
```

Optional isolated run directory:

```text
<output_root>/<input_sha256>/<run_id>/
```

Page Markdown files use:

```text
page_0001.md
page_0002.md
```

Success pages:

```markdown
# Page N

<content>
```

Failure pages:

```markdown
# Page N

OCR FAILED

Error: <error_message>
```

## progress.json

`progress.json` is versioned with `schema_version` and `extractor_version`. It stores source identity, page count, pipeline, config hash, resolved config, run ID, status timestamps, failed pages, and page records.

Progress is written before page 1 after startup validation succeeds, then after every page success/failure, then at completion or interruption.

## Dependency Validation

`validate_environment(config)` reports provider availability, missing Python packages, missing binaries, degraded capabilities, fatal blockers, and a summary.

Relevant external binaries:

- `marker_single`
- `ollama`
- `pdftoppm`

Forced fallback fails fast when Ollama tooling is missing. Forced OCR fails fast when Marker is missing. Text-native extraction validates PyMuPDF.

## Concurrency

Different PDFs do not collide because output directories are SHA-256 based. A `.pagewise-extractor.lock` file prevents concurrent runs from sharing the same resolved output directory. For concurrent runs of the same PDF, use `separate_runs=True` or distinct run-scoped output directories.

Atomic progress writes use run-specific temp filenames.

## Package Consumption

Local development:

```powershell
pip install -e D:\Developer\Projects\pagewise-pdf-extractor
```

Pinned GitHub dependency after tagging:

```text
pagewise-pdf-extractor @ git+https://github.com/ebmurha/pagewise-pdf-extractor.git@v0.1.0
```

Manual release work still required:

- confirm package name
- create a release tag or commit SHA for `rag-engine`
- publish to PyPI later only if desired

Operational details are documented in:

- `docs/PACKAGING.md`
- `docs/RELEASE.md`
