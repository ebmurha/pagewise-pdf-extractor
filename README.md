# Book OCR Tool

A local CLI that OCRs a PDF book page-by-page, writes one Markdown file per page, runs Marker first, and falls back to Ollama only when Marker fails on a page.

## Install

```bash
pip install -r requirements.txt
```

## Optional Configuration

Copy `.env.example` to `.env` and set `MODEL_CACHE_DIR` only if you want Marker models stored outside the default cache path.

If `MODEL_CACHE_DIR` is unset, the tool leaves Marker on its default cache location under `%LOCALAPPDATA%\datalab\datalab\Cache\models`.

## Usage

```bash
python ocr_tool.py /path/to/book.pdf [--ollama-model deepseek-ocr]
```

To test the fallback path directly without depending on Marker failure:

```bash
python ocr_tool.py /path/to/book.pdf --force-ollama-fallback
```

On Windows PowerShell with an override cache path:

```powershell
$env:MODEL_CACHE_DIR = 'D:\DevTools\marker-model-cache'
python ocr_tool.py sample.pdf --force-ollama-fallback
```

## Output Layout

```text
output/
  book_name/
    page_0001.md
    page_0002.md
    ...
    progress.json
    run.log
```

## Behavior

- Sequential page processing
- Resume support via `progress.json`
- Terminal + persistent log observability
- Per-page timing, character count, low-text warnings
- Failure placeholders (`OCR FAILED`) while continuing pipeline
- SHA-256 input validation to prevent resume against the wrong file
- Marker cache is inspected locally at startup without launching an extra Marker OCR pass
- Marker OCR runs first on every page
- Ollama OCR is used only as fallback when Marker fails or returns unusable output
- `--force-ollama-fallback` skips Marker and sends pages directly through the Ollama fallback path for testing
- `progress.json` records which provider ultimately handled each page

## Notes

- The pipeline requires `marker_single` on `PATH` (installed with `marker-pdf`).
- The fallback requires `ollama` and `pdftoppm` on `PATH`.
- Marker/Surya model cache can be redirected by setting `MODEL_CACHE_DIR`, for example `D:\DevTools\marker-model-cache`.
- If `MODEL_CACHE_DIR` is not set, the default Marker cache path is used automatically.
- On a cold cache, Marker downloads missing models during the first real OCR page run, not during a separate startup preflight.
- Output stays under `output/`; there is no separate LLM output folder.
- Processing is local; internet may only be needed for first-time package/model setup.

## Run Tests

```bash
python -m unittest discover -s tests -p "test_*.py"
```
