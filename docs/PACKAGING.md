# Package Names

The project uses two names:

- Install name: `pagewise-pdf-extractor`
- Import name: `pagewise_pdf_extractor`

This is normal for Python packages. Package installers use the distribution name, while Python imports must use a valid Python identifier.

## Install Name

Use the hyphenated name with `pip`:

```powershell
python -m pip install pagewise-pdf-extractor
```

For a pinned GitHub install:

```txt
pagewise-pdf-extractor @ git+https://github.com/ebmurha/pagewise-pdf-extractor.git@v0.1.1
```

## Import Name

Use the underscored name in Python code:

```python
from pagewise_pdf_extractor import ExtractionConfig, process_pdf
```

Do not import `pagewise-pdf-extractor` in Python code. Hyphens are not valid in Python module names.

## Command Name

The installed CLI command is:

```powershell
pagewise-pdf-extractor --help
```

## External Tools

The Python package does not bundle external OCR tools or local model servers.

Depending on the configured providers, users may also need:

- `marker_single` for Marker OCR
- `ollama` for Ollama fallback
- `pdftoppm` for rendering pages passed to Ollama

Run the environment check after installation:

```powershell
pagewise-pdf-extractor --validate-environment
```
