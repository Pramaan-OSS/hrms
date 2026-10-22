"""Integration-module checks with a minimal frappe stub and the fake transport."""

import importlib
import sys
import types
import unittest
import datetime
from pathlib import Path
from unittest.mock import patch

from test_pramaan_stubs import boundary

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FrappeThrow(Exception):
	pass


def _install_frappe_stub():
	frappe = types.ModuleType("frappe")

	frappe._ = lambda text, *args, **kwargs: (text % args if args else text)
	frappe.session = types.SimpleNamespace(user="tester@example.com")

	def throw(message, *args, **kwargs):
		raise FrappeThrow(str(message))

	frappe.throw = throw
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	frappe.only_for = lambda *a, **k: None
	frappe.log_error = lambda *a, **k: None
	frappe.utils = types.SimpleNamespace(
		cstr=str,
		now=lambda: "2026-10-16 00:00:00",
		get_datetime=lambda value: datetime.datetime.fromisoformat(str(value)),
		time_diff=lambda a, b: a - b,
		comma_and=lambda items: ", ".join(str(item) for item in items),
	)
	frappe._dict = dict
	db = types.SimpleNamespace(get_value=None)
	frappe.db = db

	class Doc:
		def __init__(self, **fields):
			self.__dict__.update(fields)

		def check_permission(self, *args):
			return None

		def add_comment(self, *args, **kwargs):
			return None

		def db_set(self, key, value=None):
			if isinstance(key, dict):
				self.__dict__.update(key)
			else:
				setattr(self, key, value)

	frappe.get_doc = lambda doctype, name=None: Doc(doctype=doctype)
	frappe._frappe_stub_Doc = Doc
	sys.modules["frappe"] = frappe
	return frappe


class FrappeStubCase(unittest.TestCase):
	def setUp(self):
		self.frappe = _install_frappe_stub()
		for name in [
			"hrms.integrations.pramaan_common",
			"hrms.integrations.pramaan_recruiting",
			"hrms.integrations.pramaan_notices",
			"hrms.integrations.pramaan_schedule",
			"hrms.integrations.pramaan_payouts",
		]:
			sys.modules.pop(name, None)

	def load(self, dotted):
		module = importlib.import_module(dotted)
		importlib.reload(module)
		return module

	def fake_client(self, calls):
		class Client:
			def __init__(self):
				self.calls = calls

			def call(self, capability, inputs, **kwargs):
				self.calls.append((capability, inputs, kwargs))
				if capability == "sms.send":
					return {"ref": "sms-ref"}
				if capability == "security.ip.lookup":
					return {"country": "x"}
				if capability == "geo.address.reverse-geocode":
					return {"results": [{"formatted": "Somewhere"}]}
				if capability == "finance.transfer-quote.create":
					return {"quoteId": "quote-1"}
				if capability == "calendar.event.create":
					return {"ref": "event-1"}
				if capability == "meetings.room.create":
					return {"joinUrl": "https://join.example/room"}
				return {}

			def outcome_estimate(self, outcome, body):
				self.calls.append(("estimate", outcome, body, {}))
				return {"plan": "plan-1"}

			def outcome_run(self, outcome, body, plan=None, idempotency_key=None):
				assert plan == "plan-1" or outcome == "candidate.dev.profile"
				self.calls.append(("run", outcome, body, {"plan": plan, "idempotency_key": idempotency_key}))
				return {"status": "done", "requirements": []}

		return Client()


