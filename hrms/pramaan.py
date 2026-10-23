"""All outside service calls go through this server-side module."""

import copy
import hashlib
import json
import math
import os
import time
from dataclasses import dataclass
from typing import ClassVar, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

Feature = Literal[
    "transactional_email", "writing_help", "ip_insights", "check_in_addresses",
    "push_notifications", "sms_notices", "document_intake", "recruiting_insights",
    "scheduling", "identity_checks", "payroll_payouts", "assessments",
]


class CapabilityUnavailable(RuntimeError):
    """A stable application error safe to show without request data or secrets."""

    code = "capability_unavailable"

    def __init__(self, feature: Feature):
        self.feature = feature
        messages = {
            "transactional_email": "Email sending is not available yet.",
            "writing_help": "Writing help is not available yet.",
            "ip_insights": "Address lookup is not available yet.",
            "check_in_addresses": "Address lookup is not available yet.",
            "push_notifications": "Push notifications are not available yet.",
            "sms_notices": "Text messages are not available yet.",
            "document_intake": "Document reading is not available yet.",
            "recruiting_insights": "Recruiting insights are not available yet.",
            "scheduling": "Calendars and meeting rooms are not available yet.",
            "identity_checks": "Identity checks are not available yet.",
            "payroll_payouts": "Payouts are not available yet.",
            "assessments": "Assessments are not available yet.",
        }
        super().__init__(messages[feature])


@dataclass(frozen=True)
class FeatureAvailability:
    feature: Feature
    enabled: bool
    reason: str


class PramaanError(RuntimeError):
    """Normalized error: never expose an upstream body, provider or secret."""

    def __init__(self, code="unavailable", *, uncertain=False, job_id=None):
        self.code = code
        self.uncertain = uncertain
        self.job_id = job_id
        super().__init__(
            "The action may already have completed. Check its status before trying again."
            if uncertain else "Pramaan could not complete this request."
        )


MISSING_KEY_MESSAGE = "Add PRAMAAN_API_KEY to .env"


class MissingPramaanKey(PramaanError):
    http_status_code = 422

    def __init__(self):
        super().__init__("missing_api_key")
        self.args = (MISSING_KEY_MESSAGE,)


class OrganizationNameRequired(PramaanError):
    http_status_code = 422

    def __init__(self):
        super().__init__("organization_name_required")
        self.args = ("Set your organization name in your Pramaan account before creating an assessment.",)


class InvalidGenerationRequest(PramaanError):
    http_status_code = 422

    def __init__(self, label, path, reason):
        super().__init__("invalid_request")
        self.args = (f"{label} schema at {path}: {reason}",)


class IncompleteGeneration(PramaanError):
    http_status_code = 422

    def __init__(self):
        super().__init__("incomplete_reply")
        self.args = ("The reply is incomplete because it reached the reply limit. Retry this step manually with a larger reply limit.",)


class GenerationConfigurationError(PramaanError):
    http_status_code = 422

    def __init__(self):
        super().__init__("reply_limit_configuration")
        self.args = ("The reply limit is too small to produce an answer. Ask your administrator to increase the reply limit before retrying.",)


def generation_result(capability, inputs, result):
    if capability in {"llm.chat", "llm.complete"} and result.get("finishReason") == "length":
        if inputs.get("jsonSchema") or inputs.get("tools") or result.get("toolCalls"):
            raise IncompleteGeneration()
    return result


class PramaanNotAvailable(PramaanError):
    http_status_code = 503

    def __init__(self, capability):
        super().__init__("not_available_yet")
        surface = "Email sending" if capability.startswith("email.") else (
            "Push notifications" if capability.startswith("notify.") else (
            "Text messages" if capability.startswith("sms.") else (
            "Address lookup" if capability.startswith(("geo.", "security.ip.")) else (
            "Document reading" if capability.startswith("document.") else (
            "Recruiting insights" if capability.startswith("job.") else (
            "Calendars and meeting rooms" if capability.startswith(("calendar.", "meetings.")) else (
            "Identity checks" if capability.startswith("identity.") else (
            "Assessments" if capability.startswith("assessment.") else (
            "Employment verification" if capability.startswith("people.") else (
            "Payouts"))))))))))
        self.args = (f"{surface} is not available yet.",)


