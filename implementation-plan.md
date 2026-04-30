# Implementation Plan

1. Convert the repository into an installable package named `pagewise-pdf-extractor` with import package `pagewise_pdf_extractor`.
2. Add package metadata, MIT license, version export, CLI entrypoint, and direct dependencies.
3. Add typed config, result models, exceptions, progress handling, and environment validation.
4. Implement provider interfaces for PyMuPDF text extraction, Marker OCR, and Ollama fallback.
5. Implement `process_pdf(input_pdf, output_root, config, run_id, logger)` as the single library API used by the CLI.
6. Use caller-controlled output roots and SHA-256/run-id output directories to avoid same-stem and concurrent run collisions.
7. Write one UTF-8 Markdown file per page and a versioned, atomic `progress.json` after startup and after each page.
8. Preserve page-level failure behavior by writing failure Markdown and returning a partial result instead of aborting the whole document.
9. Keep legacy script names as compatibility wrappers around the package CLI/API and avoid duplicate extraction logic.
10. Replace tests with package-level tests covering API, output layout, progress, routing, validation, fallback, CLI, and compatibility.
11. Update `README.md` and `PDF_TOOL_PROJECT_OVERVIEW.md` to document the new package contract.
12. Run unit tests and editable-install smoke checks; note any manual dependency or publication steps that remain.
