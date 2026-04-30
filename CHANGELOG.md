# Changelog

## v0.1.0

First valid integration release.

- Converted the project into installable package `pagewise-pdf-extractor`.
- Added import package `pagewise_pdf_extractor`.
- Added public library API with `process_pdf()`, `ExtractionConfig`, `ExtractionResult`, and `validate_environment()`.
- Added CLI entrypoint `pagewise-pdf-extractor`.
- Added PyMuPDF embedded-text provider.
- Added Marker OCR provider.
- Added Ollama fallback provider.
- Added structured result models, typed exceptions, progress schema, and Markdown output contract.
- Added SHA-256 output directory isolation and same-output locking.
- Added developer-facing package documentation:
  - API reference
  - configuration reference
  - environment/provider setup
  - downstream integration guide
  - packaging and release process
- Removed legacy root-level script shims and duplicate dependency files.
- Archived implementation handoff documents outside tracked package documentation.
- Added MIT license and package metadata.
