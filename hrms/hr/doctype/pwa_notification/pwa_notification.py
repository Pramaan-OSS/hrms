# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
import frappe
from frappe.model.document import Document

import hrms


class PWANotification(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from_user: DF.Link | None
		message: DF.TextEditor | None
		name: DF.Int | None
		read: DF.Check
		reference_document_name: DF.Data | None
		reference_document_type: DF.Link | None
		to_user: DF.Link | None
	# end: auto-generated types

	def on_update(self):
		hrms.refetch_resource("hrms:notifications", self.to_user)

	def after_insert(self):
		self.send_push_notification()

	def send_push_notification(self):
		try:
			from html import unescape as _unescape
			from re import sub as _sub

			from hrms.pramaan import PramaanClient

			PramaanClient().call(
				"notify.push.send",
				{
					"subscriberId": self.to_user,
					"title": self.reference_document_type or "HRMS",
					"body": _sub(r"<[^>]+>", "", _unescape(self.message or ""))[:280],
					"data": {"url": self.get_notification_link()},
				},
				idempotency_key=f"{self.doctype}:{self.name}",
			)
		except ImportError:
			# the single client is not importable in this runtime
			pass
		except Exception:
			# Delivery is best-effort; the in-app notification is already saved.
			self.log_error(f"Error sending push notification: {self.name}")

	def get_notification_link(self):
		base_url = f"{frappe.utils.get_url()}/hrms"

		if self.reference_document_type == "Leave Application":
			return f"{base_url}/leave-applications/{self.reference_document_name}"
		elif self.reference_document_type == "Expense Claim":
			return f"{base_url}/expense-claims/{self.reference_document_name}"

		return base_url