class RecruitingTests(FrappeStubCase):
	def test_screen_resume_sends_content_with_basis_and_criteria(self):
		module = self.load("hrms.integrations.pramaan_recruiting")
		calls = []
		applicant = self.frappe._frappe_stub_Doc(
			doctype="Job Applicant", name="APPL-1", resume_attachment="FILE-1"
		)
		file = self.frappe._frappe_stub_Doc(
			doctype="File", name="FILE-1", file_name="cv.pdf"
		)
		file.get_content = lambda: b"resume-bytes"
		self.frappe.get_doc = lambda doctype, name=None: applicant if doctype == "Job Applicant" else file
		with patch.object(module, "get_client", return_value=self.fake_client(calls)):
			result = module.screen_resume("APPL-1", ["three years of support"])
		self.assertTrue(result["available"])
		kind, outcome, body, kwargs = calls[0]
		self.assertEqual((kind, outcome), ("estimate", "resume.screen"))
		inputs = body["input"]
		import base64

		self.assertEqual(base64.b64decode(inputs["content"]), b"resume-bytes")
		self.assertEqual(inputs["extension"], "pdf")
		self.assertEqual(inputs["criteria"], ["three years of support"])
		self.assertEqual(body["basis"]["ground"], "consent")
		self.assertEqual(result["report"]["status"], "done")

	def test_resume_attachment_url_is_resolved_with_file_permissions(self):
		module = self.load("hrms.integrations.pramaan_recruiting")
		applicant = self.frappe._frappe_stub_Doc(resume_attachment="/private/files/cv.pdf")
		file = self.frappe._frappe_stub_Doc(file_name="cv.pdf")
		file.get_content = lambda: b"private resume"
		permissions = []
		file.check_permission = lambda permission: permissions.append(permission)
		def lookup(doctype, key):
			self.assertEqual((doctype, key), ("File", {"file_url": "/private/files/cv.pdf"}))
			return file
		self.frappe.get_doc = lookup
		self.assertEqual(module._resume_file_bytes(applicant), (b"private resume", "pdf"))
		self.assertEqual(permissions, ["read"])

	def test_receipt_attachment_url_is_read_before_extraction(self):
		module = self.load("hrms.integrations.pramaan_receipts")
		claim = self.frappe._frappe_stub_Doc(expenses=[{"receipt_attachment": "/private/files/receipt.pdf"}], currency="USD")
		file = self.frappe._frappe_stub_Doc(file_name="receipt.pdf")
		file.get_content = lambda: b"private receipt"
		def lookup(doctype, key):
			if doctype == "Expense Claim":
				return claim
			self.assertEqual(key, {"file_url": "/private/files/receipt.pdf"})
			return file
		self.frappe.get_doc = lookup
		client = types.SimpleNamespace(call=lambda *args: {"data": {"amount": 12}, "truncated": False})
		with patch.object(module, "get_client", return_value=client):
			result = module.extract_from_claim("CLAIM-1")
		self.assertEqual(result["suggestion"]["amount"], 12)

	def test_resume_reader_unwraps_the_canonical_candidate(self):
		module = self.load("hrms.integrations.pramaan_recruiting")
		self.frappe.get_doc = lambda *a: self.frappe._frappe_stub_Doc()
		client = boundary.PramaanClient(api_key="fixture", transport=boundary.PramaanClient._fake)
		with patch.object(module, "_resume_file_bytes", return_value=(b"resume", "pdf")), patch.object(module, "get_client", return_value=client):
			result = module.parse_resume("APPL-1")
		self.assertEqual(result["candidate"]["fullName"], "Local fixture candidate")
		self.assertNotIn("candidate", result["candidate"])

	def test_truncated_receipt_data_is_not_proposed_as_a_claim_amount(self):
		module = self.load("hrms.integrations.pramaan_receipts")
		claim = self.frappe._frappe_stub_Doc(expenses=[{"receipt_attachment": "/private/files/receipt.pdf"}], currency="INR")
		file = self.frappe._frappe_stub_Doc(file_name="receipt.pdf")
		file.get_content = lambda: b"receipt"
		self.frappe.get_doc = lambda dt, name: claim if dt == "Expense Claim" else file
		client = types.SimpleNamespace(call=lambda *a: {"data": {"amount": 100}, "truncated": True})
		with patch.object(module, "get_client", return_value=client):
			result = module.extract_from_claim("CLAIM-1")
		self.assertIsNone(result["suggestion"])

	def test_salary_lookup_requires_a_location_without_calling_the_client(self):
		module = self.load("hrms.integrations.pramaan_recruiting")
		self.frappe.get_doc = lambda *a: self.frappe._frappe_stub_Doc(location="  ")
		with patch.object(module, "get_client") as client:
			with self.assertRaisesRegex(FrappeThrow, "Set the job location"):
				module.suggest_salary_range("OPENING-1")
		client.assert_not_called()

	def test_salary_lookup_uses_the_catalogue_country_code(self):
		module = self.load("hrms.integrations.pramaan_recruiting")
		self.frappe.get_doc = lambda *args: self.frappe._frappe_stub_Doc(company="QA Company", designation="Engineer", job_title="Engineer", location="London")
		self.frappe.db.get_value = lambda doctype, *args: "United Kingdom" if doctype == "Company" else "gb"
		calls = []
		with patch.object(module, "get_client", return_value=self.fake_client(calls)):
			module.suggest_salary_range("OPENING-1")
		self.assertEqual(calls[0][1]["country"], "GB")

	def test_screen_resume_refuses_bad_criteria_count(self):
		module = self.load("hrms.integrations.pramaan_recruiting")
		with self.assertRaises(FrappeThrow):
			module.screen_resume("APPL-1", [])


