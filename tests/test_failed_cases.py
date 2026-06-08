import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pagewise_pdf_extractor import ExtractionConfig
from pagewise_pdf_extractor.markdown import write_page_markdown
from pagewise_pdf_extractor.models import LayoutArtifact
from pagewise_pdf_extractor.preprocessing import PreparedOCRPage
from pagewise_pdf_extractor.providers.marker_ocr import (
    PAGE_BREAK,
    MarkerOCRExtractor,
    _ProcessResult,
    _logical_page_headings,
)
from pagewise_pdf_extractor.quality import assess_embedded_text


class EmbeddedTextQualityTests(unittest.TestCase):
    def test_rejects_corrupt_type3_glyph_text(self):
        quality = assess_embedded_text(
            "Header " + "\x88\x89\x90 " * 100,
            min_chars=50,
            fonts=[(1, "n/a", "Type3", "", "T3_0", "", 0)],
        )

        self.assertFalse(quality.accepted)
        self.assertIn("corrupt_type3_text", quality.reasons)
        self.assertGreater(quality.metrics["non_printable_ratio"], 0.01)

    def test_accepts_clean_embedded_text(self):
        quality = assess_embedded_text(
            "This is clean embedded text with normal words and punctuation. " * 3,
            min_chars=50,
            fonts=[(1, "ttf", "TrueType", "Arial", "F1", "WinAnsiEncoding", 0)],
        )

        self.assertTrue(quality.accepted)
        self.assertEqual(quality.reasons, [])

    def test_routes_table_like_text_to_visual_extraction(self):
        text = "\n".join(
            [
                "ANNEX",
                "1 Revenue 5 300 391 645",
                "2 Expenses 4 200 100 000",
                "3 Balance 1 100 291 645",
            ]
        )

        quality = assess_embedded_text(text, min_chars=20, prefer_visual_tables=True)

        self.assertFalse(quality.accepted)
        self.assertIn("table_layout_requires_visual_extraction", quality.reasons)

    def test_rejects_abnormal_word_spacing(self):
        quality = assess_embedded_text(
            "Long enough text to otherwise pass the basic quality threshold.",
            min_chars=20,
            suspicious_spacing_ratio=0.25,
            suspicious_spacing_pairs=12,
        )

        self.assertFalse(quality.accepted)
        self.assertIn("abnormal_word_spacing", quality.reasons)


class OCRPreprocessingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import fitz  # noqa: F401
            import numpy  # noqa: F401
        except Exception as exc:
            raise unittest.SkipTest(f"visual preprocessing dependencies unavailable: {exc}")

    def test_supplied_two_up_sample_splits_every_physical_page(self):
        from pagewise_pdf_extractor.preprocessing import prepare_page_for_ocr

        sample = Path(__file__).resolve().parents[1] / "local-docs" / "samples" / "two-up-pdf-sample.pdf"
        with tempfile.TemporaryDirectory() as temp_dir:
            for page_number in range(1, 4):
                prepared = prepare_page_for_ocr(
                    sample,
                    page_number,
                    Path(temp_dir) / f"page-{page_number}.pdf",
                    dpi=100,
                    detect_two_up=True,
                )
                self.assertEqual(prepared.logical_pages, 2)
                self.assertGreater(prepared.split_confidence, 0.8)
                self.assertEqual([a.metadata["logical_index"] for a in prepared.artifacts], [1, 2])

    def test_supplied_two_up_sample_splits_at_production_dpi(self):
        from pagewise_pdf_extractor.preprocessing import prepare_page_for_ocr

        sample = Path(__file__).resolve().parents[1] / "local-docs" / "samples" / "two-up-pdf-sample.pdf"
        with tempfile.TemporaryDirectory() as temp_dir:
            prepared = prepare_page_for_ocr(
                sample,
                2,
                Path(temp_dir) / "page-2.pdf",
                dpi=350,
                detect_two_up=True,
            )

        self.assertEqual(prepared.logical_pages, 2)
        self.assertGreater(prepared.split_confidence, 0.8)

    def test_supplied_distiller_sample_is_not_split(self):
        from pagewise_pdf_extractor.preprocessing import prepare_page_for_ocr

        sample = Path(__file__).resolve().parents[1] / "local-docs" / "samples" / "incorrect-pdf-from-word.pdf"
        with tempfile.TemporaryDirectory() as temp_dir:
            for page_number in (1, 2, 11, 20):
                prepared = prepare_page_for_ocr(
                    sample,
                    page_number,
                    Path(temp_dir) / f"page-{page_number}.pdf",
                    dpi=100,
                    detect_two_up=True,
                )
                self.assertEqual(prepared.logical_pages, 1)
                self.assertIsNone(prepared.split_ratio)

    def test_marker_uses_preprocessed_pdf_and_preserves_artifacts(self):
        artifact = LayoutArtifact(
            kind="logical_page",
            page_number=1,
            bbox=(0, 0, 300, 800),
            metadata={"logical_index": 1},
        )
        prepared = PreparedOCRPage(
            pdf_path=Path("prepared.pdf"),
            artifacts=[artifact],
            logical_pages=2,
            split_ratio=0.5,
            split_confidence=0.95,
        )
        seen_command = []

        def fake_run(command):
            seen_command.extend(command)
            output_dir = Path(command[command.index("--output_dir") + 1])
            (output_dir / "result.md").write_text(
                f"{{0}}{PAGE_BREAK}\nLeft text\n{{1}}{PAGE_BREAK}\nRight text",
                encoding="utf-8",
            )
            return _ProcessResult(0, "ok")

        with patch(
            "pagewise_pdf_extractor.providers.marker_ocr.prepare_page_for_ocr",
            return_value=prepared,
        ), patch(
            "pagewise_pdf_extractor.providers.marker_ocr._run_streamed",
            side_effect=fake_run,
        ):
            result = MarkerOCRExtractor().extract_page(
                Path("source.pdf"),
                1,
                1,
                ExtractionConfig(min_ocr_chars=5),
            )

        self.assertEqual(seen_command[1], "prepared.pdf")
        self.assertIn("--paginate_output", seen_command)
        self.assertIn("## Logical Page 1", result.text)
        self.assertIn("## Logical Page 2", result.text)
        self.assertEqual(result.metadata["logical_pages"], 2)
        self.assertEqual(result.layout_artifacts[0].kind, "logical_page")

    def test_logical_heading_normalization_is_noop_for_single_page(self):
        self.assertEqual(_logical_page_headings("plain text", 1), "plain text")

    def test_table_artifact_does_not_duplicate_existing_markdown(self):
        table = "| A | B |\n| --- | --- |\n| 1 | 2 |"
        artifact = LayoutArtifact(kind="table", page_number=1, text=table)
        with tempfile.TemporaryDirectory() as temp_dir:
            output = write_page_markdown(Path(temp_dir), 1, table, [artifact])
            rendered = output.read_text(encoding="utf-8")

        self.assertEqual(rendered.count("| A | B |"), 1)


if __name__ == "__main__":
    unittest.main()
