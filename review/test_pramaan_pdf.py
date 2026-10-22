"""PDF browser selection must stay local, including a missing-installation failure."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class LocalPdfBrowserTests(unittest.TestCase):
    def setUp(self):
        self.config = {}
        framework = types.ModuleType("frappe")
        framework.get_common_site_config = lambda: self.config
        spec = importlib.util.spec_from_file_location(
            "local_pdf_browser_checks", Path(__file__).resolve().parents[1] / "hrms/overrides/chromium.py"
        )
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"frappe": framework}):
            spec.loader.exec_module(self.module)

    def test_image_browser_is_the_default(self):
        with patch.object(self.module.shutil, "which", return_value="/usr/bin/chromium") as which:
            self.assertEqual(self.module.find_local_chromium_executable(), "/usr/bin/chromium")
        which.assert_called_once_with("/usr/bin/chromium")

    def test_configured_local_binary_is_respected(self):
        self.config["chromium_path"] = "/opt/local/chromium"
        with patch.object(self.module.shutil, "which", return_value="/opt/local/chromium") as which:
            self.assertEqual(self.module.find_local_chromium_executable(), "/opt/local/chromium")
        which.assert_called_once_with("/opt/local/chromium")

    def test_missing_binary_fails_without_a_download_fallback(self):
        with patch.object(self.module.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Rebuild the application image"):
                self.module.find_local_chromium_executable()

    def test_download_entry_point_is_disabled(self):
        with self.assertRaisesRegex(RuntimeError, "Rebuild the application image"):
            self.module.refuse_chromium_download()