class NoticeTests(FrappeStubCase):
	def test_interviewer_user_resolves_to_the_opted_in_employee_before_sending(self):
		module = self.load("hrms.integrations.pramaan_notices")
		self.frappe.get_doc = lambda *a: self.frappe._frappe_stub_Doc(name="INT-1", scheduled_on="2026-10-18", from_time="10:00:00", interview_details=[types.SimpleNamespace(interviewer="interviewer@example.test")])
		def employee_value(doctype, name, field=None):
			if isinstance(name, dict):
				self.assertEqual(name, {"user_id": "interviewer@example.test", "status": "Active"})
				return "EMP-1"
			return {"receive_text_notices": 1, "cell_number": "+15550001111"}.get(field)
		self.frappe.db.get_value = employee_value
		calls = []
		with patch.object(module, "get_client", return_value=self.fake_client(calls)):
			result = module.send_interview_sms("INT-1")
		self.assertEqual(result["sent"], 1)
		self.assertEqual(calls[0][0], "sms.send")
		self.assertEqual(calls[0][2]["idempotency_key"], "Interview:INT-1:EMP-1")

	def test_opt_in_gates_the_text(self):
		module = self.load("hrms.integrations.pramaan_notices")
		calls = []
		self.frappe.db.get_value = lambda doctype, name, field=None: 0
		with patch.object(module, "get_client", return_value=self.fake_client(calls)):
			self.assertFalse(module.send_employee_sms("EMP-1", "hello"))
		self.assertEqual(calls, [])

		def employee_value(doctype, name, field=None):
			if field == "receive_text_notices":
				return 1
			if field == "cell_number":
				return "0555"  # not E.164
			return None

		self.frappe.db.get_value = employee_value
		with patch.object(module, "get_client", return_value=self.fake_client(calls)):
			self.assertFalse(module.send_employee_sms("EMP-1", "hello"))
		self.assertEqual(calls, [])

		def employee_value2(doctype, name, field=None):
			if field == "receive_text_notices":
				return 1
			if field == "cell_number":
				return "+15550001111"
			return None

		self.frappe.db.get_value = employee_value2
		with patch.object(module, "get_client", return_value=self.fake_client(calls)):
			self.assertTrue(module.send_employee_sms("EMP-1", "hello", "Doc", "DOC-1"))
		self.assertEqual(calls[0][0], "sms.send")
		self.assertEqual(calls[0][1]["to"], "+15550001111")
		self.assertEqual(calls[0][2]["idempotency_key"], "Doc:DOC-1:EMP-1")


class ScheduleTests(FrappeStubCase):
	def test_missing_setting_is_a_plain_setup_message(self):
		module = self.load("hrms.integrations.pramaan_schedule")
		self.frappe.db.get_single_value = lambda *args, **kwargs: None
		interview = self.frappe._frappe_stub_Doc(
			doctype="Interview",
			name="INT-1",
			scheduled_on="2026-11-02",
			from_time="10:00:00",
			to_time="11:00:00",
		)
		self.frappe.get_doc = lambda doctype, name=None: interview
		with self.assertRaises(FrappeThrow) as raised:
			module.schedule_interview("INT-1")
		self.assertIn("connected_calendar_inbox", str(raised.exception))

	def test_schedule_creates_room_and_event_with_idempotency(self):
		module = self.load("hrms.integrations.pramaan_schedule")
		calls = []
		values = {
			"connected_calendar_inbox": "inbox-1",
			"connected_meeting_app": "meet-1",
		}
		self.frappe.db.get_single_value = lambda *args: values.get(args[-1])
		interview = self.frappe._frappe_stub_Doc(
			doctype="Interview",
			name="INT-1",
			scheduled_on="2026-11-02",
			from_time="10:00:00",
			to_time="11:00:00",
		)
		self.frappe.get_doc = lambda doctype, name=None: interview
		with patch.object(module, "get_client", return_value=self.fake_client(calls)):
			result = module.schedule_interview("INT-1")
		self.assertTrue(result["available"])
		used = {item[0] for item in calls}
		self.assertEqual(used, {"meetings.room.create", "calendar.event.create"})
		for capability, inputs, kwargs in calls:
			self.assertTrue(kwargs.get("idempotency_key"))
		self.assertEqual(calls[0][1]["app"], "meet-1")
		self.assertEqual(calls[1][1]["inbox"], "inbox-1")


