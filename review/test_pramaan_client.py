"""Contract and safety tests; every request uses an in-memory fake."""
import unittest
from unittest.mock import patch
from test_pramaan_stubs import boundary


class ClientTests(unittest.TestCase):
    def test_live_assessment_setup_error_is_actionable_without_exposing_the_api_body(self):
        import io, json
        from urllib.error import HTTPError
        payload = io.BytesIO(json.dumps({"error": {"code": "invalid_request", "message": "Set your organisation's name first (PUT /v1/organization)."}}).encode())
        client = boundary.PramaanClient(api_key="fixture", base_url="https://pramaan.test")
        # The HTTP decoder is exercised only through the mocked opener.
        client._transport = client._http
        with patch.object(boundary, "build_opener") as opener:
            opener.return_value.open.side_effect = HTTPError("https://pramaan.test", 400, "bad request", {}, payload)
            with self.assertRaises(boundary.OrganizationNameRequired) as raised:
                client.call("assessment.exam.create", {"title": "QA exam"}, idempotency_key="fixture")
        self.assertIn("Set your organization name", str(raised.exception))
        self.assertNotIn("PUT", str(raised.exception))
        opener.return_value.open.assert_called_once()

    def test_missing_key_is_clear_and_never_calls_transport(self):
        calls = []
        client = boundary.PramaanClient(api_key="", transport=lambda *args: calls.append(args))
        with self.assertRaises(boundary.MissingPramaanKey) as raised:
            client.call("email.send", {})
        self.assertEqual(raised.exception.http_status_code, 422)
        self.assertEqual("Add PRAMAAN_API_KEY to .env", str(raised.exception))
        self.assertFalse(client.configured)
        self.assertEqual(calls, [])

    def test_async_completion_uses_same_job_and_only_one_action(self):
        requests = []
        replies = iter([(202, {"job_id": "job/one", "status": "running"}), (200, {"status": "done", "result": {"ref": "accepted"}})])
        def transport(*args):
            requests.append(args)
            return next(replies)
        client = boundary.PramaanClient(api_key="fake", transport=transport, sleep=lambda _: None)
        self.assertEqual(client.call("email.send", {"to": ["a@example.com"]}, idempotency_key="saved-key"), {"ref": "accepted"})
        self.assertEqual([r[0] for r in requests], ["POST", "GET"])
        self.assertEqual(requests[0][2]["Idempotency-Key"], "saved-key")
        self.assertTrue(requests[1][1].endswith("/jobs/job%2Fone"))

    def test_uncertain_action_is_not_retried_and_error_is_safe(self):
        calls = []
        def transport(*args):
            calls.append(args)
            raise RuntimeError("vendor secret customer data")
        client = boundary.PramaanClient(api_key="fake", transport=transport)
        with self.assertRaises(boundary.PramaanError) as raised:
            client.call("email.send", {}, idempotency_key="saved")
        self.assertTrue(raised.exception.uncertain)
        self.assertNotIn("secret", str(raised.exception))
        self.assertEqual(len(calls), 1)

    def test_invalid_actions_are_rejected_before_transport(self):
        calls = []
        client = boundary.PramaanClient(api_key="fake", transport=lambda *args: calls.append(args))
        for cap in ["invented.capability", "email.send"]:
            with self.assertRaises(boundary.PramaanError):
                client.run(cap, {})
        self.assertEqual(calls, [])

    def test_redirects_never_forward_credentials(self):
        self.assertIsNone(boundary.NoRedirects().redirect_request(None, None, 302, "", {}, "https://elsewhere.example"))

    def test_configuration_rejects_credentials_and_remote_plain_http(self):
        for url in ["http://remote.example", "https://user:password@example.com", "https://example.com?secret=key"]:
            with self.assertRaises(boundary.PramaanError):
                boundary.PramaanClient(base_url=url)

    def test_invalid_completed_result_is_rejected(self):
        client = boundary.PramaanClient(api_key="fake", transport=lambda *args: (202, {"job_id": "one", "status": "done", "result": None}))
        with self.assertRaises(boundary.PramaanError):
            client.call("email.send", {}, idempotency_key="saved")

    def test_http_unavailable_codes_are_preserved_without_upstream_text(self):
        import io
        import json
        from urllib.error import HTTPError
        payload = io.BytesIO(json.dumps({"error": {"code": "upstream_unavailable", "message": "private upstream diagnostics"}}).encode())
        client = boundary.PramaanClient(api_key="fake", base_url="https://pramaan.test")
        # The HTTP decoder is exercised only through the mocked opener.
        client._transport = client._http
        with patch.object(boundary, "build_opener") as opener:
            opener.return_value.open.side_effect = HTTPError("https://pramaan.test", 502, "unavailable", {}, payload)
            with self.assertRaises(boundary.PramaanNotAvailable) as raised:
                client.call("sms.send", {"to": "+15550000000", "text": "x"}, idempotency_key="fixture")
            self.assertEqual(str(raised.exception), "Text messages is not available yet.")
            self.assertNotIn("private", str(raised.exception))
            opener.return_value.open.assert_called_once()
        payload.close()

    def test_generation_boundary_defaults_and_floor(self):
        request = boundary.generation_request({"messages": [{"role": "user", "content": "hello"}]})
        self.assertEqual(request["maxTokens"], 256)
        for bad in [0, 63, "x", True]:
            with self.assertRaises(boundary.PramaanError):
                boundary.generation_request({"messages": [{"role": "user", "content": "hello"}], "maxTokens": bad})
        with self.assertRaises(boundary.PramaanError):
            boundary.generation_request({"prompt": "hello"})

    def test_fixture_mode_never_uses_the_network(self):
        import os
        with patch.dict(os.environ, {"PRAMAAN_FAKE": "1"}):
            client = boundary.PramaanClient(api_key="fixture")
            result = client.call("assessment.invitation.create", {"ref": "exam", "email": "c@example.com"}, idempotency_key="fixture")
            self.assertEqual(result["ref"], "fixture-invitation-ref")
            self.assertIn("link", result)

    def test_outcome_run_rejects_unknown_outcome_and_reports(self):
        client = boundary.PramaanClient(api_key="fake", transport=lambda *args: (200, {}))
        with self.assertRaises(boundary.PramaanError):
            client.outcome_run("invented.outcome", {})
        seen = []
        def transport(method, url, headers, body):
            seen.append((method, url))
            if method == "GET":
                return 200, {"available": True, "effect_class": "read_only", "requires_approval": False}
            return 200, {"status": "done", "requirements": [{"requirement": "r", "verdict": "not_checked"}]}
        client = boundary.PramaanClient(api_key="fake", transport=transport)
        report = client.outcome_run("resume.screen", {"input": {}})
        self.assertEqual(report["status"], "done")
        self.assertEqual(seen[0][0], "GET")

    def test_outcome_missing_plan_is_refused_before_run(self):
        def transport(method, url, headers, body):
            if method == "GET":
                return 200, {"available": True, "effect_class": "read_only", "requires_approval": True}
            raise AssertionError("run must not start without the reviewed plan")
        client = boundary.PramaanClient(api_key="fake", transport=transport)
        with self.assertRaises(boundary.PramaanError):
            client.outcome_run("candidate.match", {"input": {}})