class ConnectionRequired(PramaanError):
    """The estimate needs an account the person has not connected yet."""

    http_status_code = 422

    def __init__(self, slot=""):
        super().__init__("connection_required")
        slot = (slot or "").strip().replace("_", " ")
        message = (
            f"This feature needs a connected account. Connect {slot} first."
            if slot else "This feature needs a connected account. Connect it first."
        )
        self.args = (message,)


SCHEMA_KEYS = frozenset({"type", "properties", "required", "additionalProperties", "items",
    "enum", "const", "anyOf", "$defs", "$ref", "title", "description", "default", "examples",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength",
    "minItems", "maxItems"})
SCHEMA_TYPES = frozenset({"object", "array", "string", "number", "integer", "boolean", "null"})
SCHEMA_BOUNDS = frozenset({"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minLength", "maxLength", "minItems", "maxItems"})
UNAVAILABLE_CODES = frozenset({"upstream_unavailable", "not_available_yet", "not_available",
    "capability_unavailable", "not_implemented", "unsupported_capability"})
NOT_AVAILABLE_PREFIXES = ("email.", "notify.", "sms.", "geo.", "security.ip.", "document.",
    "job.", "calendar.", "meetings.", "identity.", "people.", "finance.", "assessment.")


def _schema_path(path, key):
    return path + "/" + str(key).replace("~", "~0").replace("/", "~1")


def _schema_json(value, label, path="#", stack=None, depth=0):
    stack = set() if stack is None else stack
    if depth > 32:
        raise InvalidGenerationRequest(label, path, "JSON value is too deep")
    if value is None or isinstance(value, str | bool | int):
        return
    if isinstance(value, float) and math.isfinite(value):
        return
    if not isinstance(value, dict | list) or id(value) in stack:
        raise InvalidGenerationRequest(label, path, "must contain finite JSON values without cycles")
    stack.add(id(value))
    for key, item in (value.items() if isinstance(value, dict) else enumerate(value)):
        if not isinstance(key, str | int) or (isinstance(value, dict) and not isinstance(key, str)):
            raise InvalidGenerationRequest(label, path, "property names must be strings")
        _schema_json(item, label, _schema_path(path, key), stack, depth + 1)
    stack.remove(id(value))


