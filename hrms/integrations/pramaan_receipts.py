"""Expense receipt intake: one selected receipt suggests one claim line."""

import base64

import frappe
from frappe import _

from hrms.integrations.pramaan_common import get_client, respond

EXTRACT_SCHEMA = {
	"type": "object",
	"properties": {
		"merchant": {"type": "string"},
		"amount": {"type": "number"},
		"currency": {"type": "string"},
		"date": {"type": "string"},
	},
	"required": ["amount"],
}


@frappe.whitelist()
@respond
def extract_from_claim(claim: str) -> dict:
	"""Read one receipt attachment and suggest a claim line for review."""
	doc = frappe.get_doc("Expense Claim", claim)
	doc.check_permission("read")

	attachment_field = None
	for row in doc.expenses or []:
		if row.get("receipt_attachment"):
			attachment_field = row.get("receipt_attachment")
			break
	if not attachment_field:
		frappe.throw(_("Attach a receipt to a claim line first."))

	file = frappe.get_doc("File", {"file_url": attachment_field})
	file.check_permission("read")
	name = (file.file_name or "receipt").rsplit(".", 1)
	extension = name[1].lower() if len(name) == 2 else "pdf"

	result = get_client().call(
		"document.extract",
		{
			"content": base64.b64encode(file.get_content()).decode(),
			"extension": extension,
			"schema": EXTRACT_SCHEMA,
		},
	)
	if result.get("truncated"):
		return {"suggestion": None}
	fields = result.get("data") if isinstance(result.get("data"), dict) else {}

	amount = fields.get("amount")
	try:
		amount = round(float(amount), 2) if amount is not None else None
	except (TypeError, ValueError):
		amount = None
	if amount is None:
		return {"suggestion": None}

	suggestion = {
		"expense_type": "",
		"description": fields.get("merchant") or _("From receipt"),
		"amount": amount,
		"expense_date": fields.get("date") or "",
		"currency": fields.get("currency") or doc.currency,
	}
	return {"suggestion": suggestion}
