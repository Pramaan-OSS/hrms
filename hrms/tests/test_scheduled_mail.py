"""Scheduled messages stay local until due and never enter the old mail transport."""
from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from hrms.integrations import pramaan_mail
from hrms.pramaan import PramaanClient, PramaanError


class TestScheduledMail(IntegrationTestCase):
	def setUp(self):
		frappe.db.set_single_value("HR Settings", "pramaan_email_from", "notifications@example.test")
		self.requests = []
		def transport(*args):
			self.requests.append(args)
			return PramaanClient._fake(*args)
		self.client = PramaanClient(api_key="fixture", transport=transport)
		self.client_patch = patch.object(pramaan_mail, "_client", return_value=self.client)
		self.client_patch.start()
		self.addCleanup(self.client_patch.stop)

	def queued(self):
		result = pramaan_mail.sendmail(recipients=["qa@example.test"], subject="Scheduled " + frappe.generate_hash(),
			message="Future payslip", attachments=[{"fname": "payslip.pdf", "fcontent": b"%PDF-fixture"}],
			send_after=now_datetime() + timedelta(hours=1))
		return frappe.get_doc("Email Queue", result["name"])

	def test_future_message_does_not_upload_or_send(self):
		doc = self.queued()
		doc.send()
		self.assertEqual(doc.status, "Not Sent")
		self.assertEqual(self.requests, [])

	def test_due_message_sends_once_with_its_private_attachment(self):
		doc = self.queued()
		doc.send_after = now_datetime() - timedelta(minutes=1)
		with patch.object(doc, "can_send_now", return_value=True), patch.object(frappe.db, "commit"):
			doc.send()
		self.assertEqual(frappe.db.get_value("Email Queue", doc.name, "status"), "Sent")
		self.assertEqual(len(self.requests), 2)
		self.assertEqual(self.requests[0][3], b"%PDF-fixture")
		self.assertIn("fileId", self.requests[1][3]["attachments"][0])
		doc.reload()
		doc.send(force_send=True)
		self.assertEqual(len(self.requests), 2)

	def test_uncertain_delivery_is_never_retried_automatically(self):
		doc = self.queued()
		doc.send_after = now_datetime() - timedelta(minutes=1)
		with patch.object(self.client, "call", side_effect=PramaanError("unavailable", uncertain=True)) as send:
			with patch.object(doc, "can_send_now", return_value=True), patch.object(frappe.db, "commit"):
				doc.send()
			doc.reload()
			doc.send(force_send=True)
			self.assertEqual(send.call_count, 1)
		self.assertEqual(doc.status, "Error")

	def test_document_composer_queues_without_original_mail_account(self):
		from hrms.integrations.pramaan_mail.composer import make
		result = make(recipients="qa@example.test", subject="QA composer " + frappe.generate_hash(),
			content="Synthetic local message", send_email=True)
		self.assertTrue(frappe.db.exists("Email Queue", {"communication": result["name"], "status": "Not Sent"}))
		self.assertEqual(self.requests, [])

	def test_undo_removes_queued_message_before_any_external_effect(self):
		from hrms.integrations.pramaan_mail.composer import make
		from frappe.core.doctype.communication.email import undo_email_send
		result = make(recipients="qa@example.test", subject="QA undo " + frappe.generate_hash(),
			content="Synthetic local message", send_email=True)
		undo_email_send(result["name"])
		self.assertFalse(frappe.db.exists("Email Queue", {"communication": result["name"]}))
		self.assertEqual(self.requests, [])
