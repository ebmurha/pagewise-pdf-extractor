#!/usr/bin/env python3
"""Compatibility wrapper for the packaged pagewise-pdf-extractor CLI."""

from pagewise_pdf_extractor.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
