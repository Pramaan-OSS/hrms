"""Optional writing help: drafts the person edits, never saved automatically."""

import frappe
from frappe import _

from hrms.integrations.pramaan_common import get_client, respond

SYSTEM_PROMPT = (
	"You are an assistant inside a human-resources product. Write clear, plain, "
	"professional text. Follow every instruction from the user. Reply with the "
	"requested text only."
)


def _complete(user_prompt: str, max_tokens: int = 1024) -> str:
	result = get_client().call(
		"llm.complete",
		{
			"messages": [
				{"role": "system", "content": SYSTEM_PROMPT},
				{"role": "user", "content": user_prompt},
			],
			"maxTokens": max_tokens,
		},
	)
	return (result.get("text") or "").strip()


@frappe.whitelist()
@respond
def draft_job_description(opening: str) -> dict:
	"""Draft a job description for one Job Opening; the user reviews and applies it."""
	doc = frappe.get_doc("Job Opening", opening)
	doc.check_permission("read")

	parts = [f"Role or title: {doc.job_title or opening}"]
	if doc.company:
		parts.append(f"Company: {doc.company}")
	if doc.department:
		parts.append(f"Department: {doc.department}")
	if doc.designation:
		parts.append(f"Designation: {doc.designation}")
	if doc.employment_type:
		parts.append(f"Employment type: {doc.employment_type}")
	if doc.location:
		parts.append(f"Location: {doc.location}")
	parts.append("Write a job description of about 150 words with a short overview, "
	             "responsibilities and what we look for. Use plain words.")

	return {"draft": _complete("\n".join(parts))}


@frappe.whitelist()
@respond
def draft_appraisal_summary(appraisal: str) -> dict:
	"""Draft a neutral performance summary from one Appraisal's own scores."""
	doc = frappe.get_doc("Appraisal", appraisal)
	doc.check_permission("read")

	goals = [
		f"- {goal.kra}: weight {goal.per_weightage or 0}%, score {goal.score_earned or 0}/{goal.score or 0}"
		for goal in (doc.goals or [])
	]
	parts = [
		f"Employee: {doc.employee_name}",
		f"Cycle: {doc.appraisal_cycle}",
		f"Final score: {doc.final_score or 0}",
	]
	if goals:
		parts.append("Goals:")
		parts.extend(goals)
	parts.append(
		"Write a short, factual performance summary (about 120 words) from only these "
		"facts. Name no strengths or weaknesses the facts do not show. No rankings, "
		"no recommendations about the person's future."
	)

	return {"draft": _complete("\n".join(parts))}


@frappe.whitelist()
@respond
def draft_offer_letter(offer: str) -> dict:
	"""Draft offer-letter wording from one Job Offer's own terms."""
	doc = frappe.get_doc("Job Offer", offer)
	doc.check_permission("read")

	parts = [
		f"Candidate: {doc.applicant_name}",
		f"Role: {doc.designation}",
		f"Company: {doc.company}",
		f"Offer date: {doc.offer_date}",
	]
	terms = [
		f"- {term.offer_term}: {term.value}"
		for term in (doc.offer_terms or [])
	]
	if terms:
		parts.append("Agreed terms:")
		parts.extend(terms)
	parts.append(
		"Draft the body of an offer letter (about 180 words) that states these terms "
		"clearly and warmly. Leave the greeting and signature lines generic."
	)

	return {"draft": _complete("\n".join(parts))}