def validate_json_schema(value, label="Response"):
    """Validate the platform's bounded subset, including acyclic local references."""
    if not isinstance(value, dict):
        raise InvalidGenerationRequest(label, "#", "root must be a JSON Schema object")
    _schema_json(value, label)
    try:
        size = len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())
    except (ValueError, TypeError, OverflowError):
        raise InvalidGenerationRequest(label, "#", "must be serializable JSON") from None
    if size > 65536:
        raise InvalidGenerationRequest(label, "#", "exceeds 64 KB")
    nodes = set()
    count = 0

    def children(node, path):
        for key in ("properties", "$defs"):
            for name, child in node.get(key, {}).items():
                yield child, _schema_path(_schema_path(path, key), name)
        for key in ("items", "additionalProperties"):
            if isinstance(node.get(key), dict):
                yield node[key], _schema_path(path, key)
        for index, child in enumerate(node.get("anyOf", [])):
            yield child, f"{path}/anyOf/{index}"

    def walk(node, path, depth):
        nonlocal count
        def fail(key, reason):
            raise InvalidGenerationRequest(label, _schema_path(path, key) if key else path, reason)
        if not isinstance(node, dict):
            fail("", "must be a schema object")
        if depth > 16:
            fail("", "exceeds depth 16")
        count += 1
        if count > 256:
            fail("", "exceeds 256 schema nodes")
        nodes.add(id(node))
        for key, item in node.items():
            if key not in SCHEMA_KEYS:
                fail(key, "unsupported keyword " + key)
            if key == "type":
                items = item if isinstance(item, list) else [item]
                if not items or any(not isinstance(t, str) or t not in SCHEMA_TYPES for t in items) or len(set(items)) != len(items):
                    fail(key, "invalid type")
            if key in {"properties", "$defs", "items"} and not isinstance(item, dict):
                fail(key, "must be an object")
            if key == "required" and (not isinstance(item, list) or any(not isinstance(t, str) for t in item) or len(set(item)) != len(item)):
                fail(key, "must be distinct property names")
            if key == "additionalProperties" and not isinstance(item, bool | dict):
                fail(key, "must be boolean or a schema")
            if key in {"anyOf", "enum"} and (not isinstance(item, list) or not 1 <= len(item) <= (16 if key == "anyOf" else 256)):
                fail(key, "exceeds branch or value limit")
            if key in {"title", "description", "$ref"} and not isinstance(item, str):
                fail(key, "must be a string")
            if key == "examples" and not isinstance(item, list):
                fail(key, "must be an array")
            if key in SCHEMA_BOUNDS and (isinstance(item, bool) or not isinstance(item, int | float) or (isinstance(item, float) and not math.isfinite(item)) or (key in {"minLength", "maxLength", "minItems", "maxItems"} and (not isinstance(item, int) or item < 0))):
                fail(key, "invalid bound")
        for child, child_path in children(node, path):
            walk(child, child_path, depth + 1)

    walk(value, "#", 0)
    expanded = 0

    def references(node, path, stack, depth):
        nonlocal expanded
        expanded += 1
        if id(node) in stack or depth > 32 or expanded > 4096:
            raise InvalidGenerationRequest(label, path, "recursive or excessive reference expansion")
        next_stack = stack | {id(node)}
        if "$ref" in node:
            ref, target = node["$ref"], value
            import re
            if not ref.startswith("#/") or re.search(r"~(?![01])", ref):
                raise InvalidGenerationRequest(label, path + "/$ref", "only local #/... references are allowed")
            for key in ref[2:].split("/"):
                key = key.replace("~1", "/").replace("~0", "~")
                if not isinstance(target, dict) or key not in target:
                    raise InvalidGenerationRequest(label, path + "/$ref", "reference does not resolve")
                target = target[key]
            if not isinstance(target, dict) or id(target) not in nodes:
                raise InvalidGenerationRequest(label, path + "/$ref", "reference must resolve to a schema")
            references(target, path + "/$ref", next_stack, depth + 1)
        for child, child_path in children(node, path):
            references(child, child_path, next_stack, depth + 1)

    references(value, "#", set(), 0)
    return value


def normalise_json_schema(value, label="Response"):
    """Strip only refused annotations; unexpressible constraints are rejected."""
    if not isinstance(value, dict):
        raise InvalidGenerationRequest(label, "#", "root must be a JSON Schema object")
    _schema_json(value, label)
    def convert(node, path, depth=0):
        if not isinstance(node, dict) or depth > 16:
            raise InvalidGenerationRequest(label, path, "must be a schema object within depth 16")
        result = {}
        for key, item in node.items():
            if key in {"$schema", "format"}:
                continue
            if key not in SCHEMA_KEYS:
                raise InvalidGenerationRequest(label, _schema_path(path, key), "unsupported keyword " + key)
            if key in {"properties", "$defs"} and isinstance(item, dict):
                result[key] = {name: convert(child, _schema_path(_schema_path(path, key), name), depth + 1) for name, child in item.items()}
            elif key in {"items", "additionalProperties"} and isinstance(item, dict):
                result[key] = convert(item, _schema_path(path, key), depth + 1)
            elif key == "anyOf" and isinstance(item, list):
                result[key] = [convert(child, f"{path}/anyOf/{index}", depth + 1) for index, child in enumerate(item)]
            else:
                result[key] = copy.deepcopy(item)
        return result
    return validate_json_schema(convert(value, "#"), label)


