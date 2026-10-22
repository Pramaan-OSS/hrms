"""Optional payout of an approved payroll run, with explicit approval per step."""

import frappe
from frappe import _

from hrms.integrations.pramaan_common import get_client, respond

PROFILE_SETTING = "payout_profile_id"


def _profile_id() -> str:
	profile = (frappe.db.get_single_value("HR Settings", PROFILE_SETTING) or "").strip()
	if not profile:
		frappe.throw(
			_("Payouts are not set up yet. Set payout_profile_id in HR Settings to turn this on.")
		)
	return profile


def _require_approval(doc):
	if doc.docstatus != 1:
		frappe.throw(_("Submit the payroll run before approving a payout."))
	if not doc.payout_approved_by:
		frappe.throw(_("Tick the payout approval on this run first."))


@frappe.whitelist()
@respond
def approve_payout(payroll_entry: str) -> dict:
	"""Record the signed-in payroll approver after the run has been submitted."""
	doc = frappe.get_doc("Payroll Entry", payroll_entry)
	doc.check_permission("submit")
	if doc.docstatus != 1:
		frappe.throw(_("Submit the payroll run before approving a payout."))
	doc.db_set("payout_approved_by", frappe.session.user)
	return {"approved": True}


@frappe.whitelist()
@respond
def prepare_payout(payroll_entry: str) -> dict:
	"""Quote the transfer for one approved run; nothing is sent."""
	doc = frappe.get_doc("Payroll Entry", payroll_entry)
	doc.check_permission("write")
	_require_approval(doc)
	if not doc.payout_currency or not doc.payout_amount:
		frappe.throw(_("Set the payout amount and currency on this run first."))

	profile = _profile_id()
	result = get_client().call(
		"finance.transfer-quote.create",
		{
			"profileId": profile,
			"fromCurrency": doc.payout_currency,
			"toCurrency": doc.payout_currency,
			"fromAmount": doc.payout_amount,
		},
		idempotency_key=f"payout-quote:{doc.name}",
	)
	doc.db_set("payout_quote_ref", result.get("quoteId") or "")
	return {"quote": result}


@frappe.whitelist()
@respond
def send_payout(payroll_entry: str) -> dict:
	"""Send the quoted transfer once, after the explicit on-run approval."""
	doc = frappe.get_doc("Payroll Entry", payroll_entry)
	doc.check_permission("write")
	_require_approval(doc)
	if not doc.payout_quote_ref:
		frappe.throw(_("Prepare the payout quote first."))
	if doc.payout_transfer_ref:
		frappe.throw(_("This run already has a payout. Check its status instead of sending again."))

	profile = _profile_id()
	client = get_client()
	transfer = client.call(
		"finance.transfer.create",
		{
			"profileId": profile,
			"quoteId": doc.payout_quote_ref,
			"amount": {"amount": int(doc.payout_amount * 100), "currency": doc.payout_currency},
			"note": _("Payroll run {0}").format(doc.name),
		},
		idempotency_key=f"payout-transfer:{doc.name}",
		approved_by=doc.payout_approved_by,
	)
	transfer_ref = transfer.get("ref") or ""
	doc.db_set("payout_transfer_ref", transfer_ref)
	doc.db_set("payout_status", transfer.get("status") or "pending")

	if transfer.get("status") == "pending" and transfer_ref:
		funding = client.call(
			"finance.transfer.fund",
			{
				"profileId": profile,
				"transferId": transfer_ref,
				"currency": doc.payout_currency,
				"maxDebit": doc.payout_amount * 1.05,
				"maxFee": doc.payout_amount * 0.05,
			},
			idempotency_key=f"payout-fund:{doc.name}",
			approved_by=doc.payout_approved_by,
		)
		doc.db_set("payout_status", funding.get("status") or "funding")

	return {"transfer_ref": transfer_ref, "status": doc.payout_status}
