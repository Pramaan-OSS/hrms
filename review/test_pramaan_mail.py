"""Mail contracts at the app/framework boundary, using no network transport."""
import html
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from test_pramaan_stubs import boundary


class MailBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.frappe = types.ModuleType("frappe")
        utils = types.ModuleType("frappe.utils")
        utils.escape_html = html.escape
        self.frappe.utils = utils
        self.frappe._ = lambda message: message
        self.frappe.OutgoingEmailError = ValueError
        self.frappe.db = types.SimpleNamespace(get_single_value=lambda *args: "notifications@example.test")
        self.frappe.throw = lambda message, *args: (_ for _ in ()).throw(ValueError(message))
        self.frappe.log_error = lambda **kwargs: None
        email = types.ModuleType("frappe.email")
        self.frappe.email = email
        self.modules = patch.dict(sys.modules, {"frappe": self.frappe, "frappe.utils": utils, "frappe.email": email})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        path = Path(__file__).resolve().parents[1] / "hrms/integrations/pramaan_mail/__init__.py"
        spec = importlib.util.spec_from_file_location("mail_boundary_test", path)
        self.mail = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mail)

        def transport(*args):
            self.requests.append(args)
            return boundary.PramaanClient._fake(*args)

        self.client = boundary.PramaanClient(api_key="fixture", transport=transport)
        self.mail._client = lambda: self.client

    def send(self, **kwargs):
        return self.mail.sendmail(recipients="QA Person <person@example.test>", subject="QA notice", **kwargs)

    def test_application_sender_has_one_default_setting(self):
        import json
        fields = json.loads((Path(__file__).resolve().parents[1] / "hrms/hr/doctype/hr_settings/hr_settings.json").read_text())["fields"]
        sender = next(field for field in fields if field["fieldname"] == "pramaan_email_from")
        self.assertEqual(sender["default"], "HRMS <noreply@updates.pramaan.one>")
        self.frappe.db.get_single_value = lambda *args: sender["default"]
        self.send(message="Notice")
        self.assertEqual(self.requests[-1][3]["from"], sender["default"])

    def test_framework_mail_uses_the_same_sender_and_transport(self):
        self.mail.install_transport()
        self.assertIs(self.frappe.sendmail, self.mail.sendmail)
        self.assertIs(self.frappe.email.sendmail, self.mail.sendmail)
        self.frappe.sendmail(recipients="QA <qa@example.test>", subject="Reset", content="New reset link")
        body = self.requests[-1][3]
        self.assertEqual(body["from"], "notifications@example.test")
        self.assertEqual(body["to"], ["qa@example.test"])
        self.assertIn("New reset link", body["html"])

    def test_private_attachment_is_uploaded_before_sending_by_reference(self):
        self.send(message="Receipt", cc="copy@example.test", bcc="hidden@example.test",
                  attachments=[{"fname": "receipt.pdf", "fcontent": b"%PDF-fixture"}],
                  reference_doctype="Expense Claim", reference_name="QA-CLAIM-1")
        upload, send = self.requests
        self.assertTrue(upload[1].endswith("/v1/files?kind=document"))
        self.assertEqual(upload[2]["Content-Type"], "application/pdf")
        self.assertEqual(upload[3], b"%PDF-fixture")
        self.assertEqual(send[3]["attachments"], [{"fileId": "file_01ARZ3NDEKTSV4RRFFQ69G5FAV", "name": "receipt.pdf"}])
        self.assertEqual(send[3]["cc"], ["copy@example.test"])
        self.assertEqual(send[3]["bcc"], ["hidden@example.test"])
        self.assertIsInstance(send[3]["tags"], dict)

    def test_upload_keys_cover_the_content_and_are_stable_for_retries(self):
        for content in (b"first", b"first", b"second"):
            self.client.upload_file(content, kind="document", content_type="application/pdf")
        keys = [request[2]["Idempotency-Key"] for request in self.requests]
        self.assertEqual(keys[0], keys[1])
        self.assertNotEqual(keys[0], keys[2])

    def test_new_reset_link_has_a_new_key_but_retry_reuses_the_key(self):
        for link in ("first", "first", "second"):
            self.send(template="password_reset", args={"link": "http://localhost/update-password?key=" + link})
        keys = [request[2]["Idempotency-Key"] for request in self.requests]
        self.assertEqual(keys[0], keys[1])
        self.assertNotEqual(keys[0], keys[2])

    def test_attachment_limits_are_checked_before_any_upload(self):
        with self.assertRaises(ValueError):
            self.send(message="Too many", attachments=[{"fname": "file.txt", "fcontent": b"x"}] * 11)
        self.assertEqual(self.requests, [])

    def test_missing_key_uses_the_framework_mail_error_with_setup_instructions(self):
        from hrms.pramaan import PramaanClient
        self.mail._client = lambda: PramaanClient(api_key="")
        with self.assertRaisesRegex(ValueError, "Add PRAMAAN_API_KEY"):
            self.send(message="Notice")
        self.assertEqual(self.requests, [])

    def test_sender_must_be_configured_before_sending(self):
        self.frappe.db.get_single_value = lambda *args: ""
        with self.assertRaisesRegex(ValueError, "Application Email Sender"):
            self.send(message="Notice")
        self.assertEqual(self.requests, [])

    def test_fake_transport_rejects_the_old_attachment_contract(self):
        with self.assertRaises(boundary.PramaanError):
            self.client.call("email.send", {"to": ["qa@example.test"], "subject": "Notice", "html": "Text",
                             "attachments": [{"filename": "receipt.pdf", "content": "raw"}]},
                             idempotency_key="fixture")


    def test_future_mail_is_held_locally_without_uploading_or_sending(self):
        from datetime import datetime
        self.frappe.utils.get_datetime = datetime.fromisoformat
        self.frappe.utils.now_datetime = lambda: datetime(2026, 10, 17)
        with patch.object(self.mail, "_queue_for_later", return_value={"status": "queued"}) as queue:
            result = self.send(message="Future payslip", send_after="2026-10-18")
        self.assertEqual(result["status"], "queued")
        self.assertEqual(self.requests, [])
        self.assertEqual(queue.call_args.args[2], "2026-10-18")
