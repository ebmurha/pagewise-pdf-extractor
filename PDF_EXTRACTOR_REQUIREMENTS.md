# PDF Extraction Package Requirements for RAG Integration

Audience: team responsible for the current `ocr-tool-main` project.

This document is the complete authority for what must be done to this PDF extraction package before `rag-engine` consumes it. If another note, chat message, README, or older plan conflicts with this file, this file wins unless the human explicitly updates it.

This file is a handoff contract. It tells the extractor-package team what must be completed before `rag-engine` consumes this package as a dependency.

`rag-engine` will not own or implement these changes. The extractor package must be made complete, tested, packaged, versioned, and released independently first.

## 1. Product Goal

Build a standalone Python package for converting PDFs into page-wise Markdown with reliable metadata, progress tracking, and provider-level observability.

The package must handle:

- text-native PDFs
- scanned/image PDFs
- mixed PDFs containing both text and scanned pages
- provider failure and fallback
- resumable extraction
- deterministic output contracts for downstream RAG ingestion

The package is not a RAG tool. It is a reusable PDF extraction/OCR library.

## 2. Package Identity

Proposed names:

- PyPI/distribution name: `pagewise-pdf-extractor`
- Python import name: `pagewise_pdf_extractor`

Confirm or override before implementation. Once confirmed, apply consistently in:

- package metadata
- imports
- README
- tests
- CLI entrypoints
- release notes

Do not use a name tied to `rag-engine`.

## 3. Responsibility Split

The human/operator is only expected to do manual repository/account actions:

- confirm or override the final package name
- rename the GitHub repository if the final name is accepted
- update local git remote URLs if needed
- confirm when the package is ready for PyPI publication after the API stabilizes

Current public repository:

- `https://github.com/ebmurha/pagewise-pdf-extractor`

Distribution strategy:

- initial consumption by `rag-engine`: GitHub dependency pinned to a tag or commit SHA
- do not depend on the moving `main` branch
- PyPI publication is optional later, after the public API is stable
- no PyPI release is required before `rag-engine` begins using the package

Everything else is implementation work for the extractor package team and must be completed in this package repository:

- restructure the project into an installable Python package
- add and maintain `pyproject.toml`
- add an MIT `LICENSE` file
- declare the MIT license in package metadata
- move source under `src/pagewise_pdf_extractor/`
- rename modules/imports to `pagewise_pdf_extractor`
- add the `pagewise-pdf-extractor` CLI entrypoint
- implement PyMuPDF text-native extraction
- harden Marker scanned-page OCR
- make Ollama/fallback OCR configurable
- implement provider interfaces
- implement extraction config models
- implement structured result models
- implement typed exceptions
- implement environment validation
- implement caller-controlled output paths
- implement safe output directory naming
- implement progress writing and schema/versioning
- implement concurrency behavior or locking
- implement logging suitable for library use
- consolidate `ocr_tool.py` and `pdf_ocr_marker.py`
- add/update tests
- update README and release documentation
- verify editable install
- prepare package release/versioning

`rag-engine` must not implement these package responsibilities.

## 4. Required Package Shape

Convert the current flat script layout into a real Python package.

Target shape:

```text
pagewise-pdf-extractor/
  pyproject.toml
  README.md
  CHANGELOG.md
  src/
    pagewise_pdf_extractor/
      __init__.py
      api.py
      config.py
      models.py
      exceptions.py
      progress.py
      markdown.py
      cli.py
      providers/
        __init__.py
        base.py
        pymupdf_text.py
        marker_ocr.py
        ollama_vision.py
  tests/
```

Expose:

- library API for application use
- CLI for standalone use

Do not require callers to import from script files like `ocr_tool.py`.

## 5. Extraction Strategy

The package must select the best extraction path per page, not only per document.

Required default pipeline:

