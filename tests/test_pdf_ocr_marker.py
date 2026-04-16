import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pdf_ocr_marker


class PdfOcrMarkerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.pdf_path = self.root / "document.pdf"
        self.pdf_path.write_bytes(b"dummy pdf content")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initialize_progress_resume_match(self):
        output_dir = self.root / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        progress_path = output_dir / "progress.json"
        logger = pdf_ocr_marker.setup_logger(output_dir)

        try:
            with patch("pdf_ocr_marker.compute_sha256", return_value="abc123"):
                progress, start_page = pdf_ocr_marker.initialize_progress(
                    self.pdf_path,
                    10,
                    progress_path,
                    logger,
                )
                self.assertEqual(start_page, 1)
                progress["last_completed_page"] = 3
                pdf_ocr_marker.save_progress(progress_path, progress)

                resumed, resumed_start = pdf_ocr_marker.initialize_progress(
                    self.pdf_path,
                    10,
                    progress_path,
                    logger,
                )
        finally:
            pdf_ocr_marker.close_logger(logger)

        self.assertEqual(resumed_start, 4)
        self.assertEqual(resumed["last_completed_page"], 3)

    def test_process_pdf_writes_failure_placeholder_and_continues(self):
        output_root = self.root / "out"

        def fake_run_marker(_pdf, page_number, _total_pages, _logger):
            if page_number == 2:
                raise RuntimeError("boom")
            return f"text from page {page_number}"

        with patch("pdf_ocr_marker.validate_marker_cli", return_value=None), \
            patch("pdf_ocr_marker.get_total_pages", return_value=3), \
            patch("pdf_ocr_marker.compute_sha256", return_value="abc"), \
            patch("pdf_ocr_marker.run_marker_for_page", side_effect=fake_run_marker):
            code = pdf_ocr_marker.process_pdf(self.pdf_path, output_root=output_root)

        self.assertEqual(code, 0)

        pdf_dir = output_root / "document"
        page_1 = (pdf_dir / "page_0001.md").read_text(encoding="utf-8")
        page_2 = (pdf_dir / "page_0002.md").read_text(encoding="utf-8")
        page_3 = (pdf_dir / "page_0003.md").read_text(encoding="utf-8")

        self.assertIn("text from page 1", page_1)
        self.assertIn("OCR FAILED", page_2)
        self.assertIn("text from page 3", page_3)

        progress = json.loads((pdf_dir / "progress.json").read_text(encoding="utf-8"))
        self.assertEqual(progress["last_completed_page"], 3)
        self.assertIn(2, progress["failed_pages"])
        self.assertEqual(progress["pages"]["1"]["status"], "low_text_warning")
        self.assertEqual(progress["pages"]["2"]["status"], "failed")
        self.assertEqual(progress["pages"]["3"]["status"], "low_text_warning")

    def test_process_pdf_resumes_from_next_page(self):
        output_root = self.root / "out"
        pdf_dir = output_root / "document"
        pdf_dir.mkdir(parents=True, exist_ok=True)

        progress_data = {
            "input_file": str(self.pdf_path.resolve()),
            "input_file_name": "document.pdf",
            "input_sha256": "abc",
            "total_pages": 5,
            "last_completed_page": 2,
            "failed_pages": [],
            "pages": {},
        }
        pdf_ocr_marker.save_progress(pdf_dir / "progress.json", progress_data)

        seen_pages = []

        def fake_run_marker(_pdf, page_number, _total_pages, _logger):
            seen_pages.append(page_number)
            return "ok"

        with patch("pdf_ocr_marker.validate_marker_cli", return_value=None), \
            patch("pdf_ocr_marker.get_total_pages", return_value=5), \
            patch("pdf_ocr_marker.compute_sha256", return_value="abc"), \
            patch("pdf_ocr_marker.run_marker_for_page", side_effect=fake_run_marker):
            code = pdf_ocr_marker.process_pdf(self.pdf_path, output_root=output_root)

        self.assertEqual(code, 0)
        self.assertEqual(seen_pages, [3, 4, 5])


if __name__ == "__main__":
    unittest.main()
