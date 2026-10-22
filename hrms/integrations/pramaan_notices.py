"""Opt-in text notices for employees through the single client."""

import frappe
from frappe import _

from hrms.integrations.pramaan_common import get_client, respond


def employee_mobile_number(employee: str) -> str | None:
	number = frappe.db.get_value("Employee", employee, "cell_number")
	if not number:
		return None
	digits = frappe.utils.cstr(number).strip().replace(" ", "").replace("-", "")
	return digits if digits.startswith("+") else None


def send_employee_sms(employee: str, message: str, reference_doctype=None, reference_name=None):
	"""Send one text to an employee who opted in; silent no-op otherwise."""
	opt_in = frappe.db.get_value("Employee", employee, "receive_text_notices")
	if not opt_in:
		return False
	number = employee_mobile_number(employee)
	if not number:
		return False
	try:
		get_client().call(
			"sms.send",
			{"to": number, "body": message[:640]},
			idempotency_key=f"{reference_doctype}:{reference_name}:{employee}" if reference_doctype else None,
		)
		return True
	except Exception:
		frappe.log_error(
			title=_("Text notice not sent"),
			message=f"{reference_doctype} {reference_name}: {employee}",
		)
		return False


def send_user_sms(user: str, message: str, reference_doctype=None, reference_name=None):
	"""Resolve one user's employee record and send their opted-in text notice."""
	employee = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
	if not employee:
		return False
	return send_employee_sms(employee, message, reference_doctype, reference_name)


@frappe.whitelist()
@respond
def send_interview_sms(interview: str) -> dict:
	"""Explicit action: text the round to its opted-in interviewers."""
	doc = frappe.get_doc("Interview", interview)
	doc.check_permission("read")

	sent = 0
	for row in (doc.interview_details or []):
		interviewer = row.interviewer
		if interviewer and send_user_sms(
			interviewer,
			_("Interview round {0} on {1} at {2}. Check your email for details.").format(
				doc.name, doc.scheduled_on, doc.from_time
			),
			"Interview",
			doc.name,
		):
			sent += 1

	return {"sent": sent}
