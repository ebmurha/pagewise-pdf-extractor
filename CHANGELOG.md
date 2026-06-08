# Changelog

All notable changes to this project are documented in this file.

## v0.3.0 - 2026-06-08

### Added

- Structural embedded-text quality diagnostics for corrupt Type3 glyph streams, non-printable content, abnormal word spacing, and table-heavy pages.
- Configurable 350 DPI image-only preprocessing for Marker OCR.
- Automatic two-up page detection and left-to-right logical-page splitting.
- `logical_page` layout artifacts with source PDF coordinates, logical order, render DPI, and split confidence.
- Configuration and CLI controls for text-quality validation, visual table routing, two-up detection, and Marker render DPI.
- Regression coverage using the supplied two-up scan and structurally broken Distiller PDF samples.

### Changed

- Embedded text is accepted only after length and structural quality validation.
- Marker now receives a temporary image-only PDF so corrupt embedded text cannot influence OCR.
- Table-heavy pages prefer visual OCR/layout extraction while clean born-digital prose remains on the faster text path.
- Multi-page Marker output is reconstructed under explicit `## Logical Page N` headings.
- Empty PyMuPDF grid detections are excluded from table artifacts.
- Existing table Markdown is no longer duplicated in the appended layout-artifact section.

### Fixed

- Two-up scanned pages no longer merge left and right logical pages during OCR.
- Corrupt but high-character-count text layers no longer bypass OCR.
- Production-DPI split detection now handles sparse two-up pages consistently.

### Verification

- Full test suite: 23 tests passed.
- Local no-fallback extraction: all 3 physical pages of the two-up sample succeeded and produced 2 logical pages each.
- Local no-fallback extraction: all 20 pages of the Distiller sample succeeded, with damaged and table-heavy pages routed through Marker.
- No Ollama or token-based service was used for sample verification.

## v0.2.0

Adds layout artifact preservation for richer PDF structure, including tables, figures/images, and vector drawing metadata where providers expose it.

## v0.1.1

Release prepared for PyPI publication after the original `v0.1.0` Git tag was created before the publishing workflow existed.

## v0.1.0

First public integration release of `pagewise-pdf-extractor`.

See the detailed release notes: [docs/releases/v0.1.0.md](docs/releases/v0.1.0.md).
