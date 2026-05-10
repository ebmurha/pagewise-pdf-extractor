import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pagewise_pdf_extractor import (
    ConcurrencyError,
    ExtractionConfig,
    ExtractionResult,
    LayoutArtifact,
    process_pdf,
    validate_environment,
)
from pagewise_pdf_extractor.api import EXTRACTOR_VERSION
from pagewise_pdf_extractor.models import EnvironmentReport, ProviderCapability, ProviderResult
from pagewise_pdf_extractor.providers.base import markdown_layout_artifacts


def clean_report():
    return EnvironmentReport(providers={"pymupdf": ProviderCapability("pymupdf", True)})


class PackageApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.pdf_path = self.root / "document.pdf"
        self.pdf_path.write_bytes(b"%PDF dummy")
        self.output_root = self.root / "out"

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_with_patches(self, config=None, pages=1):
        config = config or ExtractionConfig()
        with patch("pagewise_pdf_extractor.api.validate_environment", return_value=clean_report()), \
            patch("pagewise_pdf_extractor.api.get_total_pages", return_value=pages):
            return process_pdf(self.pdf_path, self.output_root, config=config, run_id="run1")

    def test_public_api_returns_structured_result_and_progress(self):
        with patch(
            "pagewise_pdf_extractor.api.PyMuPDFTextExtractor.extract_page",
            return_value=ProviderResult(
                text="embedded text with enough characters to pass the quality threshold",
                status="text_ok",
                characters=62,
            ),
        ) as text_provider, \
            patch("pagewise_pdf_extractor.api.MarkerOCRExtractor.extract_page") as marker_provider:
            result = self.run_with_patches(pages=2)

        self.assertIsInstance(result, ExtractionResult)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.extractor_version, EXTRACTOR_VERSION)
        self.assertEqual(result.config_used.text_provider, "pymupdf")
        self.assertEqual(len(result.pages), 2)
        self.assertEqual(result.pages[0].final_provider, "pymupdf")
        marker_provider.assert_not_called()
        self.assertEqual(text_provider.call_count, 2)

        progress = json.loads(result.progress_path.read_text(encoding="utf-8"))
        self.assertEqual(progress["schema_version"], "1.0")
        self.assertEqual(progress["extractor_version"], EXTRACTOR_VERSION)
        self.assertEqual(progress["config_hash"], result.config_hash)
        self.assertIn("config_used", progress)
        self.assertEqual(progress["status"], "ok")

    def test_layout_artifacts_are_returned_and_persisted(self):
        artifact = LayoutArtifact(
            kind="table",
            page_number=1,
            bbox=(10.0, 20.0, 110.0, 80.0),
            text="| A | B |\n| --- | --- |\n| 1 | 2 |",
            rows=[["A", "B"], ["1", "2"]],
            metadata={"source": "test"},
        )

        with patch("pagewise_pdf_extractor.api.validate_environment", return_value=clean_report()), \
            patch("pagewise_pdf_extractor.api.get_total_pages", return_value=1), \
            patch(
                "pagewise_pdf_extractor.api.PyMuPDFTextExtractor.extract_page",
                return_value=ProviderResult(
                    text="embedded text with enough characters to pass the quality threshold",
                    status="text_ok",
                    characters=62,
                    layout_artifacts=[artifact],
                ),
            ):
            result = process_pdf(self.pdf_path, self.output_root, run_id="layout")

        self.assertEqual(result.pages[0].layout_artifacts[0].kind, "table")
        self.assertEqual(result.pages[0].layout_artifacts[0].rows, [["A", "B"], ["1", "2"]])
        markdown = result.pages[0].output_file.read_text(encoding="utf-8")
        self.assertIn("## Layout Artifacts", markdown)
        self.assertIn("| A | B |", markdown)

        progress = json.loads(result.progress_path.read_text(encoding="utf-8"))
        saved_artifact = progress["pages"]["1"]["layout_artifacts"][0]
        self.assertEqual(saved_artifact["kind"], "table")
        self.assertEqual(saved_artifact["bbox"], [10.0, 20.0, 110.0, 80.0])

    def test_marker_failure_falls_back_to_ollama(self):
        def marker_fail(*_args, **_kwargs):
            raise RuntimeError("marker failed")

        with patch(
            "pagewise_pdf_extractor.api.PyMuPDFTextExtractor.extract_page",
            return_value=ProviderResult(text="", status="text_empty", characters=0),
        ), patch(
            "pagewise_pdf_extractor.api.MarkerOCRExtractor.extract_page",
            side_effect=marker_fail,
        ), patch(
            "pagewise_pdf_extractor.api.OllamaVisionExtractor.extract_page",
            return_value=ProviderResult(
                text="fallback text from ollama with enough useful characters",
                status="ollama_ok",
                characters=54,
            ),
        ):
            result = self.run_with_patches()

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.pages[0].status, "fallback_ok")
        self.assertEqual(result.pages[0].final_provider, "ollama")
        self.assertTrue(result.pages[0].fallback_used)
        self.assertEqual([attempt.provider for attempt in result.pages[0].attempts], ["pymupdf", "marker", "ollama"])

    def test_forced_fallback_skips_text_and_marker(self):
        config = ExtractionConfig(force_fallback=True)
        with patch("pagewise_pdf_extractor.api.PyMuPDFTextExtractor.extract_page") as text_provider, \
            patch("pagewise_pdf_extractor.api.MarkerOCRExtractor.extract_page") as marker_provider, \
            patch(
                "pagewise_pdf_extractor.api.OllamaVisionExtractor.extract_page",
                return_value=ProviderResult(text="forced fallback text with enough chars", status="ollama_ok", characters=38),
            ):
            result = self.run_with_patches(config=config)

        text_provider.assert_not_called()
        marker_provider.assert_not_called()
        self.assertEqual(result.pages[0].final_provider, "ollama")
        self.assertEqual(result.pages[0].attempts[0].status, "skipped")

    def test_page_level_failure_returns_partial_result_and_failure_markdown(self):
        def marker_by_page(_pdf, page_number, *_args):
            if page_number == 2:
                raise RuntimeError("marker page failed")
            return ProviderResult(text="ocr text with enough characters", status="marker_ok", characters=31)

        with patch(
            "pagewise_pdf_extractor.api.PyMuPDFTextExtractor.extract_page",
            return_value=ProviderResult(text="", status="text_empty", characters=0),
        ), patch(
            "pagewise_pdf_extractor.api.MarkerOCRExtractor.extract_page",
            side_effect=marker_by_page,
        ):
            result = self.run_with_patches(config=ExtractionConfig(fallback_enabled=False), pages=3)

        self.assertEqual(result.status, "partial_failure")
        self.assertEqual(result.failed_pages, [2])
        self.assertIn("OCR FAILED", result.pages[1].output_file.read_text(encoding="utf-8"))

    def test_output_root_uses_sha_not_pdf_stem(self):
        other_pdf = self.root / "nested" / "document.pdf"
        other_pdf.parent.mkdir()
        other_pdf.write_bytes(b"%PDF other")

        with patch("pagewise_pdf_extractor.api.validate_environment", return_value=clean_report()), \
            patch("pagewise_pdf_extractor.api.get_total_pages", return_value=1), \
            patch(
                "pagewise_pdf_extractor.api.PyMuPDFTextExtractor.extract_page",
                return_value=ProviderResult(text="embedded text with enough characters", status="text_ok", characters=37),
            ):
            first = process_pdf(self.pdf_path, self.output_root, run_id="a")
            second = process_pdf(other_pdf, self.output_root, run_id="b")

        self.assertNotEqual(first.output_dir, second.output_dir)
        self.assertEqual(first.output_dir.parent, self.output_root.resolve())
        self.assertEqual(second.output_dir.parent, self.output_root.resolve())

    def test_resume_reuses_matching_progress(self):
        seen_pages = []

        def text_page(_pdf, page_number, *_args):
            seen_pages.append(page_number)
            return ProviderResult(text=f"embedded page {page_number} with enough characters", status="text_ok", characters=42)

        with patch("pagewise_pdf_extractor.api.validate_environment", return_value=clean_report()), \
            patch("pagewise_pdf_extractor.api.get_total_pages", return_value=2), \
            patch("pagewise_pdf_extractor.api.PyMuPDFTextExtractor.extract_page", side_effect=text_page):
            first = process_pdf(self.pdf_path, self.output_root, run_id="resume")
            second = process_pdf(self.pdf_path, self.output_root, run_id="resume")

        self.assertEqual(first.output_dir, second.output_dir)
        self.assertEqual(seen_pages, [1, 2])
        self.assertEqual(second.pages[0].page_number, 1)

    def test_same_output_directory_lock_fails_fast(self):
        with patch("pagewise_pdf_extractor.api.validate_environment", return_value=clean_report()), \
            patch("pagewise_pdf_extractor.api.get_total_pages", return_value=1), \
            patch("pagewise_pdf_extractor.api.compute_sha256", return_value="abc"):
            output_dir = self.output_root.resolve() / "abc"
            output_dir.mkdir(parents=True)
            (output_dir / ".pagewise-extractor.lock").write_text("locked", encoding="utf-8")
            with self.assertRaises(ConcurrencyError):
                process_pdf(self.pdf_path, self.output_root, run_id="locked")

    def test_markdown_layout_artifacts_detect_tables_and_figures(self):
        text = "\n".join(
            [
                "| Col A | Col B |",
                "| --- | --- |",
                "| one | two |",
                "",
                "![Chart caption](images/chart.png)",
            ]
        )

        artifacts = markdown_layout_artifacts(text, page_number=3)

        self.assertEqual([artifact.kind for artifact in artifacts], ["table", "figure"])
        self.assertEqual(artifacts[0].rows, [["Col A", "Col B"], ["one", "two"]])
        self.assertEqual(artifacts[1].text, "Chart caption")
        self.assertEqual(artifacts[1].metadata["target"], "images/chart.png")

    def test_validate_environment_reports_forced_fallback_missing_tools_as_fatal(self):
        with patch("pagewise_pdf_extractor.providers.pymupdf_text.PyMuPDFTextExtractor.validate", return_value=ProviderCapability("pymupdf", True)), \
            patch("pagewise_pdf_extractor.providers.marker_ocr.shutil.which", return_value="marker_single"), \
            patch("pagewise_pdf_extractor.providers.ollama_vision.shutil.which", return_value=None):
            report = validate_environment(ExtractionConfig(force_fallback=True))

        self.assertTrue(report.has_fatal_errors)
        self.assertIn("ollama", report.missing_binaries)
        self.assertIn("pdftoppm", report.missing_binaries)

    def test_missing_marker_fails_fast_when_ocr_is_required(self):
        def fake_which(command):
            return None if command == "marker_single" else "tool"

        with patch("pagewise_pdf_extractor.providers.pymupdf_text.PyMuPDFTextExtractor.validate", return_value=ProviderCapability("pymupdf", True)), \
            patch("pagewise_pdf_extractor.providers.marker_ocr.shutil.which", side_effect=fake_which):
            report = validate_environment(ExtractionConfig(force_ocr=True))

        self.assertTrue(report.has_fatal_errors)
        self.assertIn("marker_single", report.missing_binaries)


class RealPyMuPDFProviderTests(unittest.TestCase):
    def test_text_native_pdf_extraction_through_pymupdf(self):
        try:
            import fitz  # type: ignore
        except Exception:
            self.skipTest("PyMuPDF is not installed")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pdf_path = root / "native.pdf"
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 72), "This is embedded text from a text native PDF page.")
            doc.save(str(pdf_path))
            doc.close()

            from pagewise_pdf_extractor.providers.pymupdf_text import PyMuPDFTextExtractor

            result = PyMuPDFTextExtractor().extract_page(pdf_path, 1, 1, ExtractionConfig(min_text_chars=10))

        self.assertEqual(result.status, "text_ok")
        self.assertIn("embedded text", result.text)


if __name__ == "__main__":
    unittest.main()
