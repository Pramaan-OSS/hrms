"""App mail goes to the platform through the single Pramaan client.

One drop-in replacement for the app's outgoing mail: the call sites keep
their local templates, recipients and permission checks, and this module
owns the transport, idempotency and error boundaries.
"""

import json
import mimetypes
import uuid
from email.utils import getaddresses

import frappe
import frappe.utils
from frappe import _


def _client():
    from hrms.pramaan import PramaanClient

    return PramaanClient()


def _render_template(template, args):
	"""Resolve a template exactly like the platform send: an app HTML file from
	templates/emails, falling back to a stored Email Template record."""
	if template in {"password_reset", "new_user"}:
		context = args or {}
		link = frappe.utils.escape_html(str(context.get("link") or ""))
		title = "Reset your HRMS password" if template == "password_reset" else "Complete your HRMS account"
		return title, f'<p>{title}</p><p><a href="{link}">Continue to HRMS</a></p>'
	from frappe.utils.jinja import get_email_from_template

	try:
		message, _text = get_email_from_template(template, args or {})
		return None, message
	except Exception:
		doc = frappe.get_doc("Email Template", template)
		context = args or {}
		return frappe.render_template(doc.subject, context), frappe.render_template(doc.response, context)


def _wrap(message, header):
	body = message or ""
	if header:
		body = f"<div style='margin-bottom:16px;font-size:16px'>{frappe.utils.escape_html(str(header))}</div>{body}"
	return (
		"<div style='font-family:Helvetica,Arial,sans-serif;font-size:14px;line-height:1.5'>"
		+ body
		+ "</div>"
	)


def _addresses(value):
	values = value if isinstance(value, list | tuple) else [value or ""]
	return list(dict.fromkeys(address for _, address in getaddresses(values) if address))


def _attachments(attachments):
	files = []
	for attachment in attachments or []:
		if isinstance(attachment, str) or attachment.get("file_url"):
			ref = attachment if isinstance(attachment, str) else attachment["file_url"]
			file = frappe.get_doc("File", {"file_url": ref} if ref.startswith("/") else ref)
			file.check_permission("read")
			content, filename = file.get_content(), file.file_name
		else:
			content = attachment.get("fcontent") or attachment.get("content") or b""
			filename = attachment.get("fname") or attachment.get("filename") or "attachment"
		if isinstance(content, str):
			content = content.encode()
		files.append({"name": filename, "content": content})
	if len(files) > 10 or sum(len(file["content"]) for file in files) > 6_000_000:
		frappe.throw(_("Email attachments must be at most 10 files and 6 MB combined."))
	return files


def install_transport(**kwargs):
	"""Include framework password, welcome and notification mail in the same boundary."""
	import frappe.email

	frappe.sendmail = sendmail
	frappe.email.sendmail = sendmail


def _queue_for_later(inputs, files, due, key, reference_doctype, reference_name, communication=None):
	from email.message import EmailMessage

	name = "HRMS-" + key
	if not frappe.db.exists("Email Queue", name):
		message = EmailMessage()
		message["From"] = inputs["from"]
		message["Subject"] = inputs["subject"]
		for header, field in (("To", "to"), ("Cc", "cc"), ("Bcc", "bcc")):
			if inputs.get(field):
				message[header] = ", ".join(inputs[field])
		message.set_content(inputs["html"], subtype="html")
		for file in files:
			mime = mimetypes.guess_type(file["name"])[0] or "application/octet-stream"
			main, sub = mime.split("/", 1)
			message.add_attachment(file["content"], maintype=main, subtype=sub, filename=file["name"])
		frappe.get_doc({"doctype": "Email Queue", "sender": inputs["from"], "status": "Not Sent",
			"message": message.as_string(), "send_after": due,
			"reference_doctype": reference_doctype, "reference_name": reference_name, "communication": communication,
			"recipients": [{"recipient": address, "status": "Not Sent"} for address in
				list(dict.fromkeys(inputs["to"] + inputs.get("cc", []) + inputs.get("bcc", [])))]
		}).insert(ignore_permissions=True, set_name=name)
	return {"name": name, "status": "queued"}