class PayoutTests(FrappeStubCase):
	def test_draft_run_cannot_be_approved_or_quoted(self):
		module = self.load("hrms.integrations.pramaan_payouts")
		entry = self.frappe._frappe_stub_Doc(doctype="Payroll Entry", name="PE-1", docstatus=0)
		self.frappe.get_doc = lambda *args: entry
		for action in (module.approve_payout, module.prepare_payout):
			with self.assertRaisesRegex(FrappeThrow, "Submit the payroll run"):
				action("PE-1")

	def test_approval_records_the_signed_in_user(self):
		module = self.load("hrms.integrations.pramaan_payouts")
		entry = self.frappe._frappe_stub_Doc(doctype="Payroll Entry", name="PE-1", docstatus=1)
		self.frappe.get_doc = lambda *args: entry
		module.approve_payout("PE-1")
		self.assertEqual(entry.payout_approved_by, self.frappe.session.user)

	def test_payout_requires_recorded_approval(self):
		module = self.load("hrms.integrations.pramaan_payouts")
		entry = self.frappe._frappe_stub_Doc(
			doctype="Payroll Entry",
			name="PE-1",
			docstatus=1,
			payout_approved_by=None,
			payout_currency="USD",
			payout_amount=1000,
		)
		self.frappe.get_doc = lambda doctype, name=None: entry
		with self.assertRaises(FrappeThrow) as raised:
			module.prepare_payout("PE-1")
		self.assertIn("approval", str(raised.exception))

	def test_payout_quote_uses_profile_and_requires_setup(self):
		module = self.load("hrms.integrations.pramaan_payouts")
		self.frappe.db.get_single_value = lambda *args, **kwargs: None
		entry = self.frappe._frappe_stub_Doc(
			doctype="Payroll Entry",
			name="PE-1",
			docstatus=1,
			payout_approved_by="manager@example.com",
			payout_currency="USD",
			payout_amount=1000,
		)
		self.frappe.get_doc = lambda doctype, name=None: entry
		with self.assertRaises(FrappeThrow) as raised:
			module.prepare_payout("PE-1")
		self.assertIn("payout_profile_id", str(raised.exception))

		calls = []
		self.frappe.db.get_single_value = lambda *args: "profile-1"
		with patch.object(module, "get_client", return_value=self.fake_client(calls)):
			result = module.prepare_payout("PE-1")
		self.assertTrue(result["available"])
		self.assertEqual(calls[0][1]["profileId"], "profile-1")
		self.assertEqual(entry.payout_quote_ref, "quote-1")


if __name__ == "__main__":
	unittest.main()


class RespondMappingTests(FrappeStubCase):
    def load_common(self):
        module = self.load("hrms.integrations.pramaan_common")
        # respond catches the exception classes from the real client module,
        # not the standalone stub copy used by the client tests.
        from hrms.pramaan import ConnectionRequired, PramaanError

        self.real = types.SimpleNamespace(PramaanError=PramaanError, ConnectionRequired=ConnectionRequired)
        return module

    def test_document_action_keeps_its_signature_for_http_dispatch(self):
        from inspect import signature
        from hrms.pramaan import MissingPramaanKey

        module = self.load_common()

        class Assessment:
            @module.respond
            def sync_from_platform(self):
                raise MissingPramaanKey()

        action = Assessment().sync_from_platform
        # The document dispatcher calls a no-argument method without an extra args value.
        self.assertEqual(list(signature(action).parameters), [])
        result = action()
        self.assertFalse(result["available"])
        self.assertEqual(result["message"], "Add PRAMAAN_API_KEY to .env")

    def test_upstream_unavailable_maps_to_plain_not_available(self):
        module = self.load_common()

        @module.respond
        def endpoint():
            raise self.real.PramaanError("upstream_unavailable", uncertain=False)

        result = endpoint()
        self.assertFalse(result["available"])
        self.assertEqual(result["message"], module.NOT_AVAILABLE_MESSAGE)

    def test_connection_required_maps_to_its_plain_message(self):
        module = self.load_common()

        @module.respond
        def endpoint():
            raise self.real.ConnectionRequired("meeting_app")

        result = endpoint()
        self.assertFalse(result["available"])
        self.assertIn("Connect meeting app", result["message"])
        self.assertNotIn("meeting_app", result["message"])


