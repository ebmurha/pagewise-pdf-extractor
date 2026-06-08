"""Public library API for page-wise PDF extraction."""

from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

from .config import ExtractionConfig
from .environment import validate_environment
from .exceptions import (
    ConfigurationError,
    ConcurrencyError,
    DependencyMissingError,
    InvalidInputError,
    PageExtractionError,
    ProviderError,
)
from .markdown import write_failure_markdown, write_page_markdown
from .models import ExtractionResult, LayoutArtifact, PageExtractionResult, ProviderAttempt, ProviderResult
from .progress import (
    PROGRESS_FILE_NAME,
    SCHEMA_VERSION,
    atomic_write_json,
    build_baseline_progress,
    load_progress,
    page_progress_record,
    progress_matches,
    utc_now,
)
from .providers.marker_ocr import MarkerOCRExtractor
from .providers.ollama_vision import OllamaVisionExtractor
from .providers.pymupdf_text import PyMuPDFTextExtractor

EXTRACTOR_VERSION = "0.3.0"


def process_pdf(
    input_pdf: Path,
    output_root: Path,
    *,
    config: ExtractionConfig | None = None,
    run_id: str | None = None,
    logger: logging.Logger | None = None,
) -> ExtractionResult:
    config = config or ExtractionConfig()
    logger = logger or logging.getLogger(__name__)
    input_pdf = Path(input_pdf).expanduser().resolve()
    output_root = Path(output_root).expanduser().resolve()
    _validate_input(input_pdf)
    _validate_config(config)

    report = validate_environment(config)
    if report.has_fatal_errors:
        raise DependencyMissingError(report.summary)

    input_sha256 = compute_sha256(input_pdf)
    total_pages = get_total_pages(input_pdf)
    config_hash = config.hash()
    run_id = run_id or uuid.uuid4().hex
    output_dir = _resolve_output_dir(output_root, input_sha256, run_id, config)
    output_dir.mkdir(parents=True, exist_ok=True)
    lock_path = _acquire_run_lock(output_dir)
    progress_path = output_dir / PROGRESS_FILE_NAME
    started_at = utc_now()

    try:
        progress = load_progress(progress_path) if config.resume else None
        if progress and progress_matches(
            progress,
            input_pdf=input_pdf,
            input_sha256=input_sha256,
            total_pages=total_pages,
            config_hash=config_hash,
            extractor_version=EXTRACTOR_VERSION,
        ):
            start_page = int(progress.get("last_completed_page", 0)) + 1
            run_id = str(progress.get("run_id", run_id))
        else:
            progress = build_baseline_progress(
                input_pdf=input_pdf,
                input_sha256=input_sha256,
                total_pages=total_pages,
                extractor_version=EXTRACTOR_VERSION,
                config=config,
                config_hash=config_hash,
                run_id=run_id,
                started_at=started_at,
            )
            atomic_write_json(progress_path, progress, run_id)
            start_page = 1

        pages: list[PageExtractionResult] = _pages_from_progress(progress)

        for page_number in range(start_page, total_pages + 1):
            page_result = _process_page(input_pdf, output_dir, page_number, total_pages, config, logger)
            pages = [page for page in pages if page.page_number != page_number]
            pages.append(page_result)
            progress["last_completed_page"] = page_number
            if page_result.status == "failed":
                if page_number not in progress["failed_pages"]:
                    progress["failed_pages"].append(page_number)
            elif page_number in progress["failed_pages"]:
                progress["failed_pages"].remove(page_number)
            progress["pages"][str(page_number)] = page_progress_record(page_result)
            atomic_write_json(progress_path, progress, run_id)
            if config.fail_fast and page_result.status == "failed":
                break
    except KeyboardInterrupt:
        progress["status"] = "interrupted"
        atomic_write_json(progress_path, progress, run_id)
        raise
    finally:
        _release_run_lock(lock_path)

    pages.sort(key=lambda page: page.page_number)
    failed_pages = sorted(page.page_number for page in pages if page.status == "failed")
    completed_at = utc_now()
    if failed_pages and len(failed_pages) == total_pages:
        status = "failed"
    elif failed_pages:
        status = "partial_failure"
    else:
        status = "ok"
    progress["status"] = status
    progress["failed_pages"] = failed_pages
    progress["completed_at"] = completed_at.isoformat()
    atomic_write_json(progress_path, progress, run_id)

    return ExtractionResult(
        input_pdf=input_pdf,
        output_dir=output_dir,
        progress_path=progress_path,
        extractor_version=EXTRACTOR_VERSION,
        input_sha256=input_sha256,
        total_pages=total_pages,
        pages=pages,
        failed_pages=failed_pages,
        status=status,
        run_id=run_id,
        schema_version=SCHEMA_VERSION,
        started_at=started_at,
        completed_at=completed_at,
        config_hash=config_hash,
        config_used=config,
    )


