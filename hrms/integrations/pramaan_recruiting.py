"""Recruiting insights through the single client: all explicit reviewer actions."""

import base64

import frappe
from frappe import _

from hrms.integrations.pramaan_common import get_client, respond


def _resume_file_bytes(applicant_doc) -> tuple[bytes, str]:
	"""Read the local resume attachment with its permission checks."""
	attachment = applicant_doc.resume_attachment
	if not attachment:
		frappe.throw(_("No resume attachment on this applicant."))
	file = frappe.get_doc("File", {"file_url": attachment})
	file.check_permission("read")
	name = (file.file_name or "resume").rsplit(".", 1)
	extension = name[1].lower() if len(name) == 2 else "pdf"
	return file.get_content(), extension


@frappe.whitelist()
@respond
def parse_resume(applicant: str) -> dict:
	"""Read one applicant's uploaded CV into structured data for review."""
	doc = frappe.get_doc("Job Applicant", applicant)
	doc.check_permission("read")

	content, extension = _resume_file_bytes(doc)
	result = get_client().call(
		"document.resume.parse",
		{"content": base64.b64encode(content).decode(), "extension": extension},
	)
	return {"candidate": result.get("candidate") or {}}


@frappe.whitelist()
@respond
def screen_resume(applicant: str, criteria: list | str, basis_ground: str = "consent") -> dict:
	"""Quoted evidence per stated requirement from one resume, for a human reviewer."""
	if isinstance(criteria, str):
		criteria = frappe.parse_json(criteria)
	if not isinstance(criteria, list) or not (1 <= len(criteria) <= 10):
		frappe.throw(_("State between 1 and 10 requirements."))

	doc = frappe.get_doc("Job Applicant", applicant)
	doc.check_permission("read")

	content, extension = _resume_file_bytes(doc)
	body = {
		"input": {
			"content": base64.b64encode(content).decode(),
			"extension": extension,
			"criteria": [str(item)[:200] for item in criteria],
		},
		"options": {},
		"basis": {"ground": basis_ground or "consent"},
	}
	client = get_client()
	estimate = client.outcome_estimate("resume.screen", body)
	report = client.outcome_run("resume.screen", body, plan=estimate.get("plan"))
	return {"report": report, "estimate": estimate}


@frappe.whitelist()
@respond
def rank_applicants(opening: str, skills: list | str, basis_ground: str = "consent") -> dict:
	"""Rank an opening's applicants against its stated skills; a human decides."""
	if isinstance(skills, str):
		skills = frappe.parse_json(skills)
	if not isinstance(skills, list) or not (1 <= len(skills) <= 10):
		frappe.throw(_("State between 1 and 10 skill requirements."))

	frappe.only_for(("System Manager", "HR Manager", "HR User"), True)

	applicants = frappe.get_all(
		"Job Applicant",
		filters={"job_title": opening, "resume_link": ("is", "set")},
		fields=["name", "applicant_name", "email_id", "resume_link"],
		limit_page_length=10,
	)
	rows = []
	skipped = []
	for row in applicants:
		if not (row.resume_link or "").startswith(("http://", "https://")):
			skipped.append(row.name)
			continue
		rows.append(
			{
				"id": row.name,
				"fullName": row.applicant_name or row.name,
				"email": row.email_id or "",
				"resumeUrl": row.resume_link,
			}
		)
	if not rows:
		frappe.throw(_("Applicants need a public resume link to be compared."))

	body = {
		"input": {
			"skills": [str(item)[:100] for item in skills],
			"candidates": rows,
		},
		"options": {},
		"basis": {"ground": basis_ground or "consent"},
	}
	client = get_client()
	estimate = client.outcome_estimate("candidate.match", body)
	report = client.outcome_run("candidate.match", body, plan=estimate.get("plan"))
	return {"report": report, "estimate": estimate, "skipped": skipped}


@frappe.whitelist()
@respond
def analyze_description(opening: str) -> dict:
	"""Check a drafted description: title, skills, pay range and warning signs."""
	doc = frappe.get_doc("Job Opening", opening)
	doc.check_permission("read")
	if not doc.description:
		frappe.throw(_("Write the description first."))

	text = frappe.utils.strip_html(doc.description)
	result = get_client().call("job.posting.analyze", {"text": text[:20000]})
	return {"analysis": result}


@frappe.whitelist()
@respond
def suggest_salary_range(opening: str) -> dict:
	"""Advertised pay distribution for one opening's role and location."""
	doc = frappe.get_doc("Job Opening", opening)
	doc.check_permission("read")

	location = (doc.location or "").strip()
	if not location:
		frappe.throw(_("Set the job location before requesting a salary range."))

	country = None
	if doc.company:
		country = frappe.db.get_value("Company", doc.company, "country")
	if not country:
		frappe.throw(_("Set the company's country first."))

	country_code = (frappe.db.get_value("Country", country, "code") or "").upper()
	if country_code not in {"GB", "US", "AT", "AU", "BE", "BR", "CA", "CH", "DE", "ES", "FR", "IN", "IT", "MX", "NL", "NZ", "PL", "SG", "ZA"}:
		frappe.throw(_("Salary suggestions are not available for this country yet."))
	result = get_client().call(
		"job.market.salary-distribution",
		{
			"country": country_code,
			"keywords": doc.designation or doc.job_title or "",
			"locationArea": [location],
		},
	)
	return {"distribution": result}
