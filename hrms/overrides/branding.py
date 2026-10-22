"""Keep the template title and app launcher focused on HRMS."""
import frappe


def apply_branding():
	for doctype in ("Website Settings", "System Settings"):
		if frappe.get_meta(doctype).has_field("app_name"):
			current = frappe.db.get_single_value(doctype, "app_name")
			if not current or current in {"Frappe", "ERPNext"}:
				frappe.db.set_single_value(doctype, "app_name", "HRMS")


def extend_bootinfo(bootinfo):
	for app in bootinfo.get("app_data", []):
		if app.get("app_name") != "hrms":
			app["on_apps_screen"] = False