def compute_sha256(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as file_obj:
        while True:
            chunk = file_obj.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def get_total_pages(pdf_path: Path) -> int:
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(pdf_path))
        pages = len(reader.pages)
    except Exception as exc:
        raise InvalidInputError(f"Unable to read PDF pages from {pdf_path}: {exc}") from exc
    if pages <= 0:
        raise InvalidInputError(f"Unable to determine total pages for {pdf_path}")
    return pages


def _process_page(
    input_pdf: Path,
    output_dir: Path,
    page_number: int,
    total_pages: int,
    config: ExtractionConfig,
    logger: logging.Logger,
) -> PageExtractionResult:
    start = time.perf_counter()
    attempts: list[ProviderAttempt] = []

    try:
        final = _extract_page_with_providers(input_pdf, page_number, total_pages, config, attempts)
        duration = round(time.perf_counter() - start, 3)
        page_path = write_page_markdown(output_dir, page_number, final.text, final.layout_artifacts)
        status = _page_status(final, attempts)
        logger.info(
            "page extraction complete",
            extra={
                "page": page_number,
                "provider": attempts[-1].provider if attempts else None,
                "status": status,
                "duration_seconds": duration,
                "characters": final.characters,
            },
        )
        return PageExtractionResult(
            page_number=page_number,
            status=status,
            output_file=page_path,
            characters=final.characters,
            duration_seconds=duration,
            final_provider=attempts[-1].provider if attempts else None,
            fallback_used=any(attempt.provider == config.fallback_provider and attempt.status == "ok" for attempt in attempts),
            attempts=attempts,
            layout_artifacts=final.layout_artifacts,
        )
    except PageExtractionError as exc:
        duration = round(time.perf_counter() - start, 3)
        page_path = write_failure_markdown(output_dir, page_number, str(exc))
        logger.error(
            "page extraction failed",
            extra={
                "page": page_number,
                "provider": None,
                "status": "failed",
                "duration_seconds": duration,
                "characters": 0,
            },
        )
        return PageExtractionResult(
            page_number=page_number,
            status="failed",
            output_file=page_path,
            characters=0,
            duration_seconds=duration,
            final_provider=None,
            fallback_used=any(attempt.provider == config.fallback_provider for attempt in attempts),
            attempts=attempts,
            error=str(exc),
        )


def _extract_page_with_providers(
    input_pdf: Path,
    page_number: int,
    total_pages: int,
    config: ExtractionConfig,
    attempts: list[ProviderAttempt],
) -> ProviderResult:
    if config.force_fallback:
        attempts.append(ProviderAttempt(config.text_provider, "skipped", error="force_fallback"))
        attempts.append(ProviderAttempt(config.ocr_provider, "skipped", error="force_fallback"))
        return _run_provider(OllamaVisionExtractor(), input_pdf, page_number, total_pages, config, attempts, accept_status="ollama_ok")

    if not config.force_ocr:
        text_result = _run_provider(
            PyMuPDFTextExtractor(),
            input_pdf,
            page_number,
            total_pages,
            config,
            attempts,
            accept_status="text_ok",
            raise_on_reject=False,
        )
        if text_result is not None and text_result.status == "text_ok":
            return text_result

    marker_result = _run_provider(
        MarkerOCRExtractor(),
        input_pdf,
        page_number,
        total_pages,
        config,
        attempts,
        accept_status="marker_ok",
        raise_on_reject=False,
    )
    if marker_result is not None and marker_result.status == "marker_ok":
        return marker_result

    if config.fallback_enabled and config.fallback_provider == "ollama":
        return _run_provider(
            OllamaVisionExtractor(),
            input_pdf,
            page_number,
            total_pages,
            config,
            attempts,
            accept_status="ollama_ok",
        )

    raise PageExtractionError(f"No provider produced usable output for page {page_number}.", attempts)


