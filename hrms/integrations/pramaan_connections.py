"""Hosted setup links for the application's optional calendar account."""
import uuid
from urllib.parse import urlparse

import frappe
from frappe import _

from hrms.integrations.pramaan_common import get_client, respond
from hrms.pramaan import PramaanError


@frappe.whitelist()
@respond
def connect_calendar():
	frappe.get_doc("HR Settings").check_permission("write")
	user_ref = uuid.uuid5(uuid.NAMESPACE_URL, "hrms-calendar:" + frappe.session.user).hex
	result = get_client().call(
		"apps.connection.start",
		{"endUserRef": user_ref, "app": "googlecalendar", "redirectUrl": frappe.utils.get_url("/desk/hr-settings")},
		idempotency_key="calendar-connect:" + uuid.uuid4().hex,
	)
	url = result.get("connectUrl") or ""
	if urlparse(url).scheme != "https" or not urlparse(url).hostname:
		raise PramaanError("invalid_response")
	return {"connect_url": url}