1. Detect whether a page has usable embedded text.
2. If usable embedded text exists, extract text directly with a text extractor.
3. If embedded text is absent or below quality threshold, use OCR.
4. If primary OCR fails or returns unusable output, use configurable fallback OCR.
5. Write one Markdown file per page plus `progress.json`.

### 5.1 Text-Native PDF Extraction

Add a text extraction provider.

This is a new capability. The current `ocr_tool.py` implementation does not include a PyMuPDF/text-native extraction path; it is Marker + Ollama fallback only.

Preferred default:

- PyMuPDF (`fitz`)

Requirements:

- extract embedded text page by page
- preserve basic reading order where possible
- preserve page numbers
- return enough metadata to explain why the text path was accepted or rejected
- allow quality threshold configuration
- do not OCR a text-native page if text extraction is good enough

Quality checks should include at least:

- minimum character count
- non-whitespace ratio
- optional language/script sanity checks if easy
- configurable threshold

Provider output status examples:

- `text_ok`
- `text_low_quality`
- `text_empty`
- `text_error`

### 5.2 Scanned PDF Extraction

Keep Marker as the primary OCR/layout extractor by default.

Requirements:

- call Marker per page or through a reliable page-specific path
- capture Marker stdout/stderr into structured attempts
- preserve Marker Markdown body under the package's page wrapper
- expose Marker configuration in package config
- validate Marker availability before it is required
- document first-run model download/cache behavior

Provider output status examples:

- `marker_ok`
- `marker_empty`
- `marker_low_quality`
- `marker_error`

### 5.3 OCR Fallback

Keep Ollama vision OCR as the default fallback initially, but make fallback provider configurable.

Requirements:

- configurable fallback provider
- configurable Ollama endpoint if supported
- configurable Ollama model
- configurable prompt/template
- configurable render DPI/format for image conversion
- support forced fallback mode for tests and diagnostics
- validate fallback dependencies before forced fallback starts

The package must not hardcode a single model as the only supported fallback path.

Provider output status examples:

- `ollama_ok`
- `ollama_empty`
- `ollama_low_quality`
- `ollama_error`

### 5.4 Mixed Documents

Mixed documents must be handled per page:

- text page -> text extractor
- scanned page -> Marker
- Marker failure -> fallback OCR

The final output must record the final provider per page.

## 6. Configuration

Add an explicit config model.

Equivalent shape:

```python
ExtractionConfig:
  text_provider: str = "pymupdf"
  ocr_provider: str = "marker"
  fallback_provider: str | None = "ollama"
  fallback_enabled: bool = True
  force_ocr: bool = False
  force_fallback: bool = False
  min_text_chars: int = 50
  min_ocr_chars: int = 20
  output_format: str = "markdown"
  marker_model_cache_dir: Path | None = None
  ollama_model: str = "deepseek-ocr"
  ollama_endpoint: str | None = None
  render_dpi: int = 200
```

The exact fields can differ, but these capabilities must exist.

Configuration must be accepted through:

- library API
- CLI flags
- environment variables only where appropriate

Avoid hidden global configuration.

## 7. Required Library API

Add a stable library function equivalent to:

```python
def process_pdf(
    input_pdf: Path,
    output_root: Path,
    *,
    config: ExtractionConfig | None = None,
    run_id: str | None = None,
    logger: logging.Logger | None = None,
) -> ExtractionResult:
    ...
```

Requirements:

- `output_root` must be caller-configurable.
- Return a structured `ExtractionResult`.
- CLI may return exit codes, but internally it must call the library API.
- Page-level extraction failures must not abort the whole document unless configured to fail-fast.
- Startup/fatal failures should raise typed exceptions in library mode.

Do not require `rag-engine` to:

- call a CLI
- monkeypatch globals
- infer result state from an integer return code

## 8. Required Models

Define typed result models.

Dataclasses or Pydantic models are acceptable.

