"""Markdown output helpers."""

from pathlib import Path

from .models import LayoutArtifact

PAGE_FILENAME_TEMPLATE = "page_{page:04d}.md"
FAILURE_PLACEHOLDER = "OCR FAILED"


def page_filename(page_number: int) -> str:
    return PAGE_FILENAME_TEMPLATE.format(page=page_number)


def write_page_markdown(
    output_dir: Path,
    page_number: int,
    content: str,
    layout_artifacts: list[LayoutArtifact] | None = None,
) -> Path:
    page_path = output_dir / page_filename(page_number)
    body = f"# Page {page_number}\n\n{content.strip()}\n"
    if layout_artifacts:
        body = f"{body}\n{_layout_artifacts_markdown(layout_artifacts, content)}\n"
    page_path.write_text(body, encoding="utf-8")
    return page_path


def write_failure_markdown(output_dir: Path, page_number: int, error_message: str) -> Path:
    page_path = output_dir / page_filename(page_number)
    body = f"# Page {page_number}\n\n{FAILURE_PLACEHOLDER}\n\nError: {error_message}\n"
    page_path.write_text(body, encoding="utf-8")
    return page_path


def _layout_artifacts_markdown(
    layout_artifacts: list[LayoutArtifact],
    page_content: str = "",
) -> str:
    lines = ["## Layout Artifacts", ""]
    for index, artifact in enumerate(layout_artifacts, start=1):
        bbox = f" bbox={list(artifact.to_dict().get('bbox') or [])}" if artifact.bbox else ""
        lines.append(f"- {index}. `{artifact.kind}`{bbox}")
        if artifact.kind == "table" and artifact.text and artifact.text.strip() not in page_content:
            lines.extend(["", artifact.text.strip(), ""])
        elif artifact.kind != "table" and artifact.text:
            lines.append(f"  - text: {artifact.text.strip()}")
    return "\n".join(lines).rstrip()
