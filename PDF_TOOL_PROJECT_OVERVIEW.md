# OCR Tool Project Overview

## 1. Folder and File Structure

Current tracked project files:

```text
ocr-tool/
  .aiignore
  .env
  .env.example
  .gitignore
  README.md
  ocr_providers.py
  ocr_tool.py
  pdf_ocr_marker.py
  requirements.txt
  output/
  tests/
    test_ocr_tool.py
    test_pdf_ocr_marker.py
```

Main files:

- `ocr_tool.py`: current main OCR pipeline. It runs Marker first and falls back to Ollama per page.
- `ocr_providers.py`: provider implementations for Marker, Ollama, PDF page counting, environment checks, and model cache inspection.
- `pdf_ocr_marker.py`: older/simple Marker-only OCR pipeline.
- `tests/`: unit tests for both pipelines.
- `output/`: generated OCR output root. Each processed PDF gets its own subfolder here.

## 2. Inputs

The current main pipeline takes a single PDF file path as its required input:

```bash
python ocr_tool.py /path/to/file.pdf
```

It does not take a folder of PDFs. It processes one PDF at a time.

Optional CLI inputs:

```bash
python ocr_tool.py /path/to/file.pdf --ollama-model deepseek-ocr
python ocr_tool.py /path/to/file.pdf --force-ollama-fallback
```

Configuration:

- `.env` is loaded if present.
- `.env.example` documents the optional `MODEL_CACHE_DIR` setting.
- `MODEL_CACHE_DIR` controls where Marker/Surya model files are cached.
- If `MODEL_CACHE_DIR` is unset, Marker uses its default cache location.

Environment/tooling inputs:

- `marker_single` must be on `PATH` for Marker OCR.
- `ollama` must be on `PATH` for fallback OCR.
- `pdftoppm` must be on `PATH` for Ollama fallback because the PDF page is rendered to PNG first.

## 3. Outputs

The main output location is:

```text
output/<pdf_stem>/
```

For example, processing `document.pdf` writes to:

```text
output/document/
  page_0001.md
  page_0002.md
  page_0003.md
  progress.json
  run.log
```

Page Markdown naming convention:

```text
page_<4-digit-page-number>.md
```

Examples:

- `page_0001.md`
- `page_0002.md`
- `page_0010.md`

Successful page Markdown content looks like:

```markdown
# Page 1

<OCR markdown content from Marker or Ollama>
```

Failed page Markdown content looks like:

```markdown
# Page 2

OCR FAILED

Error: Marker and Ollama both failed for page 2.
```

Metadata/progress file:

- `progress.json` is written alongside the page Markdown files.
- It records the input PDF path, filename, SHA-256 hash, page count, completed page, failed pages, pipeline mode, Ollama model, force-fallback flag, and per-page status.

Representative `progress.json` shape:

```json
{
  "input_file": "D:\\path\\to\\document.pdf",
  "input_file_name": "document.pdf",
  "input_sha256": "<sha256>",
  "total_pages": 3,
  "last_completed_page": 3,
  "failed_pages": [],
  "pages": {
    "1": {
      "status": "ok",
      "characters": 1234,
      "duration_seconds": 4.321,
      "output_file": "page_0001.md",
      "processed_at": "2026-04-29T00:00:00+00:00",
      "final_provider": "marker",
      "fallback_used": false,
      "attempts": [
        {
          "provider": "marker",
          "status": "ok",
          "characters": 1234
        }
      ]
    }
  },
  "pipeline": "marker_with_ollama_fallback",
  "ollama_model": "deepseek-ocr",
  "force_ollama_fallback": false,
  "updated_at": "2026-04-29T00:00:00+00:00"
}
```

Log file:

- `run.log` is written alongside the output.
- It contains terminal-style progress events and structured fields such as page number, total pages, duration, character count, and status.

## 4. Invocation

Primary CLI:

```bash
python ocr_tool.py /path/to/file.pdf
```

With explicit Ollama fallback model:

```bash
python ocr_tool.py /path/to/file.pdf --ollama-model deepseek-ocr
```

Force the Ollama fallback path for every page:

```bash
python ocr_tool.py /path/to/file.pdf --force-ollama-fallback
```

The code can also be imported from Python. The main callable is:

```python
from pathlib import Path
from ocr_tool import process_pdf

exit_code = process_pdf(
    Path("document.pdf"),
    ollama_model="deepseek-ocr",
    force_ollama_fallback=False,
)
```

The older Marker-only pipeline can be invoked as:

```bash
python pdf_ocr_marker.py /path/to/file.pdf
```

And imported as:

```python
from pathlib import Path
from pdf_ocr_marker import process_pdf

exit_code = process_pdf(Path("document.pdf"))
```

## 5. Dependencies

Python dependencies in `requirements.txt`:

```text
marker-pdf
pypdf
tqdm
python-json-logger
python-dotenv
```

External command-line dependencies used by the current pipeline:

- `marker_single`: installed/provided by `marker-pdf`.
- `ollama`: used for fallback OCR.
- `pdftoppm`: used to render individual PDF pages to PNG for Ollama fallback.

There is no `pyproject.toml` in the current project.
