"""Production entry point with the same local public-file rules as the local server."""
import os

import frappe.app

frappe.app._site = os.environ.get("HRMS_SITE_NAME", "hrms.localhost")
frappe.app._sites_path = os.environ.get("SITES_PATH", "/app/.runtime/bench/sites")
application = frappe.app.application_with_statics()