def _run_provider(
    provider,
    input_pdf: Path,
    page_number: int,
    total_pages: int,
    config: ExtractionConfig,
    attempts: list[ProviderAttempt],
    *,
    accept_status: str,
    raise_on_reject: bool = True,
) -> ProviderResult | None:
    start = time.perf_counter()
    try:
        result = provider.extract_page(input_pdf, page_number, total_pages, config)
        duration = round(time.perf_counter() - start, 3)
        ok = result.status == accept_status
        attempts.append(
            ProviderAttempt(
                provider=provider.name,
                status="ok" if ok else "low_quality",
                characters=result.characters,
                duration_seconds=duration,
                metadata={"provider_status": result.status, **result.metadata},
            )
        )
        if ok:
            return result
        if raise_on_reject:
            raise PageExtractionError(f"{provider.name} output rejected as {result.status}.", attempts)
        return result
    except PageExtractionError:
        raise
    except Exception as exc:
        duration = round(time.perf_counter() - start, 3)
        attempts.append(
            ProviderAttempt(
                provider=provider.name,
                status="failed",
                characters=0,
                duration_seconds=duration,
                error=str(exc)[:300],
            )
        )
        if raise_on_reject:
            raise PageExtractionError(f"{provider.name} failed for page {page_number}.", attempts) from exc
        return None


def _page_status(final: ProviderResult, attempts: list[ProviderAttempt]) -> str:
    if not attempts:
        return "failed"
    if attempts[-1].provider == "ollama":
        return "fallback_ok"
    if any(attempt.status == "low_quality" for attempt in attempts[:-1]):
        return "low_text_warning"
    return "ok"


def _validate_input(input_pdf: Path) -> None:
    if not input_pdf.exists() or not input_pdf.is_file():
        raise InvalidInputError(f"Input PDF not found: {input_pdf}")
    if input_pdf.suffix.lower() != ".pdf":
        raise InvalidInputError(f"Input file is not a PDF: {input_pdf}")


def _validate_config(config: ExtractionConfig) -> None:
    if config.output_format != "markdown":
        raise ConfigurationError("Only markdown output is currently supported.")
    if config.text_provider != "pymupdf":
        raise ConfigurationError("Only text_provider='pymupdf' is currently supported.")
    if config.ocr_provider != "marker":
        raise ConfigurationError("Only ocr_provider='marker' is currently supported.")
    if config.fallback_provider not in (None, "ollama"):
        raise ConfigurationError("Only fallback_provider=None or 'ollama' is currently supported.")
    if config.force_fallback and config.fallback_provider != "ollama":
        raise ConfigurationError("force_fallback requires fallback_provider='ollama'.")
    if config.marker_render_dpi < 72:
        raise ConfigurationError("marker_render_dpi must be at least 72.")


def _resolve_output_dir(output_root: Path, input_sha256: str, run_id: str, config: ExtractionConfig) -> Path:
    if config.separate_runs:
        return output_root / input_sha256 / run_id
    return output_root / input_sha256


def _acquire_run_lock(output_dir: Path) -> Path:
    lock_path = output_dir / ".pagewise-extractor.lock"
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as lock_file:
            lock_file.write(str(os.getpid()))
    except FileExistsError as exc:
        raise ConcurrencyError(f"Extraction output is already locked: {output_dir}") from exc
    return lock_path


def _release_run_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink(missing_ok=True)
    except Exception:
        pass


def _pages_from_progress(progress: dict) -> list[PageExtractionResult]:
    pages = []
    for raw_page, record in progress.get("pages", {}).items():
        attempts = [ProviderAttempt(**attempt) for attempt in record.get("attempts", [])]
        layout_artifacts = [
            LayoutArtifact.from_dict(artifact) for artifact in record.get("layout_artifacts", [])
        ]
        pages.append(
            PageExtractionResult(
                page_number=int(raw_page),
                status=record.get("status", "failed"),
                output_file=Path(record.get("output_file", "")),
                characters=int(record.get("characters", 0)),
                duration_seconds=float(record.get("duration_seconds", 0)),
                final_provider=record.get("final_provider"),
                fallback_used=bool(record.get("fallback_used", False)),
                attempts=attempts,
                layout_artifacts=layout_artifacts,
                error=record.get("error"),
            )
        )
    return pages
