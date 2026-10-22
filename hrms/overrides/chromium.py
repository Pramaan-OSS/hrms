"""Resolve the image's local PDF browser without downloading runtime dependencies."""
import shutil

import frappe

DEFAULT_CHROMIUM_PATH = "/usr/bin/chromium"
MISSING_BROWSER = "The local PDF browser is missing. Rebuild the application image to restore printing."


def find_local_chromium_executable():
	path = frappe.get_common_site_config().get("chromium_path") or DEFAULT_CHROMIUM_PATH
	if executable := shutil.which(path):
		return executable
	raise RuntimeError(MISSING_BROWSER)


def refuse_chromium_download():
	raise RuntimeError(MISSING_BROWSER)
