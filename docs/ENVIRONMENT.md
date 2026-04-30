# Environment and Provider Setup

This package separates Python installation from external OCR tooling. Text-native extraction only needs Python dependencies. OCR and fallback paths need local binaries.

## Install Python Package

Development install:

```powershell
python -m pip install -e .
```

Consumer repo local install:

```powershell
python -m pip install -e D:\Developer\Projects\pagewise-pdf-extractor
```

Pinned GitHub install:

```txt
pagewise-pdf-extractor @ git+https://github.com/ebmurha/pagewise-pdf-extractor.git@v0.1.0
```

## Validate Environment

CLI:

```powershell
pagewise-pdf-extractor --validate-environment
```

Python:

```python
from pagewise_pdf_extractor import ExtractionConfig, validate_environment

report = validate_environment(ExtractionConfig())
print(report.summary)
```

Use forced modes to validate a specific path:

```powershell
pagewise-pdf-extractor --validate-environment --force-ocr
pagewise-pdf-extractor --validate-environment --force-fallback
```

## Provider Requirements

PyMuPDF text extraction:

- Python package: `PyMuPDF`

Marker OCR:

- Python package: `marker-pdf`
- Binary on `PATH`: `marker_single`

Ollama fallback:

- Binary on `PATH`: `ollama`
- Binary on `PATH`: `pdftoppm`
- Local Ollama model available, for example `deepseek-ocr`

## Application UX Recommendation

Applications should call `validate_environment(config)` during setup or before an extraction run and display the report to operators.

Recommended behavior:

- fatal blockers: stop and show setup instructions
- degraded fallback: warn but allow text-native extraction
- missing optional provider: record degraded capability

Do not wait for a page extraction failure to tell users that `marker_single`, `ollama`, or `pdftoppm` is missing.