```python
ExtractionResult:
  input_pdf: Path
  output_dir: Path
  progress_path: Path
  extractor_version: str
  input_sha256: str
  total_pages: int
  pages: list[PageExtractionResult]
  failed_pages: list[int]
  status: str              # ok | partial_failure | failed | interrupted
  run_id: str
  schema_version: str
  started_at: datetime
  completed_at: datetime | None
  config_hash: str
  config_used: ExtractionConfig

PageExtractionResult:
  page_number: int
  status: str              # ok | fallback_ok | low_text_warning | failed
  output_file: Path
  characters: int
  duration_seconds: float
  final_provider: str | None
  fallback_used: bool
  attempts: list[ProviderAttempt]
  error: str | None

ProviderAttempt:
  provider: str            # pymupdf | marker | ollama | etc.
  status: str              # ok | skipped | failed | low_quality
  characters: int
  duration_seconds: float | None
  error: str | None
  metadata: dict
```

These models are the contract consumed by `rag-engine`.

## 9. Output Directory Rules

Current behavior uses `output/<pdf_stem>/`, which is unsafe.

Required behavior:

- caller can choose `output_root`
- generated output directory must avoid collisions
- same-stem PDFs from different folders must not collide
- concurrent runs must not share `progress.tmp`, `run.log`, or page files
- output path must be returned in `ExtractionResult`

Acceptable default:

```text
<output_root>/<input_sha256>/
```

If multiple runs for the same source need separate outputs:

```text
<output_root>/<input_sha256>/<run_id>/
```

Document resume behavior clearly.

## 10. Markdown Output Contract

The final page files must have a stable shape.

Success:

```md
# Page N

<content>
```

Failure:

```md
# Page N

OCR FAILED

Error: <error_message>
```

Rules:

- `# Page N` is added by this package.
- Provider body Markdown is preserved under that wrapper.
- Empty provider output must not be written as success.
- Low-text output may be written as success with `low_text_warning`.
- Do not write partial-content-plus-error pages unless the contract is explicitly changed.
- All page files must be UTF-8.

## 11. progress.json Contract

Keep `progress.json`, but harden and document it.

Required top-level fields:

- `schema_version`
- `extractor_version`
- `input_file`
- `input_file_name`
- `input_sha256`
- `total_pages`
- `pipeline`
- `config_hash`
- `config_used`
- `run_id`
- `started_at`
- `updated_at`
- `completed_at`
- `status`
- `last_completed_page`
- `failed_pages`
- `pages`

Each page record must include:

- `status`
- `characters`
- `duration_seconds`
- `output_file`
- `processed_at`
- `final_provider`
- `fallback_used`
- `attempts`
- `error` when failed

Required behavior:

- write baseline progress before processing page 1 once startup validation succeeds
- save progress after every page success/failure
- save progress on interrupt
- write progress atomically
- avoid shared temp filenames under concurrent runs
- document that `progress.json` can be absent if startup validation fails before baseline creation

## 12. Exit Codes

Keep CLI exit codes explicit:

- `0`: completed, including partial page failures
- `1`: startup/fatal failure
- `2`: invalid input
- `130`: interrupted

Library callers must not be forced to infer outcome from exit codes.

## 13. Exceptions

Add typed exceptions:

```python
ExtractionError
InvalidInputError
DependencyMissingError
ProviderError
PageExtractionError
ProgressError
ConfigurationError
ConcurrencyError
```

Use them in the library API. The CLI catches and converts them to exit codes.

## 14. Dependency Validation

Expose a `validate_environment(config: ExtractionConfig) -> EnvironmentReport` function.

It must report:

- available providers
- missing Python packages
- missing external binaries
- degraded capabilities
- fatal blockers

Binaries currently relevant:

- `marker_single`
- `ollama`
- `pdftoppm`

Rules:

- text extraction mode must validate its Python dependency, e.g. PyMuPDF
- Marker mode must validate `marker_single`
- forced Ollama fallback must fail fast if `ollama` or `pdftoppm` is missing
- optional fallback can be reported as degraded if unavailable
- missing optional fallback must not silently pass if fallback is expected for scanned pages

