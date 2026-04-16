import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ocr_tool
import ocr_providers
from ocr_providers import PageOCRResult


class OcrToolTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.pdf_path = self.root / "document.pdf"
        self.pdf_path.write_bytes(b"dummy pdf content")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_configure_model_cache_uses_default_when_env_unset(self):
        output_dir = self.root / "out"
        output_dir.mkdir(parents=True, exist_ok=True)
        logger = ocr_tool.setup_logger(output_dir)

        try:
            with patch.dict(os.environ, {}, clear=True), \
                patch("ocr_tool.DOTENV_PATH", self.root / ".env"):
                cache_dir = ocr_tool.configure_model_cache(logger)
        finally:
            ocr_tool.close_logger(logger)

        self.assertIsNone(cache_dir)
        self.assertEqual(os.environ.get("MODEL_CACHE_DIR"), None)

    def test_configure_model_cache_uses_env_override(self):
        output_dir = self.root / "out"
        output_dir.mkdir(parents=True, exist_ok=True)
        logger = ocr_tool.setup_logger(output_dir)
        configured_cache = self.root / "marker-cache"

        try:
            with patch.dict(os.environ, {"MODEL_CACHE_DIR": str(configured_cache)}, clear=True), \
                patch("ocr_tool.DOTENV_PATH", self.root / ".env"):
                cache_dir = ocr_tool.configure_model_cache(logger)
                env_value = os.environ.get("MODEL_CACHE_DIR")
        finally:
            ocr_tool.close_logger(logger)

        self.assertEqual(cache_dir, str(configured_cache.resolve()))
        self.assertEqual(env_value, str(configured_cache.resolve()))
        self.assertTrue(configured_cache.exists())

    def test_log_marker_cache_status_ready(self):
        output_dir = self.root / "out"
        output_dir.mkdir(parents=True, exist_ok=True)
        logger = ocr_tool.setup_logger(output_dir)

        try:
            with patch("ocr_tool.inspect_marker_cache", return_value={
                "cache_root": r"D:\DevTools\marker-model-cache",
                "complete": True,
                "models": [],
            }):
                ocr_tool.log_marker_cache_status(logger)
        finally:
            ocr_tool.close_logger(logger)

        log_text = (output_dir / "run.log").read_text(encoding="utf-8")
        self.assertIn("Marker cache ready: D:\\\\DevTools\\\\marker-model-cache", log_text)

    def test_log_marker_cache_status_incomplete(self):
        output_dir = self.root / "out"
        output_dir.mkdir(parents=True, exist_ok=True)
        logger = ocr_tool.setup_logger(output_dir)

        try:
            with patch("ocr_tool.inspect_marker_cache", return_value={
                "cache_root": r"D:\DevTools\marker-model-cache",
                "complete": False,
                "models": [
                    {"checkpoint": "text_recognition/2025_09_23", "status": "complete"},
                    {"checkpoint": "layout/2025_09_23", "status": "missing"},
                ],
            }):
                ocr_tool.log_marker_cache_status(logger)
        finally:
            ocr_tool.close_logger(logger)

        log_text = (output_dir / "run.log").read_text(encoding="utf-8")
        self.assertIn("Marker cache incomplete", log_text)
        self.assertIn("Missing Marker models: layout/2025_09_23", log_text)

    def test_process_pdf_without_fallback_uses_marker_only(self):
        output_root = self.root / "out"

        def fake_run_ocr(_pdf, page_number, _total_pages, _logger, _ollama_model, force_ollama_fallback=False):
            self.assertFalse(force_ollama_fallback)
            return PageOCRResult(
                text=(
                    f"this is text from page {page_number} with enough length to avoid "
                    "the low text warning threshold in the OCR pipeline"
                ),
                final_provider="marker",
                fallback_used=False,
                attempts=[{"provider": "marker", "status": "ok", "characters": 110}],
            )

        with patch("ocr_tool.OUTPUT_ROOT", output_root), \
            patch("ocr_tool.configure_model_cache", return_value=None), \
            patch("ocr_tool.log_marker_cache_status", return_value=None), \
            patch("ocr_tool.validate_environment", return_value=None), \
            patch("ocr_tool.get_total_pages", return_value=3), \
            patch("ocr_tool.compute_sha256", return_value="abc"), \
            patch("ocr_tool.run_ocr_for_page", side_effect=fake_run_ocr):
            code = ocr_tool.process_pdf(self.pdf_path, "deepseek-ocr")

        self.assertEqual(code, 0)

        pdf_dir = output_root / "document"
        page_1 = (pdf_dir / "page_0001.md").read_text(encoding="utf-8")
        page_2 = (pdf_dir / "page_0002.md").read_text(encoding="utf-8")
        page_3 = (pdf_dir / "page_0003.md").read_text(encoding="utf-8")

        self.assertIn("this is text from page 1", page_1)
        self.assertIn("this is text from page 2", page_2)
        self.assertIn("this is text from page 3", page_3)

        progress = json.loads((pdf_dir / "progress.json").read_text(encoding="utf-8"))
        self.assertEqual(progress["last_completed_page"], 3)
        self.assertEqual(progress["pipeline"], "marker_with_ollama_fallback")
        self.assertEqual(progress["ollama_model"], "deepseek-ocr")
        self.assertFalse(progress["force_ollama_fallback"])
        self.assertEqual(progress["failed_pages"], [])
        self.assertEqual(progress["pages"]["1"]["status"], "ok")
        self.assertEqual(progress["pages"]["1"]["final_provider"], "marker")
        self.assertFalse(progress["pages"]["1"]["fallback_used"])
        self.assertEqual(progress["pages"]["2"]["status"], "ok")
        self.assertEqual(progress["pages"]["2"]["final_provider"], "marker")
        self.assertFalse(progress["pages"]["2"]["fallback_used"])
        self.assertEqual(progress["pages"]["3"]["status"], "ok")
        self.assertEqual(progress["pages"]["3"]["final_provider"], "marker")
        self.assertFalse(progress["pages"]["3"]["fallback_used"])

    def test_process_pdf_with_fallback_records_ollama_recovery(self):
        output_root = self.root / "out"

        def fake_run_ocr(_pdf, page_number, _total_pages, _logger, _ollama_model, force_ollama_fallback=False):
            self.assertFalse(force_ollama_fallback)
            if page_number == 2:
                return PageOCRResult(
                    text=(
                        "recovered text from ollama fallback with enough length to avoid "
                        "the low text warning threshold in the OCR pipeline"
                    ),
                    final_provider="ollama",
                    fallback_used=True,
                    attempts=[
                        {"provider": "marker", "status": "failed", "characters": 0, "error": "marker failed"},
                        {"provider": "ollama", "status": "ok", "characters": 119},
                    ],
                )

            return PageOCRResult(
                text=(
                    f"this is text from page {page_number} with enough length to avoid "
                    "the low text warning threshold in the OCR pipeline"
                ),
                final_provider="marker",
                fallback_used=False,
                attempts=[{"provider": "marker", "status": "ok", "characters": 110}],
            )

        with patch("ocr_tool.OUTPUT_ROOT", output_root), \
            patch("ocr_tool.configure_model_cache", return_value=None), \
            patch("ocr_tool.log_marker_cache_status", return_value=None), \
            patch("ocr_tool.validate_environment", return_value=None), \
            patch("ocr_tool.get_total_pages", return_value=3), \
            patch("ocr_tool.compute_sha256", return_value="abc"), \
            patch("ocr_tool.run_ocr_for_page", side_effect=fake_run_ocr):
            code = ocr_tool.process_pdf(self.pdf_path, "deepseek-ocr")

        self.assertEqual(code, 0)

        pdf_dir = output_root / "document"
        page_2 = (pdf_dir / "page_0002.md").read_text(encoding="utf-8")
        self.assertIn("recovered text from ollama fallback", page_2)

        progress = json.loads((pdf_dir / "progress.json").read_text(encoding="utf-8"))
        self.assertEqual(progress["last_completed_page"], 3)
        self.assertFalse(progress["force_ollama_fallback"])
        self.assertEqual(progress["failed_pages"], [])
        self.assertEqual(progress["pages"]["1"]["status"], "ok")
        self.assertEqual(progress["pages"]["1"]["final_provider"], "marker")
        self.assertFalse(progress["pages"]["1"]["fallback_used"])
        self.assertEqual(progress["pages"]["2"]["status"], "fallback_ok")
        self.assertEqual(progress["pages"]["2"]["final_provider"], "ollama")
        self.assertTrue(progress["pages"]["2"]["fallback_used"])
        self.assertEqual(len(progress["pages"]["2"]["attempts"]), 2)
        self.assertEqual(progress["pages"]["2"]["attempts"][0]["provider"], "marker")
        self.assertEqual(progress["pages"]["2"]["attempts"][1]["provider"], "ollama")
        self.assertEqual(progress["pages"]["3"]["status"], "ok")
        self.assertEqual(progress["pages"]["3"]["final_provider"], "marker")
        self.assertFalse(progress["pages"]["3"]["fallback_used"])

    def test_process_pdf_with_forced_ollama_fallback_skips_marker(self):
        output_root = self.root / "out"

        def fake_run_ocr(_pdf, page_number, _total_pages, _logger, _ollama_model, force_ollama_fallback=False):
            self.assertTrue(force_ollama_fallback)
            return PageOCRResult(
                text=(
                    f"forced ollama text from page {page_number} with enough length to avoid "
                    "the low text warning threshold in the OCR pipeline"
                ),
                final_provider="ollama",
                fallback_used=True,
                attempts=[
                    {"provider": "marker", "status": "skipped", "characters": 0, "error": "forced_ollama_fallback"},
                    {"provider": "ollama", "status": "ok", "characters": 111},
                ],
            )

        with patch("ocr_tool.OUTPUT_ROOT", output_root), \
            patch("ocr_tool.configure_model_cache", return_value=None), \
            patch("ocr_tool.log_marker_cache_status", return_value=None), \
            patch("ocr_tool.validate_environment", return_value=None), \
            patch("ocr_tool.get_total_pages", return_value=1), \
            patch("ocr_tool.compute_sha256", return_value="abc"), \
            patch("ocr_tool.run_ocr_for_page", side_effect=fake_run_ocr):
            code = ocr_tool.process_pdf(self.pdf_path, "deepseek-ocr", force_ollama_fallback=True)

        self.assertEqual(code, 0)

        pdf_dir = output_root / "document"
        progress = json.loads((pdf_dir / "progress.json").read_text(encoding="utf-8"))
        self.assertTrue(progress["force_ollama_fallback"])
        self.assertEqual(progress["pages"]["1"]["final_provider"], "ollama")
        self.assertTrue(progress["pages"]["1"]["fallback_used"])
        self.assertEqual(progress["pages"]["1"]["attempts"][0]["status"], "skipped")
        self.assertEqual(progress["pages"]["1"]["attempts"][1]["provider"], "ollama")

    def test_process_pdf_aborts_when_page_count_fails(self):
        output_root = self.root / "out"

        with patch("ocr_tool.OUTPUT_ROOT", output_root), \
            patch("ocr_tool.configure_model_cache", return_value=None), \
            patch("ocr_tool.log_marker_cache_status", return_value=None), \
            patch("ocr_tool.validate_environment", return_value=None), \
            patch("ocr_tool.get_total_pages", side_effect=RuntimeError("page count failed")), \
            patch("ocr_tool.run_ocr_for_page") as run_ocr:
            code = ocr_tool.process_pdf(self.pdf_path, "deepseek-ocr")

        self.assertEqual(code, 1)
        run_ocr.assert_not_called()

    def test_startup_validation_only_requires_marker_binary(self):
        def fake_which(command):
            if command == ocr_providers.MARKER_CMD:
                return r"D:\DevTools\marker_single.exe"
            return None

        with patch("ocr_providers.shutil.which", side_effect=fake_which):
            ocr_providers.validate_environment()


if __name__ == "__main__":
    unittest.main()