class CandidateCheckTests(FrappeStubCase):
	def load_checks(self):
		return self.load("hrms.integrations.pramaan_checks")

	def test_verify_employment_sends_consent_claims_and_plan(self):
		module = self.load_checks()
		calls = []
		applicant = self.frappe._frappe_stub_Doc(doctype="Job Applicant", name="APPL-9")
		self.frappe.get_doc = lambda doctype, name=None: applicant
		with patch.object(module, "get_client", return_value=self.fake_client(calls)):
			result = module.verify_employment(
				"APPL-9",
				"https://professional.example/in/vera",
				"CONSENT-77",
				claims=[{"employer": "Fixture Ltd"}],
				basis_ground="consent",
			)
		self.assertTrue(result["available"])
		estimate_body = calls[0][2]
		self.assertEqual(estimate_body["input"]["consentRef"], "CONSENT-77")
		self.assertEqual(estimate_body["input"]["claims"], [{"employer": "Fixture Ltd"}])
		self.assertEqual(estimate_body["basis"]["ground"], "consent")
		kind, outcome, body, kwargs = calls[1]
		self.assertEqual((kind, outcome), ("run", "candidate.employment.verify"))
		self.assertEqual(kwargs["plan"], "plan-1")
		self.assertTrue(kwargs["idempotency_key"])

	def test_verify_employment_requires_consent_claims_and_profile(self):
		module = self.load_checks()
		applicant = self.frappe._frappe_stub_Doc(doctype="Job Applicant", name="APPL-9")
		self.frappe.get_doc = lambda doctype, name=None: applicant
		with self.assertRaises(FrappeThrow):
			module.verify_employment("APPL-9", "https://professional.example/in/vera", "", claims=[{"employer": "x"}])
		with self.assertRaises(FrappeThrow):
			module.verify_employment("APPL-9", "https://professional.example/in/vera", "C1", claims=[])
		with self.assertRaises(FrappeThrow):
			module.verify_employment("APPL-9", "not-a-link", "C1", claims=[{"employer": "x"}])

	def test_background_check_requires_consent_and_name(self):
		module = self.load_checks()
		applicant = self.frappe._frappe_stub_Doc(doctype="Job Applicant", name="APPL-9")
		self.frappe.get_doc = lambda doctype, name=None: applicant
		with self.assertRaises(FrappeThrow):
			module.start_background_check("APPL-9", "", "Vera Candidate")
		with self.assertRaises(FrappeThrow):
			module.start_background_check("APPL-9", "C1", "")

	def test_background_check_runs_with_plan_and_idempotency(self):
		module = self.load_checks()
		calls = []
		applicant = self.frappe._frappe_stub_Doc(doctype="Job Applicant", name="APPL-9")
		self.frappe.get_doc = lambda doctype, name=None: applicant
		with patch.object(module, "get_client", return_value=self.fake_client(calls)):
			result = module.start_background_check("APPL-9", "CONSENT-9", "Vera Candidate", date_of_birth="1995-04-01")
		self.assertTrue(result["available"])
		kind, outcome, body, kwargs = calls[1]
		self.assertEqual((kind, outcome), ("run", "candidate.background.check"))
		self.assertEqual(body["input"]["consentRef"], "CONSENT-9")
		self.assertEqual(body["input"]["dateOfBirth"], "1995-04-01")
		self.assertEqual(kwargs["plan"], "plan-1")
		self.assertTrue(kwargs["idempotency_key"])

	def test_dev_profile_runs_read_only_without_plan(self):
		module = self.load_checks()
		calls = []
		applicant = self.frappe._frappe_stub_Doc(doctype="Job Applicant", name="APPL-9")
		self.frappe.get_doc = lambda doctype, name=None: applicant
		with patch.object(module, "get_client", return_value=self.fake_client(calls)):
			result = module.fetch_dev_profile("APPL-9", "CONSENT-5", email="vera@example.com")
		self.assertTrue(result["available"])
		kind, outcome, body, kwargs = calls[1]
		self.assertEqual((kind, outcome), ("run", "candidate.dev.profile"))
		self.assertIsNone(kwargs["plan"])
		self.assertEqual(body["input"]["email"], "vera@example.com")

	def test_dev_profile_needs_a_reference(self):
		module = self.load_checks()
		applicant = self.frappe._frappe_stub_Doc(doctype="Job Applicant", name="APPL-9")
		self.frappe.get_doc = lambda doctype, name=None: applicant
		with self.assertRaises(FrappeThrow):
			module.fetch_dev_profile("APPL-9", "C1")

	def test_client_allowlist_holds_the_hiring_outcomes(self):
		for outcome in (
			"candidate.employment.verify",
			"candidate.background.check",
			"candidate.dev.profile",
		):
			self.assertIn(outcome, boundary.PramaanClient.OUTCOMES)
		self.assertNotIn("people.employment.verify", boundary.PramaanClient.CAPABILITIES)


