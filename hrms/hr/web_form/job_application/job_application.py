"""Public application labels reveal only open, published job openings."""
import frappe


def get_context(context):
	pass


@frappe.whitelist(allow_guest=True)
def get_opening_title(opening: str) -> dict:
	title = frappe.db.get_value("Job Opening", {"name": opening, "publish": 1, "status": "Open"}, "job_title")
	return {"job_title": title} if title else {}
