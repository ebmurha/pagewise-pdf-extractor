"""Structured models used by the public API and progress file."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import ExtractionConfig


@dataclass(slots=True)
class ProviderAttempt:
    provider: str
    status: str
    characters: int = 0
    duration_seconds: float | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def model_dump(self) -> dict[str, Any]:
        return self.to_dict()


@dataclass(slots=True)
class ProviderCapability:
    provider: str
    available: bool
    missing_python_packages: list[str] = field(default_factory=list)
    missing_binaries: list[str] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)
    fatal: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LayoutArtifact:
    kind: str
    page_number: int
    bbox: tuple[float, float, float, float] | None = None
    text: str | None = None
    rows: list[list[str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.bbox is not None:
            data["bbox"] = [round(value, 3) for value in self.bbox]
        return data

    def model_dump(self) -> dict[str, Any]:
        return self.to_dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LayoutArtifact":
        bbox = data.get("bbox")
        return cls(
            kind=str(data.get("kind", "unknown")),
            page_number=int(data.get("page_number", 0)),
            bbox=tuple(float(value) for value in bbox) if bbox is not None else None,
            text=data.get("text"),
            rows=[list(map(str, row)) for row in data.get("rows", [])],
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(slots=True)
class ProviderResult:
    text: str
    status: str
    characters: int
    metadata: dict[str, Any] = field(default_factory=dict)
    layout_artifacts: list[LayoutArtifact] = field(default_factory=list)


@dataclass(slots=True)
class PageExtractionResult:
    page_number: int
    status: str
    output_file: Path
    characters: int
    duration_seconds: float
    final_provider: str | None
    fallback_used: bool
    attempts: list[ProviderAttempt]
    layout_artifacts: list[LayoutArtifact] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["output_file"] = str(self.output_file)
        data["attempts"] = [attempt.to_dict() for attempt in self.attempts]
        data["layout_artifacts"] = [artifact.to_dict() for artifact in self.layout_artifacts]
        return data

    def model_dump(self) -> dict[str, Any]:
        return self.to_dict()


@dataclass(slots=True)
class ExtractionResult:
    input_pdf: Path
    output_dir: Path
    progress_path: Path
    extractor_version: str
    input_sha256: str
    total_pages: int
    pages: list[PageExtractionResult]
    failed_pages: list[int]
    status: str
    run_id: str
    schema_version: str
    started_at: datetime
    completed_at: datetime | None
    config_hash: str
    config_used: ExtractionConfig

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["input_pdf"] = str(self.input_pdf)
        data["output_dir"] = str(self.output_dir)
        data["progress_path"] = str(self.progress_path)
        data["started_at"] = self.started_at.isoformat()
        data["completed_at"] = self.completed_at.isoformat() if self.completed_at else None
        data["config_used"] = self.config_used.to_dict()
        data["pages"] = [page.to_dict() for page in self.pages]
        return data

    def model_dump(self) -> dict[str, Any]:
        return self.to_dict()


@dataclass(slots=True)
class EnvironmentReport:
    providers: dict[str, ProviderCapability]
    missing_python_packages: list[str] = field(default_factory=list)
    missing_binaries: list[str] = field(default_factory=list)
    degraded_capabilities: list[str] = field(default_factory=list)
    fatal_blockers: list[str] = field(default_factory=list)

    @property
    def has_fatal_errors(self) -> bool:
        return bool(self.fatal_blockers)

    @property
    def summary(self) -> str:
        if not self.fatal_blockers:
            return "Environment validation passed."
        return "; ".join(self.fatal_blockers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "providers": {name: capability.to_dict() for name, capability in self.providers.items()},
            "missing_python_packages": self.missing_python_packages,
            "missing_binaries": self.missing_binaries,
            "degraded_capabilities": self.degraded_capabilities,
            "fatal_blockers": self.fatal_blockers,
            "has_fatal_errors": self.has_fatal_errors,
            "summary": self.summary,
        }