Direct Python dependencies must be declared explicitly. Current code imports `platformdirs` directly; it must be declared directly.

## 15. Provider Interfaces

Create provider interfaces internally so adding/replacing providers is controlled.

Suggested shape:

```python
class PageExtractor:
    name: str
    def validate(self) -> ProviderCapability: ...
    def extract_page(self, pdf_path: Path, page_number: int, config: ExtractionConfig) -> ProviderResult: ...
```

Providers to implement before RAG consumption:

- PyMuPDF text extractor
- Marker OCR extractor
- Ollama vision fallback extractor

Do not hardwire all logic into one `process_pdf()` function.

## 16. Quality Gates

Extraction quality must be explicit and configurable.

Required:

- minimum text characters for accepting text extraction
- minimum OCR characters for accepting OCR output
- provider attempts recorded when output is rejected as too short
- low-text warnings recorded but not hidden
- final page status reflects the actual path used

Recommended:

- simple text cleanliness checks
- ratio of printable characters
- optional page image detection where practical

## 17. Concurrency

Current implementation is not safe for simultaneous calls on the same PDF/output directory.

Required:

- either implement locking, or guarantee per-run isolated output directories
- prevent shared `progress.tmp` collisions
- avoid global logger handler resets that interfere with concurrent library calls
- document concurrency guarantees

Minimum acceptable for `rag-engine`:

- concurrent extractions of different PDFs are safe when given different output dirs
- concurrent extraction of the same PDF either uses separate run dirs or fails fast with `ConcurrencyError`

## 18. Logging

Current logger setup mutates handlers on a global logger.

Required:

- allow caller-provided logger
- avoid global handler mutation in library mode
- CLI can configure console/file logging
- library must not print to stdout/stderr except through caller-approved logging
- logs must include page number, provider, status, duration, and source identifiers where available

## 19. Resume Behavior

Current resume behavior depends on `progress.json`.

Required:

- define resume semantics explicitly
- validate source hash, page count, config hash, and pipeline version before resuming
- if any mismatch exists, start a new run or require explicit overwrite
- never silently mix outputs from different source/config versions

## 20. Consolidation of Current Code

Current code has two overlapping paths:

- `ocr_tool.py`: Marker + Ollama fallback
- `pdf_ocr_marker.py`: older Marker-only implementation with `output_root`

Required:

- consolidate around one supported library API
- preserve useful tests from both
- remove or mark legacy code clearly
- avoid duplicate implementations of progress, logging, and page writing

## 21. Security and Privacy

The package processes legal/regulatory documents and may process sensitive client PDFs.

Requirements:

- no document content sent to remote services unless explicitly configured
- local providers must be the default
- logs must not dump full page content
- error snippets must be bounded
- temporary files must be cleaned up
- output locations must be caller-controlled

## 22. Tests Required

Add or update tests for:

- text-native PDF extraction through PyMuPDF
- scanned-page OCR through Marker
- Marker failure followed by Ollama fallback
- forced fallback mode
- mixed text/scanned document routing
- custom `output_root`
- structured `ExtractionResult`
- same-stem PDFs do not collide
- partial page failure returns completed/partial result
- missing PyMuPDF when text provider is enabled
- missing `marker_single` fails fast when OCR is required
- forced fallback with missing `ollama` or `pdftoppm` fails fast
- progress baseline creation
- progress save after successful page
- progress save after failed page
- resume with matching hash/config
- resume rejected on hash/config mismatch
- interruption behavior where testable
- concurrent same-PDF invocation behavior
- CLI still works

## 23. Documentation Required

README must document:

- install
- CLI usage
- library usage
- provider configuration
- text extraction path
- scanned/OCR path
- fallback behavior
- output layout
- `progress.json` schema
- markdown page contract
- dependency requirements
- model/cache configuration
- concurrency guarantees
- privacy/local-processing behavior

