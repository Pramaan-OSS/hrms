"""Explicit, consent-noted identity, employment, background and profile checks.

Every candidate check here is one explicit HR action; the candidate's consent
is required as a reference the HR user holds, the lawful basis is recorded,
and the platform outcome returns findings for a human reviewer only.
"""

import json

import frappe
from frappe import _

from hrms.integrations.pramaan_common import get_client, respond


def _consent_ref(consent_ref):
	consent_ref = (consent_ref or "").strip()
	if not consent_ref:
		frappe.throw(_("Enter the candidate's consent reference first."))
	return consent_ref[:200]


def _basis(basis_ground):
	return {"ground": basis_ground or "consent"}


def _run_outcome(client, outcome_id, body, *, idempotency_key, requires_plan):
	estimate = client.outcome_estimate(outcome_id, body)
	plan = estimate.get("plan") if requires_plan else None
	return estimate, client.outcome_run(
		outcome_id, body, plan=plan, idempotency_key=idempotency_key
	)


def _note_consent(doc, text):
	doc.add_comment("Comment", text)


@frappe.whitelist()
@respond
def start_identity_verification(employee_onboarding: str, end_user_id: str) -> dict:
	"""Start a hosted identity check; the private link goes to the person."""
	doc = frappe.get_doc("Employee Onboarding", employee_onboarding)
	doc.check_permission("write")
	if not end_user_id or not str(end_user_id).strip():
		frappe.throw(_("Enter the person's verification reference first."))

	result = get_client().call(
		"identity.verification.create",
		{"endUserId": str(end_user_id).strip()},
		idempotency_key=f"identity:{doc.doctype}:{doc.name}",
	)
	doc.add_comment("Comment", _("Identity verification started for this onboarding."))
	return {"url": result.get("url") or "", "ref": result.get("ref") or ""}


@frappe.whitelist()
@respond
def verify_employment(
	job_applicant: str, linkedin_url: str, consent_ref: str, claims: list | str | None = None, basis_ground: str = "consent"
) -> dict:
	"""Compare stated employers and dates with a public profile, for a reviewer."""
	doc = frappe.get_doc("Job Applicant", job_applicant)
	doc.check_permission("read")
	if not (linkedin_url or "").startswith(("http://", "https://")):
		frappe.throw(_("Enter the candidate's public profile link."))

	if isinstance(claims, str):
		try:
			claims = json.loads(claims)
		except ValueError:
			frappe.throw(_("Employer claims must be a JSON list."))
	if not isinstance(claims, list) or not (1 <= len(claims) <= 10):
		frappe.throw(_("State between 1 and 10 employer claims."))

	body = {
		"input": {
			"consentRef": _consent_ref(consent_ref),
			"linkedinUrl": linkedin_url,
			"claims": [
				{"employer": str(claim.get("employer", ""))[:200], **{
					key: claim[key]
					for key in ("from", "to")
					if claim.get(key)
				}}
				for claim in claims
			],
		},
		"options": {},
		"basis": _basis(basis_ground),
	}
	client = get_client()
	estimate, report = _run_outcome(
		client,
		"candidate.employment.verify",
		body,
		idempotency_key=f"employment:{doc.name}:{_consent_ref(consent_ref)}",
		requires_plan=True,
	)
	_note_consent(
		doc,
		_("Employment comparison started; consent reference {0} recorded.").format(
			body["input"]["consentRef"]
		),
	)
	return {"report": report, "estimate": estimate}


@frappe.whitelist()
@respond
def start_background_check(
	job_applicant: str,
	consent_ref: str,
	full_name: str,
	father_name: str = "",
	date_of_birth: str = "",
	address: str = "",
	clearance_number: str = "",
	basis_ground: str = "consent",
) -> dict:
	"""Court-record counts and an optional certificate lookup, for a reviewer.

	The result never decides suitability; a missing record is not a clearance.
	"""
	doc = frappe.get_doc("Job Applicant", job_applicant)
	doc.check_permission("write")
	if not full_name or not str(full_name).strip():
		frappe.throw(_("Enter the candidate's full name as their records hold it."))

	body = {
		"input": {
			"consentRef": _consent_ref(consent_ref),
			"fullName": str(full_name).strip()[:1024],
		},
		"options": {"searchMode": "standard"},
		"basis": _basis(basis_ground),
	}
	for key, value in (
		("fatherName", father_name),
		("dateOfBirth", date_of_birth),
		("address", address),
	):
		if value and str(value).strip():
			body["input"][key] = str(value).strip()[:1024]
	if clearance_number and str(clearance_number).strip():
		body["input"]["clearanceNumber"] = str(clearance_number).strip()

	client = get_client()
	estimate, report = _run_outcome(
		client,
		"candidate.background.check",
		body,
		idempotency_key=f"background:{doc.name}:{_consent_ref(consent_ref)}",
		requires_plan=True,
	)
	_note_consent(
		doc,
		_("Background check started; consent reference {0} recorded.").format(
			body["input"]["consentRef"]
		),
	)
	return {"report": report, "estimate": estimate}


@frappe.whitelist()
@respond
def fetch_dev_profile(
	job_applicant: str, consent_ref: str, linkedin_url: str = "", email: str = "", basis_ground: str = "consent"
) -> dict:
	"""Public developer accounts and activity facts, for a human reviewer."""
	doc = frappe.get_doc("Job Applicant", job_applicant)
	doc.check_permission("read")

	inputs = {"consentRef": _consent_ref(consent_ref)}
	if linkedin_url and str(linkedin_url).startswith(("http://", "https://")):
		inputs["linkedinUrl"] = linkedin_url
	elif email and str(email).strip():
		inputs["email"] = str(email).strip()
	else:
		frappe.throw(_("Enter the candidate's public profile link or their email."))

	body = {"input": inputs, "options": {}, "basis": _basis(basis_ground)}
	client = get_client()
	estimate, report = _run_outcome(
		client,
		"candidate.dev.profile",
		body,
		idempotency_key=f"dev-profile:{doc.name}:{_consent_ref(consent_ref)}",
		requires_plan=False,
	)
	_note_consent(
		doc,
		_("Developer profile lookup started; consent reference {0} recorded.").format(
			body["input"]["consentRef"]
		),
	)
	return {"report": report, "estimate": estimate}


@frappe.whitelist()
@respond
def verify_credential(credential_ref: str, lookup: dict | str) -> dict:
	"""Look up one stated professional or vocational credential."""
	frappe.only_for(("System Manager", "HR Manager", "HR User"), True)
	if isinstance(lookup, str):
		lookup = frappe.parse_json(lookup)
	if not isinstance(lookup, dict):
		frappe.throw(_("Credential lookup must be a JSON object."))
	if not credential_ref:
		frappe.throw(_("Save the credential first."))

	result = get_client().call(
		"people.credentials.verify",
		dict(lookup or {}),
		idempotency_key=f"credential:{credential_ref}",
		approved_by=frappe.session.user,
	)
	return {"result": result}