def sendmail(
	recipients=None,
	sender=None,
	subject=None,
	message=None,
	template=None,
	args=None,
	header=None,
	attachments=None,
	reference_doctype=None,
	reference_name=None,
	send_after=None,
	**ignored,
):
	"""Send one message through the platform; never retried on uncertainty."""
	if template:
		template_subject, template_message = _render_template(template, args)
		subject = subject or template_subject
		message = message or template_message

	client = _client()
	try:
		client.require_configured()
	except Exception as error:
		_safe_error(error, reference_doctype, reference_name)
	from_address = frappe.db.get_single_value("HR Settings", "pramaan_email_from")
	if not from_address:
		frappe.throw(_("Email is not set up yet. Set Application Email Sender in HR Settings."), frappe.OutgoingEmailError)
	inputs = {
		"from": from_address,
		"to": _addresses(recipients),
		"subject": subject or "HRMS notification",
		"html": _wrap(message or ignored.get("content"), header),
	}
	for field in ("cc", "bcc"):
		if _addresses(ignored.get(field)):
			inputs[field] = _addresses(ignored[field])
	if _addresses(ignored.get("reply_to")):
		inputs["replyTo"] = _addresses(ignored["reply_to"])[0]
	if reference_doctype and reference_name:
		inputs["tags"] = {"record": uuid.uuid5(uuid.NAMESPACE_URL, f"{reference_doctype}:{reference_name}").hex}
	files = _attachments(attachments)
	# Hash the logical content before uploads: a repeated send reuses its key,
	# while a new password-reset link or attachment gets a distinct one.
	key_parts = {**inputs, "reference": [reference_doctype, reference_name], "due": str(send_after or ""),
		"files": [{"name": file["name"], "content": file["content"].hex()} for file in files]}
	idempotency_key = str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(key_parts, sort_keys=True)))
	if send_after and frappe.utils.get_datetime(send_after) > frappe.utils.now_datetime():
		return _queue_for_later(inputs, files, send_after, idempotency_key, reference_doctype, reference_name, ignored.get("communication"))
	try:
		if files:
			inputs["attachments"] = []
			for file in files:
				content_type = mimetypes.guess_type(file["name"])[0] or "application/octet-stream"
				file_id = client.upload_file(file["content"],
					kind="image" if content_type.startswith("image/") else "document",
					content_type=content_type)
				inputs["attachments"].append({"fileId": file_id, "name": file["name"]})
		return client.call("email.send", inputs, idempotency_key=idempotency_key)
	except Exception as error:
		_safe_error(error, reference_doctype, reference_name)



def _safe_error(error, reference_doctype, reference_name):
	from hrms.pramaan import MissingPramaanKey, PramaanError

	if isinstance(error, MissingPramaanKey):
		frappe.log_error(title=_("Email not sent"), message=str(error))
		raise frappe.OutgoingEmailError(str(error))
	if isinstance(error, PramaanError) and error.uncertain:
		# The message may have been delivered; never resend automatically.
		message = _("The message may already have been delivered. Check its status before sending again.")
	else:
		message = _("The message could not be sent right now. Please try again later.")
	frappe.log_error(title=_("Email not sent"), message=message)
	raise frappe.OutgoingEmailError(str(message))


def enqueue_sendmail(queue="short", timeout=300, is_async=True, enqueue_after=None, **kwargs):
	"""Queue the send; a due time releases it with the local scheduler."""
	after = kwargs.pop("send_after", None) or enqueue_after
	if after:
		return sendmail(send_after=after, **kwargs)
	frappe.enqueue(
		"hrms.integrations.pramaan_mail.sendmail",
		queue=queue,
		timeout=timeout,
		is_async=is_async,
		**kwargs,
	)