class LocalSignInTests(FrappeStubCase):
    def test_saved_provider_settings_never_publish_authorization_links(self):
        spec = importlib.util.spec_from_file_location("local_sign_in", Path(__file__).resolve().parents[1] / "hrms/api/oauth.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.frappe.get_all = lambda *args, **kwargs: self.fail("External credentials must not be read")
        self.assertEqual(module.oauth_providers(), [])


class CurrencyBoundaryTests(FrappeStubCase):
    def test_same_currency_never_makes_an_outside_call(self):
        module = self.load("hrms.integrations.pramaan_currency")
        with patch.object(module, "PramaanClient", side_effect=AssertionError("No call expected")):
            self.assertEqual(module.get_exchange_rate("USD", "USD"), 1)

    def test_saved_historical_rate_stays_local(self):
        module = self.load("hrms.integrations.pramaan_currency")
        self.frappe.db.get_value = lambda *args, **kwargs: 80
        with patch.object(module, "PramaanClient", side_effect=AssertionError("No call expected")):
            self.assertEqual(module.get_exchange_rate("USD", "INR", "2026-01-01"), 80)

    def test_remote_rate_uses_the_single_client_and_inverse_direction(self):
        module = self.load("hrms.integrations.pramaan_currency")
        self.frappe.db.get_value = lambda *args, **kwargs: None
        requests = []
        client = types.SimpleNamespace(call=lambda capability, body: (requests.append((capability, body)) or {"inverseRate": 2}))
        with patch.object(module, "PramaanClient", return_value=client):
            self.assertEqual(module.get_exchange_rate("USD", "EUR"), 0.5)
        self.assertEqual(requests, [("finance.exchange-rate.get", {"from": "USD", "to": "EUR"})])


class CalendarConnectionTests(FrappeStubCase):
	def test_setup_uses_the_catalogue_app_id_and_an_action_key(self):
		module = self.load("hrms.integrations.pramaan_connections")
		self.frappe.utils.get_url = lambda path: "http://localhost:18148" + path
		self.frappe.get_doc = lambda *a: self.frappe._frappe_stub_Doc()
		calls = []
		class Client:
			def call(self, capability, inputs, **kwargs):
				calls.append((capability, inputs, kwargs))
				return {"connectUrl": "https://connect.example/fixture"}
		with patch.object(module, "get_client", return_value=Client()):
			result = module.connect_calendar()
		self.assertTrue(result["available"])
		capability, inputs, options = calls[0]
		self.assertEqual(capability, "apps.connection.start")
		self.assertEqual(inputs["app"], "googlecalendar")
		self.assertEqual(inputs["redirectUrl"], "http://localhost:18148/desk/hr-settings")
		self.assertNotIn("@", inputs["endUserRef"])
		self.assertTrue(options["idempotency_key"])

	def test_read_only_settings_cannot_start_a_connection(self):
		module = self.load("hrms.integrations.pramaan_connections")
		doc = self.frappe._frappe_stub_Doc()
		doc.check_permission = lambda *a: self.frappe.throw("Permission denied")
		self.frappe.get_doc = lambda *a: doc
		with patch.object(module, "get_client") as client:
			with self.assertRaisesRegex(FrappeThrow, "Permission denied"):
				module.connect_calendar()
		client.assert_not_called()
