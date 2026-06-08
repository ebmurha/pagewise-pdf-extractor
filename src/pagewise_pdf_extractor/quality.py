"""Deterministic embedded-text quality diagnostics."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

ENCODED_GLYPH_RE = re.compile(r"(?:^|\s)/\d+(?=\s|$)")
TABLE_ROW_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*|[A-Z])\s+\S.*\d(?:[\d .,'’-]*)$",
    re.UNICODE,
)


@dataclass(slots=True)
class TextQuality:
    accepted: bool
    score: float
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


def assess_embedded_text(
    text: str,
    *,
    min_chars: int,
    fonts: list[tuple] | None = None,
    table_count: int = 0,
    suspicious_spacing_ratio: float = 0.0,
    suspicious_spacing_pairs: int = 0,
    prefer_visual_tables: bool = True,
) -> TextQuality:
    stripped = text.strip()
    reasons: list[str] = []
    score = 1.0

    if not stripped:
        return TextQuality(False, 0.0, ["empty_text"], {"characters": 0})
    if len(stripped) < min_chars:
        reasons.append("below_minimum_characters")
        score -= 0.6

    non_whitespace = [char for char in stripped if not char.isspace()]
    non_printable = sum(not char.isprintable() for char in non_whitespace)
    non_printable_ratio = non_printable / max(len(non_whitespace), 1)
    encoded_glyph_tokens = len(ENCODED_GLYPH_RE.findall(stripped))
    token_count = max(len(stripped.split()), 1)
    encoded_glyph_ratio = encoded_glyph_tokens / token_count

    punctuation_symbols = sum(
        not char.isalnum() and not char.isspace() and char not in ".,;:!?()[]{}'\"-–—/%+"
        for char in stripped
    )
    symbol_ratio = punctuation_symbols / max(len(non_whitespace), 1)
    type3_fonts = sum(1 for font in fonts or [] if len(font) > 2 and str(font[2]).lower() == "type3")

    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    table_like_lines = sum(bool(TABLE_ROW_RE.match(line)) for line in lines)
    table_like_ratio = table_like_lines / max(len(lines), 1)

    if non_printable_ratio > 0.01:
        reasons.append("non_printable_glyphs")
        score -= 0.8
    if encoded_glyph_ratio > 0.08:
        reasons.append("encoded_glyph_stream")
        score -= 0.8
    if type3_fonts and (
        non_printable_ratio > 0.002
        or symbol_ratio > 0.20
        or encoded_glyph_ratio > 0.01
    ):
        reasons.append("corrupt_type3_text")
        score -= 0.8
    if symbol_ratio > 0.35:
        reasons.append("excessive_symbol_noise")
        score -= 0.5
    if suspicious_spacing_pairs >= 8 and suspicious_spacing_ratio > 0.12:
        reasons.append("abnormal_word_spacing")
        score -= 0.7
    if prefer_visual_tables and (table_count > 0 or (table_like_lines >= 3 and table_like_ratio >= 0.12)):
        reasons.append("table_layout_requires_visual_extraction")
        score -= 0.7

    score = round(max(0.0, min(score, 1.0)), 3)
    metrics = {
        "characters": len(stripped),
        "non_printable_ratio": round(non_printable_ratio, 4),
        "encoded_glyph_ratio": round(encoded_glyph_ratio, 4),
        "symbol_ratio": round(symbol_ratio, 4),
        "type3_fonts": type3_fonts,
        "table_count": table_count,
        "table_like_lines": table_like_lines,
        "table_like_ratio": round(table_like_ratio, 4),
        "suspicious_spacing_ratio": round(suspicious_spacing_ratio, 4),
        "suspicious_spacing_pairs": suspicious_spacing_pairs,
    }
    return TextQuality(not reasons, score, reasons, metrics)
