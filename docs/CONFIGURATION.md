# Configuration Reference

`ExtractionConfig` controls provider routing, quality thresholds, fallback behavior, output isolation, and resume behavior.

## Provider Selection

```python
ExtractionConfig(
    text_provider="pymupdf",
    ocr_provider="marker",
    fallback_provider="ollama",
)
```

Currently supported providers:

- `pymupdf`: embedded text extraction
- `marker`: OCR/layout extraction
- `ollama`: vision fallback OCR

## Routing Controls

- `force_ocr=True`: skip embedded text extraction and use OCR.
- `force_fallback=True`: skip text and Marker, then use fallback OCR directly.
- `fallback_enabled=False`: do not attempt fallback OCR after Marker failure.
- `fail_fast=True`: stop processing after the first failed page.

Default behavior is page-level resilience: failed pages are recorded while later pages continue.

## Quality Thresholds

- `min_text_chars`: minimum characters required to accept embedded text.
- `min_ocr_chars`: minimum characters required to accept OCR output.
- `validate_text_quality`: reject embedded text with corrupt glyph streams, abnormal PDF word spacing, or other structural quality failures.
- `prefer_visual_tables`: route table-heavy pages to OCR/layout extraction even when embedded text exists.

Provider attempts rejected by thresholds are recorded as `low_quality`.
Text-provider attempt metadata includes `quality_score`, `quality_reasons`, and `quality_metrics`.

## Marker Settings

```python
ExtractionConfig(
    marker_model_cache_dir=Path("path/to/marker-model-cache"),
    marker_render_dpi=350,
    detect_two_up=True,
)
```

If unset, Marker uses its normal cache behavior. On a cold cache, Marker may download models during the first OCR run.

Marker input is rendered into an image-only temporary PDF so a corrupt embedded text layer cannot influence OCR. Confidently detected two-up pages are split into left and right logical pages. The output remains one Markdown file per physical source page, with `## Logical Page N` sections and `logical_page` layout artifacts containing source PDF coordinates.

## Ollama Settings

```python
ExtractionConfig(
    fallback_provider="ollama",
    ollama_model="deepseek-ocr",
    ollama_endpoint=None,
    ollama_prompt="<|grounding|>Convert the document to markdown.",
    render_dpi=200,
)
```

Set `ollama_endpoint` when using a non-default Ollama host. The package sets `OLLAMA_HOST` for the provider process when this is configured.

## Output and Resume

- `resume=True`: reuse compatible `progress.json`.
- `separate_runs=True`: write under `<output_root>/<input_sha256>/<run_id>/`.

Resume only applies when source path, source hash, page count, extractor version, schema version, and config hash match.

## Environment Defaults

`ExtractionConfig.from_env()` reads:

- `MODEL_CACHE_DIR`
- `OLLAMA_ENDPOINT`
- `OLLAMA_MODEL`

Prefer explicit config in applications. Environment variables are useful for CLI use.