class AvailabilityContractTests(unittest.TestCase):
    def test_upstream_unavailable_capability_is_plain_not_available(self):
        def transport(method, url, headers, body):
            return 400, {"error": {"code": "upstream_unavailable", "retryable": False}}
        client = boundary.PramaanClient(api_key="fake", transport=transport)
        with self.assertRaises(boundary.PramaanNotAvailable) as raised:
            client.call("sms.send", {"to": "+15550000000", "body": "x"}, idempotency_key="k")
        self.assertEqual(str(raised.exception), "Text messages is not available yet.")

    def test_upstream_unavailable_outcome_run_is_not_uncertain(self):
        calls = []
        def transport(method, url, headers, body):
            calls.append((method, url))
            if method == "GET":
                return 200, {"available": True, "effect_class": "read_only", "requires_approval": False}
            return 400, {"error": {"code": "upstream_unavailable", "retryable": False}}
        client = boundary.PramaanClient(api_key="fake", transport=transport)
        with self.assertRaises(boundary.PramaanError) as raised:
            client.outcome_run("resume.screen", {"input": {"criteria": ["x"]}})
        self.assertEqual(raised.exception.code, "upstream_unavailable")
        self.assertFalse(raised.exception.uncertain)

    def test_estimate_connection_required_is_a_plain_setup_message(self):
        def transport(method, url, headers, body):
            if method == "GET":
                return 200, {"available": True, "effect_class": "read_only", "requires_approval": False}
            return 200, {"can_run": False, "reason": "connection_required", "slot": "meeting_app"}
        client = boundary.PramaanClient(api_key="fake", transport=transport)
        with self.assertRaises(boundary.ConnectionRequired) as raised:
            client.outcome_estimate("resume.screen", {"input": {"criteria": ["x"]}})
        message = str(raised.exception)
        self.assertIn("connected account", message)
        self.assertIn("meeting app", message)
        self.assertNotIn("meeting_app", message)
        for provider in ("google", "zoom", "teams", "caldav"):
            self.assertNotIn(provider, message.lower())


class AssessmentReadContracts(unittest.TestCase):
    def test_assessment_reads_use_post_and_poll_without_retry_keys(self):
        requests = []
        def transport(*args):
            requests.append(args)
            return boundary.PramaanClient._fake(*args)
        client = boundary.PramaanClient(api_key="fixture", transport=transport)
        for capability in ("assessment.exam.get", "assessment.exams.list", "assessment.questions.list",
                           "assessment.invitations.list", "assessment.invitation.get", "assessment.session.get",
                           "assessment.result.get", "assessment.integrity-report.get"):
            client.call(capability, {"ref": "fixture-ref"})
        self.assertEqual(len(requests), 8)
        self.assertTrue(all(request[0] == "POST" for request in requests))
        self.assertTrue(all("Idempotency-Key" not in request[2] for request in requests))