def generation_request(inputs, *, normalise=True):
    """One boundary for chat/completion messages, token limits and schemas."""
    if not isinstance(inputs, dict) or "prompt" in inputs or not isinstance(inputs.get("messages"), list) or not inputs["messages"]:
        raise InvalidGenerationRequest("Generation", "#/messages", "send nonempty messages instead of prompt")
    for index, message in enumerate(inputs["messages"]):
        if not isinstance(message, dict) or not isinstance(message.get("role"), str) or message.get("role") not in {"system", "user", "assistant", "tool"} or not (
                isinstance(message.get("content"), str) or (message.get("role") == "assistant" and isinstance(message.get("toolCalls"), list))):
            raise InvalidGenerationRequest("Generation", f"#/messages/{index}", "must be a message with a supported role and text or assistant tool calls")
    request = dict(inputs)
    maximum = inputs.get("maxTokens", 256) if normalise else inputs.get("maxTokens")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 64:
        raise InvalidGenerationRequest("Generation", "#/maxTokens", "must be an integer of 64 or more")
    request["maxTokens"] = maximum
    validate = normalise_json_schema if normalise else validate_json_schema
    if "jsonSchema" in inputs:
        request["jsonSchema"] = validate(inputs["jsonSchema"], "Response")
    if "tools" in inputs:
        if not isinstance(inputs["tools"], list):
            raise InvalidGenerationRequest("Generation", "#/tools", "must be a list")
        request["tools"] = []
        for tool in inputs["tools"]:
            if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
                raise InvalidGenerationRequest("Generation", "#/tools", "each tool needs a name")
            request["tools"].append({**tool, "parameters": validate(tool.get("parameters"), "Tool " + tool["name"])})
    return request


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PramaanClient:
    """Single server-side HTTP client. Mutating requests are never retried."""

    CAPABILITIES = frozenset({
        "apps.connection.start", "email.send", "llm.complete", "security.ip.lookup", "finance.exchange-rate.get",
        "geo.address.reverse-geocode", "notify.push.send", "sms.send",
        "document.resume.parse", "document.extract",
        "job.posting.analyze", "job.market.salary-distribution",
        "calendar.event.create", "calendar.event.update", "meetings.room.create",
        "identity.verification.create", "people.credentials.verify",
        "finance.transfer-quote.create", "finance.transfer.create", "finance.transfer.fund",
        "assessment.exam.create", "assessment.exam.get", "assessment.exam.publish",
        "assessment.exams.list", "assessment.question.create", "assessment.questions.list",
        "assessment.invitation.create", "assessment.invitations.list",
        "assessment.invitation.get", "assessment.invitation.revoke",
        "assessment.session.get", "assessment.result.get", "assessment.integrity-report.get",
    })
    ACTIONS = frozenset({
        "apps.connection.start", "email.send", "notify.push.send", "sms.send",
        "calendar.event.create", "calendar.event.update", "meetings.room.create",
        "identity.verification.create", "people.credentials.verify",
        "finance.transfer-quote.create", "finance.transfer.create", "finance.transfer.fund",
        "assessment.exam.create", "assessment.exam.publish", "assessment.question.create",
        "assessment.invitation.create", "assessment.invitation.revoke",
    })
    OUTCOMES = frozenset({
        "resume.screen", "candidate.match", "kyc.verify",
        "candidate.employment.verify", "candidate.background.check", "candidate.dev.profile",
    })

    def __init__(self, *, api_key=None, base_url=None, transport=None, sleep=time.sleep):
        self._api_key = api_key if api_key is not None else os.environ.get("PRAMAAN_API_KEY", "")
        self._base_url = (base_url or os.environ.get("PRAMAAN_BASE_URL") or "https://api.pramaan.dev").rstrip("/")
        parsed = urlparse(self._base_url)
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "fake-pramaan"}
        ):
            raise PramaanError("invalid_configuration")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise PramaanError("invalid_configuration")
        self._transport = transport or (self._fake if os.environ.get("PRAMAAN_FAKE") == "1" else self._http)
        self._sleep = sleep

    @property
    def configured(self):
        return self._transport == self._fake or bool(self._api_key.strip())

    def require_configured(self):
        if not self.configured:
            raise MissingPramaanKey()

    @staticmethod
    def _fake(method, url, headers, body):
        # Explicit local fixture mode has no network transport or outside effects.
        path = urlparse(url).path
        if method == "POST" and path == "/v1/capabilities/llm.complete":
            return 200, {"text": "Local fixture draft text.", "finishReason": "stop"}
        if method == "POST" and path == "/v1/files":
            if not isinstance(body, bytes) or not body:
                return 400, {"error": {"code": "invalid_request"}}
            return 201, {"fileId": "file_01ARZ3NDEKTSV4RRFFQ69G5FAV"}
        if method == "POST" and path == "/v1/capabilities/apps.connection.start":
            return 200, {"connectUrl": "https://connect.example/fixture"}
        if method == "POST" and path == "/v1/capabilities/email.send":
            if (not all(body.get(key) for key in ("from", "to", "subject"))
                    or not (body.get("html") or body.get("text"))
                    or not isinstance(body.get("tags", {}), dict)
                    or any(set(item) != {"fileId", "name"} for item in body.get("attachments", []))):
                return 400, {"error": {"code": "invalid_request"}}
            return 200, {"ref": "fixture-email-ref", "status": "accepted"}
        if method == "POST" and path == "/v1/capabilities/notify.push.send":
            return 200, {"ref": "fixture-push-ref", "status": "accepted"}
        if method == "POST" and path == "/v1/capabilities/sms.send":
            return 200, {"ref": "fixture-sms-ref", "status": "accepted"}
        if method == "POST" and path == "/v1/capabilities/security.ip.lookup":
            return 200, {"country": "Local fixture country", "city": "Local fixture city"}
        if method == "POST" and path == "/v1/capabilities/geo.address.reverse-geocode":
            return 200, {"results": [{"formatted": "Local fixture address", "lat": 0.0, "lng": 0.0}]}
        if method == "POST" and path == "/v1/capabilities/document.resume.parse":
            return 200, {"candidate": {"fullName": "Local fixture candidate", "email": "candidate@example.com",
                         "skills": ["Fixture skill"], "workExperience": [], "education": []}}
        if method == "POST" and path == "/v1/capabilities/document.extract":
            return 200, {"data": {"amount": 100}, "truncated": False}
        if method == "POST" and path == "/v1/capabilities/job.posting.analyze":
            return 200, {"title": "Fixture role", "skills": ["Fixture skill"], "warnings": []}
        if method == "POST" and path == "/v1/capabilities/job.market.salary-distribution":
            return 200, {"currency": "FIX", "thresholds": []}
        if method == "POST" and path.startswith("/v1/capabilities/calendar.event."):
            return 200, {"ref": "fixture-event-ref", "status": "accepted"}
        if method == "POST" and path == "/v1/capabilities/meetings.room.create":
            return 200, {"ref": "fixture-room-ref", "joinUrl": "https://join.example/fixture"}
        if method == "POST" and path == "/v1/capabilities/identity.verification.create":
            return 200, {"ref": "fixture-identity-ref", "url": "https://verify.example/fixture"}
        if method == "POST" and path == "/v1/capabilities/people.employment.verify":
            return 200, {"ref": "fixture-employment-ref", "status": "running"}
        if method == "POST" and path == "/v1/capabilities/people.credentials.verify":
            return 200, {"ref": "fixture-credential-ref", "status": "running"}
        if method == "POST" and path == "/v1/capabilities/finance.exchange-rate.get":
            return 200, {"from": body["from"], "to": body["to"], "rate": 1.0, "inverseRate": 1.0}
        if method == "POST" and path == "/v1/capabilities/finance.transfer-quote.create":
            return 200, {"quoteId": "fixture-quote"}
        if method == "POST" and path == "/v1/capabilities/finance.transfer.create":
            return 200, {"ref": "fixture-transfer-ref", "status": "pending"}
        if method == "POST" and path == "/v1/capabilities/finance.transfer.fund":
            return 200, {"ref": "fixture-transfer-ref", "status": "funding"}
        if method == "POST" and path == "/v1/capabilities/assessment.exam.create":
            return 200, {"ref": "fixture-exam-ref", "title": (body or {}).get("title", "Fixture exam"), "status": "draft"}
        if method == "POST" and path == "/v1/capabilities/assessment.exam.get":
            return 200, {"title": "Fixture exam", "status": "draft"}
        if method == "POST" and path == "/v1/capabilities/assessment.exam.publish":
            return 200, {"ref": "fixture-exam-ref", "status": "published"}
        if method == "POST" and path == "/v1/capabilities/assessment.exams.list":
            return 200, {"results": []}
        if method == "POST" and path == "/v1/capabilities/assessment.question.create":
            return 200, {"created": True}
        if method == "POST" and path == "/v1/capabilities/assessment.questions.list":
            return 200, {"results": []}
        if method == "POST" and path == "/v1/capabilities/assessment.invitation.create":
            return 200, {"ref": "fixture-invitation-ref", "link": "https://assess.example/fixture",
                         "expiresAt": "1970-01-01T00:00:00Z", "created": True}
        if method == "POST" and path == "/v1/capabilities/assessment.invitations.list":
            return 200, {"results": []}
        if method == "POST" and path == "/v1/capabilities/assessment.invitation.get":
            return 200, {"status": "sent"}
        if method == "POST" and path == "/v1/capabilities/assessment.invitation.revoke":
            return 200, {"ref": "fixture-invitation-ref", "status": "revoked"}
        if method == "POST" and path == "/v1/capabilities/assessment.session.get":
            return 200, {"status": "not_started"}
        if method == "POST" and path == "/v1/capabilities/assessment.result.get":
            return 200, {"gradingStatus": "not_ready", "reportStatus": "not_ready", "finalizationStatus": "pending"}
        if method == "POST" and path == "/v1/capabilities/assessment.integrity-report.get":
            return 200, {"verdict": "pending", "finalizedAt": None}
        if method == "POST" and path.startswith("/v1/outcomes/") and path.endswith("/estimate"):
            return 200, {"plan": "fixture-plan", "can_run": True, "steps": [{"capability": "llm.complete"}]}
        if method == "GET" and path.startswith("/v1/outcomes/"):
            return 200, {"available": True, "effect_class": "read_only", "requires_approval": False,
                         "steps": [{"capability": "llm.complete"}]}
        if method == "POST" and path == "/v1/outcomes/candidate.employment.verify":
            return 200, {"status": "done", "result": {"consentRef": (body or {}).get("input", {}).get("consentRef", ""),
                         "claims": []}}
        if method == "POST" and path == "/v1/outcomes/candidate.background.check":
            return 200, {"status": "done", "result": {"consentRef": (body or {}).get("input", {}).get("consentRef", ""),
                         "caution": "No records found is not a clearance."}}
        if method == "POST" and path == "/v1/outcomes/candidate.dev.profile":
            return 200, {"status": "done", "result": {"consentRef": (body or {}).get("input", {}).get("consentRef", ""),
                         "accounts": []}}
        if method == "POST" and path == "/v1/outcomes/candidate.match":
            return 200, {"status": "done", "result": {"candidates": []}}
        if method == "POST" and path.startswith("/v1/outcomes/"):
            return 200, {"status": "done", "result": {"criteria": [{"text": "Fixture requirement", "status": "not_checked"}]}}
        return 503, {"error": {"code": "upstream_unavailable", "retryable": False}}

    def _http(self, method, url, headers, body):
        request = Request(url, data=body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None),
                          headers=headers, method=method)
        try:
            with build_opener(NoRedirects()).open(request, timeout=30) as response:
                raw = response.read(16_000_001)
                if len(raw) > 16_000_000:
                    raise PramaanError("invalid_response")
                return response.status, json.loads(raw)
        except HTTPError as error:
            # Read only bounded, recognized error codes; never surface the upstream body.
            try:
                payload = json.loads(error.read(16_001))
                code = payload.get("error") if isinstance(payload, dict) else None
                message = code.get("message", "") if isinstance(code, dict) else (payload.get("message", "") if isinstance(payload, dict) else "")
                if isinstance(code, dict):
                    code = code.get("code")
                if not code and isinstance(payload, dict):
                    code = payload.get("code")
                if (error.code == 400 and code == "invalid_request"
                        and urlparse(url).path == "/v1/capabilities/assessment.exam.create"
                        and message == "Set your organisation's name first (PUT /v1/organization)."):
                    return 400, {"error": {"code": "organization_name_required"}}
                if error.code == 400 and code == "invalid_request" and isinstance(message, str) and "maxtokens" in message.lower():
                    return 400, {"error": {"code": "invalid_request", "message": "maxTokens"}}
            except (ValueError, OSError):
                code = None
            return error.code, {"error": code if isinstance(code, str) and code in UNAVAILABLE_CODES else None}
        except (URLError, OSError, ValueError):
            raise PramaanError("unavailable", uncertain=method == "POST") from None

    def _request(self, method, path, body=None, *, idempotency_key=None, approved_by=None, plan=None, outcome=False, capability=None, content_type=None):
        self.require_configured()
        headers = {"Authorization": "Bearer " + self._api_key, "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = content_type or "application/json"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if approved_by:
            headers["Pramaan-Approved-By"] = approved_by
        if plan:
            headers["Pramaan-Plan"] = plan
        try:
            status, result = self._transport(method, self._base_url + path, headers, body)
        except PramaanError:
            raise
        except Exception:
            raise PramaanError("unavailable", uncertain=method == "POST") from None
        if status >= 400:
            remote_code = result.get("error") if isinstance(result, dict) else None
            if isinstance(remote_code, dict):
                remote_code = remote_code.get("code")
            if not remote_code and isinstance(result, dict):
                remote_code = result.get("code")
            remote_error = result.get("error") if isinstance(result, dict) else None
            remote_message = remote_error.get("message", "") if isinstance(remote_error, dict) else (result.get("message", "") if isinstance(result, dict) else "")
            if status == 400 and capability == "assessment.exam.create" and remote_code == "organization_name_required":
                raise OrganizationNameRequired()
            if status == 400 and capability in {"llm.chat", "llm.complete"} and remote_code == "invalid_request" and isinstance(remote_message, str) and "maxtokens" in remote_message.lower():
                raise GenerationConfigurationError()
            if capability and (capability.startswith(NOT_AVAILABLE_PREFIXES)) and (status == 501 or (isinstance(remote_code, str) and remote_code in UNAVAILABLE_CODES)):
                raise PramaanNotAvailable(capability)
            code = "request_rejected"
            uncertain = method == "POST" and status >= 500
            if outcome:
                if isinstance(remote_code, str) and remote_code == "upstream_unavailable":
                    # The live API reports a not-yet-available feature this way.
                    code, uncertain = "upstream_unavailable", False
                else:
                    code = {403: "approval_required", 409: "plan_changed", 429: "try_later"}.get(status, code)
            raise PramaanError(code, uncertain=uncertain)
        if status not in {200, 201, 202} or not isinstance(result, dict):
            raise PramaanError("invalid_response", uncertain=method == "POST")
        return status, result

    def upload_file(self, data: bytes, *, kind: str, content_type: str) -> str:
        """Upload private bytes through the same authenticated boundary."""
        if not isinstance(data, bytes) or not data or len(data) > 6_000_000:
            raise PramaanError("invalid_request")
        if kind not in {"document", "image", "data"} or not content_type or "\n" in content_type or "\r" in content_type:
            raise PramaanError("invalid_request")
        upload_key = "file:" + hashlib.sha256(kind.encode() + b"\0" + content_type.encode() + b"\0" + data).hexdigest()
        _, result = self._request("POST", "/v1/files?kind=" + quote(kind, safe=""), data,
                                  content_type=content_type, idempotency_key=upload_key)
        file_id = result.get("fileId")
        if not isinstance(file_id, str) or not file_id.startswith("file_"):
            raise PramaanError("invalid_response")
        return file_id

    def run(self, capability, inputs, *, idempotency_key=None, approved_by=None):
        self.require_configured()
        if capability not in self.CAPABILITIES:
            raise PramaanError("unsupported_capability")
        if capability in self.ACTIONS and not idempotency_key:
            raise PramaanError("missing_idempotency_key")
        if capability in {"llm.chat", "llm.complete"}:
            inputs = generation_request(inputs)
        status, result = self._request("POST", "/v1/capabilities/" + quote(capability, safe=""), inputs,
                                       idempotency_key=idempotency_key, approved_by=approved_by, capability=capability)
        if status == 202:
            if not isinstance(result.get("job_id"), str) or result.get("status") not in {"running", "done", "failed", "cancelled"}:
                raise PramaanError("invalid_response", uncertain=capability in self.ACTIONS)
        return generation_result(capability, inputs, result)

    def job(self, job_id):
        _, result = self._request("GET", "/v1/jobs/" + quote(job_id, safe=""))
        return result

    def call(self, capability, inputs, *, idempotency_key=None, approved_by=None, max_polls=60):
        result = self.run(capability, inputs, idempotency_key=idempotency_key, approved_by=approved_by)
        if "job_id" not in result:
            return result
        job_id = result["job_id"]
        for _ in range(max_polls):
            state = result.get("status")
            if state == "done":
                completed = result.get("result")
                if not isinstance(completed, dict):
                    raise PramaanError("invalid_response", uncertain=capability in self.ACTIONS)
                return generation_result(capability, inputs, completed)
            if state in {"failed", "cancelled"}:
                raise PramaanError("job_failed", uncertain=capability in self.ACTIONS)
            if state != "running":
                raise PramaanError("invalid_response")
            self._sleep(2)
            result = self.job(job_id)
        raise PramaanError("job_pending", uncertain=capability in self.ACTIONS)

    def outcomes_list(self):
        """List the platform's outcome descriptions without running anything."""
        _, result = self._request("GET", "/v1/outcomes", outcome=True)
        return result

    def outcome_get(self, outcome_id):
        _, result = self._request("GET", "/v1/outcomes/" + quote(outcome_id, safe=""), outcome=True)
        return result

    def outcome_estimate(self, outcome_id, body):
        """Return steps, worst-case cost and plan for the exact run body; no charge.

        can_run false with reason connection_required names the account slot the
        person must connect; that is a stable, safe answer to show.
        """
        _, result = self._request("POST", "/v1/outcomes/" + quote(outcome_id, safe="") + "/estimate",
                                  body, outcome=True)
        if result.get("can_run") is False and result.get("reason") == "connection_required":
            raise ConnectionRequired(result.get("slot", ""))
        return result

    def outcome_run(self, outcome_id, body, *, plan=None, idempotency_key=None,
                    approved_by=None, max_polls=60):
        """Run an explicitly reviewed body once, preserving the complete run report.

        Pass the estimate's plan only after human approval. A stale or changed plan
        requires another estimate and approval; neither requests nor failed runs
        are retried here. No account, end-user or max-price headers are accepted.
        """
        if outcome_id not in self.OUTCOMES:
            raise PramaanError("unsupported_capability")
        description = self.outcome_get(outcome_id)
        if description.get("available") is False:
            raise PramaanError("upstream_unavailable")
        if description.get("available") is not True:
            raise PramaanError("invalid_response")
        if description.get("requires_approval") and not plan:
            raise PramaanError("approval_required")
        if description.get("effect_class") != "read_only" and not idempotency_key:
            raise PramaanError("missing_idempotency_key")
        status, result = self._request("POST", "/v1/outcomes/" + quote(outcome_id, safe=""), body,
                                       plan=plan, idempotency_key=idempotency_key,
                                       approved_by=approved_by, outcome=True)
        if status == 202:
            job_id = result.get("job_id")
            if not isinstance(job_id, str) or not job_id:
                raise PramaanError("invalid_response", uncertain=True)
            for poll in range(max_polls + 1):
                state = result.get("status")
                if state in {"done", "failed", "cancelled"}:
                    report = result.get("result")
                    if not isinstance(report, dict):
                        raise PramaanError("invalid_response", uncertain=True)
                    return self._outcome_report(report)
                if state not in {"running", "queued"}:
                    raise PramaanError("invalid_response", uncertain=True)
                if poll == max_polls:
                    break
                self._sleep(2)
                try:
                    result = self.job(job_id)
                except PramaanError:
                    # The accepted run may still be acting; never start another.
                    raise PramaanError("job_pending", uncertain=True, job_id=job_id) from None
            raise PramaanError("job_pending", uncertain=True, job_id=job_id)
        return self._outcome_report(result)

    @staticmethod
    def _outcome_report(report):
        if report.get("status") not in {"done", "failed", "declined"}:
            raise PramaanError("invalid_response", uncertain=True)
        # Failed reports may contain completed or unknown effects. Return them
        # intact for review; they must not be mistaken for fallback permission.
        return report

    # Feature contracts; each stays false until its own integration and fake
    # checks are in place, and until the owner reports it live.
    FEATURES: ClassVar[dict[str, bool]] = {
        "transactional_email": True,
        "writing_help": True,
        "ip_insights": False,
        "check_in_addresses": False,
        "push_notifications": False,
        "sms_notices": False,
        "document_intake": False,
        "recruiting_insights": False,
        "scheduling": False,
        "identity_checks": False,
        "payroll_payouts": False,
        "assessments": False,
    }

    def availability(self) -> tuple[FeatureAvailability, ...]:
        return tuple(
            FeatureAvailability(feature, enabled, "" if enabled else str(CapabilityUnavailable(feature)))
            for feature, enabled in self.FEATURES.items()
        )