## 24. Release Requirements

Before `rag-engine` consumes this package:

- package installs with `pip install -e .`
- package can be pinned as a dependency
- tests pass from a clean checkout
- MIT `LICENSE` file exists at repository root
- package metadata declares MIT license
- README documents library and CLI usage
- version is defined in one place
- changelog or release notes identify the API version consumed by `rag-engine`
- public API is exported from `pagewise_pdf_extractor.__init__`

## 25. Installation and Dependency Consumption

The package must be installable as a normal Python dependency.

### 25.1 Development Install

During local development, `rag-engine` must be able to install the extractor package from its separate repository:

```powershell
pip install -e D:\Developer\Projects\pagewise-pdf-extractor
```

Equivalent `requirements.txt` entry for local development:

```txt
-e D:\Developer\Projects\pagewise-pdf-extractor
```

Do not require copying source files into `rag-engine`.

### 25.2 GitHub Dependency Install

Initial `rag-engine` consumption should use a pinned GitHub tag or commit SHA.

Preferred form after the extractor package team creates a release tag:

```txt
pagewise-pdf-extractor @ git+https://github.com/ebmurha/pagewise-pdf-extractor.git@v0.1.0
```

Commit SHA form is also acceptable during pre-release validation:

```txt
pagewise-pdf-extractor @ git+https://github.com/ebmurha/pagewise-pdf-extractor.git@<commit-sha>
```

Do not use an unpinned branch such as `@main` in `rag-engine`.

### 25.3 Released Package Install

After release to PyPI or a private package registry:

```powershell
pip install pagewise-pdf-extractor
```

Equivalent `requirements.txt` entry:

```txt
pagewise-pdf-extractor>=0.1.0
```

The exact version constraint should be chosen by `rag-engine` when it pins a known-good release.

PyPI publication is a later strategic step after the API is stable. It is not required for initial `rag-engine` integration.

### 25.4 Private Git Install

If distributed from a private Git repository before registry publication:

```txt
pagewise-pdf-extractor @ git+https://github.com/<org>/pagewise-pdf-extractor.git@v0.1.0
```

Use a tag or commit SHA, not an unpinned branch, when `rag-engine` depends on it.

For the current public repository, the Git dependency form is:

```txt
pagewise-pdf-extractor @ git+https://github.com/ebmurha/pagewise-pdf-extractor.git@v0.1.0
```

### 25.5 Required Package Metadata

The package must define at least:

```toml
[project]
name = "pagewise-pdf-extractor"
version = "0.1.0"
license = "MIT"

[project.scripts]
pagewise-pdf-extractor = "pagewise_pdf_extractor.cli:main"
```

The import package must expose the public API:

```python
from pagewise_pdf_extractor import (
    ExtractionConfig,
    ExtractionResult,
    process_pdf,
    validate_environment,
)
```

### 25.6 Installation Success Criteria

From a clean `rag-engine` environment, all of this must work:

```powershell
pip install -e D:\Developer\Projects\pagewise-pdf-extractor
python -c "from pagewise_pdf_extractor import ExtractionConfig, process_pdf, validate_environment; print('ok')"
pagewise-pdf-extractor --help
```

## 26. RAG Engine Integration Contract

`rag-engine` will:

- declare this package as a dependency
- import the library API
- call it with a controlled `output_root`
- pass explicit extraction config
- read `ExtractionResult` and/or `progress.json`
- convert page records into its own `Document`, `ExtractionRun`, and `Page` models

`rag-engine` will not:

- copy this package source
- patch module globals like `OUTPUT_ROOT`
- rely on the CLI as the primary integration path
- decide extraction provider internals
- implement PyMuPDF/Marker/Ollama extraction logic
- call the extractor concurrently for the same PDF unless the package documents that it is safe
- add a script-specific adapter for the old `ocr_tool.py` API

