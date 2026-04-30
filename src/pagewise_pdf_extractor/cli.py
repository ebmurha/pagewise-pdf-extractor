"""Command-line entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .api import process_pdf
from .config import ExtractionConfig
from .environment import validate_environment
from .exceptions import ExtractionError, InvalidInputError
from .models import EnvironmentReport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract a PDF into page-wise Markdown.")
    parser.add_argument("input_pdf", nargs="?", help="Path to the source PDF file")
    parser.add_argument("--output-root", default="output", help="Directory where extraction outputs are written")
    parser.add_argument("--ollama-model", default="deepseek-ocr", help="Ollama model used for fallback OCR")
    parser.add_argument("--ollama-endpoint", default=None, help="Optional Ollama endpoint/host")
    parser.add_argument("--marker-model-cache-dir", default=None, help="Optional Marker model cache directory")
    parser.add_argument("--force-ocr", action="store_true", help="Skip embedded text extraction and use OCR")
    parser.add_argument("--force-fallback", "--force-ollama-fallback", action="store_true", help="Use fallback OCR on every page")
    parser.add_argument("--no-fallback", action="store_true", help="Disable fallback OCR")
    parser.add_argument("--min-text-chars", type=int, default=50, help="Minimum chars for accepting embedded text")
    parser.add_argument("--min-ocr-chars", type=int, default=20, help="Minimum chars for accepting OCR output")
    parser.add_argument("--render-dpi", type=int, default=200, help="DPI used when rendering pages for fallback OCR")
    parser.add_argument("--separate-runs", action="store_true", help="Write output under <sha256>/<run_id>")
    parser.add_argument("--validate-environment", action="store_true", help="Validate providers and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = ExtractionConfig(
        fallback_enabled=not args.no_fallback,
        force_ocr=args.force_ocr,
        force_fallback=args.force_fallback,
        min_text_chars=args.min_text_chars,
        min_ocr_chars=args.min_ocr_chars,
        marker_model_cache_dir=Path(args.marker_model_cache_dir) if args.marker_model_cache_dir else None,
        ollama_model=args.ollama_model,
        ollama_endpoint=args.ollama_endpoint,
        render_dpi=args.render_dpi,
        separate_runs=args.separate_runs,
    )

    if args.validate_environment:
        report = validate_environment(config)
        print(_format_environment_report(report))
        return 1 if report.has_fatal_errors else 0

    if not args.input_pdf:
        parser.error("input_pdf is required unless --validate-environment is used")

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    try:
        result = process_pdf(Path(args.input_pdf), Path(args.output_root), config=config)
    except KeyboardInterrupt:
        return 130
    except InvalidInputError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ExtractionError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"status={result.status} output_dir={result.output_dir}")
    return 0


def _format_environment_report(report: EnvironmentReport) -> str:
    lines = ["Environment report:"]
    for name, capability in report.providers.items():
        state = "available" if capability.available else "missing"
        lines.append(f"- {name}: {state}")
        if capability.missing_python_packages:
            lines.append(f"  missing Python packages: {', '.join(capability.missing_python_packages)}")
        if capability.missing_binaries:
            lines.append(f"  missing binaries: {', '.join(capability.missing_binaries)}")
        for item in capability.degraded:
            lines.append(f"  degraded: {item}")
        for item in capability.fatal:
            lines.append(f"  fatal: {item}")
    lines.append(f"summary: {report.summary}")
    if report.missing_binaries:
        lines.append("install hints:")
        if "marker_single" in report.missing_binaries:
            lines.append("- marker_single: install marker-pdf and ensure the scripts directory is on PATH.")
        if "ollama" in report.missing_binaries:
            lines.append("- ollama: install Ollama and ensure the ollama executable is on PATH.")
        if "pdftoppm" in report.missing_binaries:
            lines.append("- pdftoppm: install Poppler and ensure its bin directory is on PATH.")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
