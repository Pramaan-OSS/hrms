"""Release local scheduled mail through Pramaan, never through an external mail server."""
from email import policy
from email.parser import Parser

import frappe
from frappe.email.doctype.email_queue.email_queue import EmailQueue

from hrms.integrations.pramaan_mail import _addresses, sendmail


class PramaanEmailQueue(EmailQueue):
	def send(self, smtp_server_instance=None, frappe_mail_client=None, force_send=False):
		if self.status in {"Sent", "Sending", "Error"}:
			return
		if not self.can_send_now() and not force_send:
			return
		if self.send_after and frappe.utils.get_datetime(self.send_after) > frappe.utils.now_datetime() and not force_send:
			return
		message = Parser(policy=policy.default).parsestr(self.message)
		body = message.get_body(preferencelist=("html", "plain"))
		if not body or self.attachments:
			self.update_status("Error", error="Resend this message from its original record.", commit=True)
			return
		files = [{"fname": part.get_filename() or "attachment", "fcontent": part.get_payload(decode=True)}
			for part in message.iter_attachments()]
		self.update_status("Sending", commit=True)
		try:
			sendmail(recipients=_addresses(message.get("To")), cc=_addresses(message.get("Cc")),
				bcc=_addresses(message.get("Bcc")), subject=str(message.get("Subject") or "HRMS notification"),
				message=body.get_content(), attachments=files,
				reference_doctype="Email Queue", reference_name=self.name)
		except Exception:
			self.update_status("Error", error="Delivery could not be confirmed. Check its status before trying again.", commit=True)
			return
		for recipient in self.recipients:
			recipient.db_set("status", "Sent")
		self.update_status("Sent", commit=True)
