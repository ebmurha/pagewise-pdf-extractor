"""Markdown output helpers."""

from pathlib import Path

PAGE_FILENAME_TEMPLATE = "page_{page:04d}.md"
FAILURE_PLACEHOLDER = "OCR FAILED"


def page_filename(page_number: int) -> str:
    return PAGE_FILENAME_TEMPLATE.format(page=page_number)


def write_page_markdown(output_dir: Path, page_number: int, content: str) -> Path:
    page_path = output_dir / page_filename(page_number)
    page_path.write_text(f"# Page {page_number}\n\n{content.strip()}\n", encoding="utf-8")
    return page_path


def write_failure_markdown(output_dir: Path, page_number: int, error_message: str) -> Path:
    page_path = output_dir / page_filename(page_number)
    body = f"# Page {page_number}\n\n{FAILURE_PLACEHOLDER}\n\nError: {error_message}\n"
    page_path.write_text(body, encoding="utf-8")
    return page_path
