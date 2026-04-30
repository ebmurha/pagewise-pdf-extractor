#!/usr/bin/env python3
"""Legacy compatibility wrapper.

Use `pagewise-pdf-extractor` or `pagewise_pdf_extractor.process_pdf` for new code.
"""

from pathlib import Path

from pagewise_pdf_extractor import ExtractionConfig
from pagewise_pdf_extractor.api import process_pdf as _process_pdf
from pagewise_pdf_extractor.cli import main


def process_pdf(input_pdf: Path, output_root: Path = Path("output")) -> int:
    _process_pdf(input_pdf, output_root, config=ExtractionConfig(force_ocr=True, fallback_enabled=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
