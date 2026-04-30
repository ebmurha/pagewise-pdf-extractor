# Contributing

Thanks for helping maintain `pagewise-pdf-extractor`.

## Development Setup

```powershell
python -m pip install -e .
```

Validate the package:

```powershell
python -m unittest discover -s tests -p "test_*.py"
python -c "from pagewise_pdf_extractor import ExtractionConfig, process_pdf, validate_environment; print('ok')"
pagewise-pdf-extractor --help
```

Provider-specific checks:

```powershell
pagewise-pdf-extractor --validate-environment
pagewise-pdf-extractor --validate-environment --force-ocr
pagewise-pdf-extractor --validate-environment --force-fallback
```

## Code Organization

- `src/pagewise_pdf_extractor/`: package code
- `src/pagewise_pdf_extractor/providers/`: extraction providers
- `tests/`: unit tests
- `docs/`: developer and integration documentation

Do not add new root-level executable scripts for extraction paths. Add provider behavior behind the package API and document the configuration.

## Pull Request Expectations

- Keep public API changes intentional and documented.
- Add or update tests for behavior changes.
- Update `README.md`, `docs/`, and `CHANGELOG.md` when user-facing behavior changes.
- Avoid logging full document content.
- Keep provider dependencies explicit and discoverable through `validate_environment()`.

## Release Changes

Follow [docs/RELEASE.md](docs/RELEASE.md). Consumers should pin immutable tags, not `main`.