## 27. Expected Dependency Call From RAG Engine

This is the concrete integration target. This package is successful when `rag-engine` can call it approximately like this without shelling out, monkeypatching globals, or parsing undocumented files:

```python
from pathlib import Path

from pagewise_pdf_extractor import ExtractionConfig, ExtractionResult, process_pdf


def run_extraction(pdf_path: Path, work_dir: Path) -> ExtractionResult:
    result = process_pdf(
        input_pdf=pdf_path,
        output_root=work_dir / "extracted",
        config=ExtractionConfig(
            text_provider="pymupdf",
            ocr_provider="marker",
            fallback_provider="ollama",
            fallback_enabled=True,
            ollama_model="deepseek-ocr",
            force_ocr=False,
            force_fallback=False,
        ),
    )

    return result
```

`rag-engine` must then be able to rely on:

```python
result.input_pdf
result.output_dir
result.progress_path
result.extractor_version
result.input_sha256
result.total_pages
result.pages
result.failed_pages
result.status
result.run_id
result.schema_version
result.config_hash
result.config_used
```

Each page result must support:

```python
page.page_number
page.status
page.output_file
page.characters
page.duration_seconds
page.final_provider
page.fallback_used
page.attempts
page.error
```

Minimal `rag-engine` mapping:

```python
for page in result.pages:
    page_record = Page(
        doc_id=doc_id,
        extraction_run_id=result.run_id,
        page_number=page.page_number,
        md_file_path=str(page.output_file),
        status=page.status,
        provider=page.final_provider or "none",
        char_count=page.characters,
        metadata={
            "fallback_used": page.fallback_used,
            "attempts": [attempt.model_dump() for attempt in page.attempts],
            "error": page.error,
        },
    )
```

The package must also export a stable environment check:

```python
from pagewise_pdf_extractor import validate_environment

report = validate_environment(config)
if report.has_fatal_errors:
    raise RuntimeError(report.summary)
```

The exact implementation may differ, but these capabilities and fields must be available from public, documented imports.

## 28. Integration Success Criteria

This package implementation is complete enough for `rag-engine` when all of these are true:

- `pip install -e /path/to/pagewise-pdf-extractor` works from the `rag-engine` environment.
- `from pagewise_pdf_extractor import ExtractionConfig, ExtractionResult, process_pdf, validate_environment` works.
- `process_pdf()` accepts `input_pdf`, `output_root`, and `config`.
- `process_pdf()` returns `ExtractionResult`, not an integer.
- `ExtractionResult.extractor_version` is populated from the package version.
- `ExtractionResult.config_used` contains the resolved config actually used.
- `ExtractionResult.config_hash` is stable for the resolved config.
- `progress.json` contains `extractor_version`, `config_used`, and `config_hash`.
- text-native PDFs can complete using PyMuPDF without unnecessary OCR.
- scanned PDFs can complete using Marker.
- Marker failure can fall back to configured Ollama OCR when fallback is enabled.
- mixed PDFs route per page and record final provider per page.
- page-level failure produces a failed page record and failure Markdown without aborting the whole document by default.
- fatal startup failures raise typed exceptions in library mode.
- output is written under caller-provided `output_root`.
- same-stem PDFs do not collide.
- no full page content is logged.
- tests cover the call pattern shown above.

## 29. Done Criteria

This package is ready for `rag-engine` only when:

- it is a real installable Python package
- it has a stable library API
- it supports text-native PDF extraction
- it supports scanned PDF OCR
- it supports configurable OCR fallback
- output path is caller-configurable
- structured results are returned
- progress contract is documented and tested
- concurrency behavior is documented and tested
- all required tests pass
- package version is released or locally installable with a stable version
- `ExtractionResult.extractor_version` is populated
- resolved `config_used` is available in `ExtractionResult` and persisted in `progress.json`
