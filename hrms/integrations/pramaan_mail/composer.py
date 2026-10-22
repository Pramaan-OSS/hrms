"""Document email keeps local permissions and queues only through the app client."""
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from hrms.integrations.pramaan_mail import _addresses, _attachments, sendmail


@frappe.whitelist()
def make(
	doctype: str | None = None,
	name: str | None = None,
	content: str | None = None,
	subject: str | None = None,
	recipients: str | list | None = None,
	send_email: str | int | bool = False,
	attachments: str | list | None = None,
	send_me_a_copy: str | int | bool = False,
	cc: str | list | None = None,
	bcc: str | list | None = None,
	send_after: str | None = None,
	print_html: str | None = None,
	print_format: str | None = None,
	print_letterhead: str | int | bool = True,
	letterhead: str | None = None,
	print_language: str | None = None,
	**kwargs,
) -> dict:
	from frappe.core.doctype.communication.email import make as create_communication

	if doctype and name:
		frappe.has_permission(doctype, doc=name, ptype="email", throw=True)
	if letterhead:
		frappe.has_permission("Letter Head", doc=letterhead, ptype="read", throw=True)
	files = frappe.parse_json(attachments) if isinstance(attachments, str) else attachments or []
	# Check the original private files before the framework copies them onto a message.
	_attachments(files)
	if print_html or print_format:
		if not doctype or not name:
			frappe.throw(_("Choose a saved document before attaching its printout."))
		frappe.has_permission(doctype, doc=name, ptype="print", throw=True)
		files.append(frappe.attach_print(doctype, name, print_format=print_format,
			html=print_html, print_letterhead=cint(print_letterhead), letterhead=letterhead,
			lang=print_language))
	if cint(send_me_a_copy):
		cc = list(dict.fromkeys(_addresses(cc) + _addresses(frappe.get_cached_value("User", frappe.session.user, "email"))))
	kwargs.pop("sender", None)
	result = create_communication(doctype=doctype, name=name, content=content, subject=subject,
		recipients=recipients, cc=cc, bcc=bcc, attachments=files, send_email=False,
		sender=frappe.db.get_single_value("HR Settings", "pramaan_email_from"),
		letterhead=letterhead, **kwargs)
	excluded = set(_addresses(result.get("emails_not_sent_to")))
	recipients = [address for address in _addresses(recipients) if address not in excluded]
	cc = [address for address in _addresses(cc) if address not in excluded]
	bcc = [address for address in _addresses(bcc) if address not in excluded]
	if cint(send_email) and (recipients or cc or bcc):
		# The local undo window can remove the queue item before any external effect.
		due = send_after or str(now_datetime() + timedelta(seconds=10))
		sendmail(recipients=recipients, cc=cc, bcc=bcc, subject=subject, message=content,
			attachments=files, reference_doctype=doctype, reference_name=name,
			send_after=due, communication=result["name"])
	return result
