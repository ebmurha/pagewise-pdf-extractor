# Packaging and Naming Guide

## Names

Use both names, for different purposes:

- Distribution name: `pagewise-pdf-extractor`
- Import package name: `pagewise_pdf_extractor`

This is the standard Python convention. Distribution/project names are what users install with `pip`, and they are commonly normalized with hyphens. Import package names must be valid Python identifiers, so they use underscores.

Examples:

```powershell
pip install pagewise-pdf-extractor
```

```python
from pagewise_pdf_extractor import ExtractionConfig, process_pdf
```

Do not change the import package to use hyphens; Python imports cannot use them.

## Local Development Install

From this repository:

```powershell
python -m pip install -e .
```

From another repository such as `rag-engine`:

```powershell
python -m pip install -e D:\Developer\Projects\pagewise-pdf-extractor
```

This installs the package in editable mode and installs declared Python dependencies.

For a packaging-only smoke test, maintainers may use:

```powershell
python -m pip install -e . --no-deps
```

That only verifies this package metadata and import wiring. It does not install runtime dependencies and should not be used as the normal setup command.

## Runtime Dependency Checks

After installation, run:

```powershell
pagewise-pdf-extractor --validate-environment
```

The report lists provider availability, missing Python packages, missing external binaries, degraded capabilities, fatal blockers, and install hints.

External binaries are intentionally not bundled inside the Python wheel:

- `marker_single`: required for Marker OCR
- `ollama`: required for Ollama fallback
- `pdftoppm`: required to render pages for Ollama fallback

This package exposes those requirements through `validate_environment()` so applications can show their own setup guidance instead of failing deep inside an extraction run.

```python
from pagewise_pdf_extractor import ExtractionConfig, validate_environment

report = validate_environment(ExtractionConfig(force_ocr=True))
if report.has_fatal_errors:
    raise RuntimeError(report.summary)
```

## Metadata

Package metadata lives in `pyproject.toml`.

Current release identity:

- version: `0.1.0`
- license: `MIT`
- CLI entrypoint: `pagewise-pdf-extractor = "pagewise_pdf_extractor.cli:main"`

Keep the version in sync with release tags.
