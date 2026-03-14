# Book OCR Tool

A local CLI that OCRs a PDF book page-by-page via `marker_single` and writes one Markdown file per page.

## Install

```bash
pip install -r requirements.txt
```

## Usage

```bash
python ocr_book.py /path/to/book.pdf
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

## Notes

- The script requires `marker_single` on `PATH` (installed with `marker-pdf`).
- Processing is local; internet may only be needed for first-time package/model setup.

## Run Tests

```bash
python -m unittest discover -s tests -p "test_*.py"
```
