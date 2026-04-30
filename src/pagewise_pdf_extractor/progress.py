"""Atomic progress.json management."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import ExtractionConfig
from .exceptions import ProgressError
from .models import PageExtractionResult

SCHEMA_VERSION = "1.0"
PROGRESS_FILE_NAME = "progress.json"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def atomic_write_json(path: Path, data: dict[str, Any], run_id: str) -> None:
    try:
        data["updated_at"] = utc_now().isoformat()
        tmp_path = path.with_name(f"{path.name}.{run_id}.tmp")
        with tmp_path.open("w", encoding="utf-8") as file_obj:
            json.dump(data, file_obj, indent=2)
        os.replace(tmp_path, path)
    except Exception as exc:
        raise ProgressError(f"Unable to write progress file {path}: {exc}") from exc


def load_progress(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ProgressError(f"Unable to read progress file {path}: {exc}") from exc


def build_baseline_progress(
    *,
    input_pdf: Path,
    input_sha256: str,
    total_pages: int,
    extractor_version: str,
    config: ExtractionConfig,
    config_hash: str,
    run_id: str,
    started_at: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "extractor_version": extractor_version,
        "input_file": str(input_pdf.resolve()),
        "input_file_name": input_pdf.name,
        "input_sha256": input_sha256,
        "total_pages": total_pages,
        "pipeline": {
            "text_provider": config.text_provider,
            "ocr_provider": config.ocr_provider,
            "fallback_provider": config.fallback_provider,
        },
        "config_hash": config_hash,
        "config_used": config.to_dict(),
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "updated_at": started_at.isoformat(),
        "completed_at": None,
        "status": "running",
        "last_completed_page": 0,
        "failed_pages": [],
        "pages": {},
    }


def progress_matches(
    progress: dict[str, Any],
    *,
    input_pdf: Path,
    input_sha256: str,
    total_pages: int,
    config_hash: str,
    extractor_version: str,
) -> bool:
    return (
        progress.get("input_file") == str(input_pdf.resolve())
        and progress.get("input_sha256") == input_sha256
        and progress.get("total_pages") == total_pages
        and progress.get("config_hash") == config_hash
        and progress.get("extractor_version") == extractor_version
        and progress.get("schema_version") == SCHEMA_VERSION
    )


def page_progress_record(page: PageExtractionResult) -> dict[str, Any]:
    return {
        "status": page.status,
        "characters": page.characters,
        "duration_seconds": page.duration_seconds,
        "output_file": str(page.output_file),
        "processed_at": utc_now().isoformat(),
        "final_provider": page.final_provider,
        "fallback_used": page.fallback_used,
        "attempts": [attempt.to_dict() for attempt in page.attempts],
        **({"error": page.error} if page.error else {}),
    }
