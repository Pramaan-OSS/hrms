# Copyright (c) 2026, contributors and license holders. See license.txt
import json

import frappe
from frappe import _
from frappe.model.document import Document

from hrms.integrations.pramaan_common import get_client, respond


class Assessment(Document):
	def validate(self):
		if self.status == "Published" and self.has_value_changed("proctoring_profile"):
			frappe.throw(_("A published exam cannot change its proctoring."))

	@frappe.whitelist()
	@respond
	def create_on_platform(self):
		"""Create the draft exam once; list exams before retrying a lost answer."""
		if self.exam_ref:
			return {"ref": self.exam_ref}
		if not self.questions:
			frappe.throw(_("Add at least one question first."))

		client = get_client()
		result = client.call(
			"assessment.exam.create",
			{
				"title": (self.title or "")[:200],
				"description": (self.description or "Candidate assessment")[:10000] or "Candidate assessment",
				"durationMinutes": self.duration_minutes,
				"passScore": self.pass_score,
				"proctoring": {"enabled": True, "profile": self.proctoring_profile or "observe"},
				"identityRequired": False,
			},
			idempotency_key=f"assessment-create:{self.doctype}:{self.name}",
		)
		ref = result.get("ref") or ""
		if ref:
			self.db_set("exam_ref", ref)
			self.db_set("platform_status", result.get("status") or "draft")
		return {"ref": ref, "status": result.get("status")}

	@frappe.whitelist()
	@respond
	def push_pending_questions(self):
		"""Create questions that are not on the platform yet."""
		if not self.exam_ref:
			frappe.throw(_("Create the exam on the platform first."))
		client = get_client()
		created = 0
		for index, row in enumerate(self.questions):
			if row.pushed:
				continue
			try:
				content = json.loads(row.options) if row.type == "mcq" and row.options else {}
			except ValueError:
				frappe.throw(_("Question {0}: options must be valid JSON.").format(index + 1))
			if row.type == "mcq" and not (2 <= len(content.get("options", [])) <= 8):
				frappe.throw(_("Question {0}: give two to eight answer options.").format(index + 1))
			client.call(
				"assessment.question.create",
				{
					"ref": self.exam_ref,
					"text": row.question,
					"points": row.points or 1,
					"required": bool(row.required),
					"type": row.type,
					"content": content,
				},
				idempotency_key=f"assessment-question:{self.name}:{index}",
			)
			row.db_set("pushed", 1)
			created += 1
		self.db_set("last_synced_on", frappe.utils.now())
		return {"created": created}

	@frappe.whitelist()
	@respond
	def publish(self):
		"""Publish the exam; this freezes its question set."""
		if self.status == "Published":
			return {"status": self.status}
		if not self.exam_ref:
			frappe.throw(_("Create the exam on the platform first."))

		client = get_client()
		pending = [row.idx for row in self.questions if not row.pushed]
		if pending:
			frappe.throw(_("Push every question before publishing. Rows still pending: {0}").format(
				frappe.utils.comma_and(pending)
			))
		result = client.call(
			"assessment.exam.publish",
			{"ref": self.exam_ref},
			idempotency_key=f"assessment-publish:{self.doctype}:{self.name}",
		)
		self.db_set("status", "Published")
		self.db_set("platform_status", result.get("status") or "published")
		return {"status": "Published"}

	@frappe.whitelist()
	@respond
	def sync_from_platform(self):
		"""Read the exam's state and questions to keep the local record honest."""
		if not self.exam_ref:
			frappe.throw(_("Create the exam on the platform first."))
		client = get_client()
		exam = client.call("assessment.exam.get", {"ref": self.exam_ref})
		remote_questions = client.call("assessment.questions.list", {"ref": self.exam_ref}).get("results") or []
		self.db_set("platform_status", exam.get("status") or "")
		if exam.get("status") == "published" and self.status != "Published":
			self.db_set("status", "Published")
		self.db_set("last_synced_on", frappe.utils.now())
		return {"exam": exam, "question_count": len(remote_questions)}

	@frappe.whitelist()
	@respond
	def list_invitations(self):
		if not self.exam_ref:
			frappe.throw(_("Create the exam on the platform first."))
		result = get_client().call("assessment.invitations.list", {"ref": self.exam_ref})
		return {"invitations": result.get("results") or []}


@frappe.whitelist()
@respond
def send_assessment(applicant: str) -> dict:
	"""Create one invitation for the opening's exam and mail the candidate link.

	Always carries a retry key; after a lost answer the invitations list is
	read before any retry. No live invitation happens without the owner's go.
	"""
	doc = frappe.get_doc("Job Applicant", applicant)
	doc.check_permission("write")
	if not doc.email_id:
		frappe.throw(_("The applicant has no email address."))

	assessment_name = frappe.db.get_value("Assessment", {"job_opening": doc.job_title, "status": "Published"}, "name")
	if not assessment_name:
		frappe.throw(_("No published assessment is linked to this opening."))
	doc.db_set("assessment", assessment_name)

	client = get_client()
	exam_ref = frappe.db.get_value("Assessment", assessment_name, "exam_ref")

	existing = frappe.db.get_value("Job Applicant", applicant, "assessment_invitation_ref")
	if not existing:
		invitations = client.call(
			"assessment.invitations.list", {"ref": exam_ref}
		).get("results") or []
		existing = next(
			(row.get("ref") for row in invitations if (row.get("email") or "") == doc.email_id),
			None,
		)

	if existing:
		client.call("assessment.invitation.get", {"ref": existing})
		link = None
		doc.db_set("assessment_invitation_ref", existing)
	else:
		result = client.call(
			"assessment.invitation.create",
			{"ref": exam_ref, "email": doc.email_id},
			idempotency_key=f"assessment-invite:{doc.doctype}:{doc.name}",
		)
		link = result.get("link") or ""
		doc.db_set("assessment_invitation_ref", result.get("ref") or "")
		doc.db_set("assessment_link", link)

	if not doc.assessment_link and not link:
		frappe.throw(_("The invitation exists but holds no link. Withdraw it and send a fresh one."))
	link = doc.assessment_link or link
	doc.db_set("assessment_status", "Sent")

	from hrms.integrations.pramaan_mail import sendmail

	sendmail(
		recipients=[doc.email_id],
		subject=_("Your assessment for {0}").format(doc.job_title),
		message=_("<p>Here is the link to your assessment:</p><p><a href='{0}'>{0}</a></p>").format(link),
		reference_doctype=doc.doctype,
		reference_name=doc.name,
	)
	return {"invitation_ref": doc.assessment_invitation_ref, "link": link}


@frappe.whitelist()
@respond
def withdraw_invitation(applicant: str) -> dict:
	"""Withdraw an unused invitation after the user confirms."""
	doc = frappe.get_doc("Job Applicant", applicant)
	doc.check_permission("write")
	if not doc.assessment_invitation_ref:
		frappe.throw(_("No assessment invitation to withdraw."))

	result = get_client().call(
		"assessment.invitation.revoke",
		{"ref": doc.assessment_invitation_ref},
		idempotency_key=f"assessment-revoke:{doc.doctype}:{doc.name}",
	)
	doc.db_set("assessment_status", "Withdrawn")
	doc.db_set("assessment_invitation_ref", "")
	return {"result": result}


@frappe.whitelist()
@respond
def refresh_assessment_status(applicant: str) -> dict:
	"""Poll invitation, session, result and integrity state; not ready is normal."""
	doc = frappe.get_doc("Job Applicant", applicant)
	doc.check_permission("read")
	if not doc.assessment_invitation_ref:
		frappe.throw(_("No assessment invitation to check."))

	client = get_client()
	ref = doc.assessment_invitation_ref
	invitation = client.call("assessment.invitation.get", {"ref": ref})
	session = client.call("assessment.session.get", {"ref": ref})
	result = client.call("assessment.result.get", {"ref": ref})
	integrity = client.call("assessment.integrity-report.get", {"ref": ref})

	status = invitation.get("status") or doc.assessment_status
	doc.db_set("assessment_status", str(status).title())

	grading = result.get("gradingStatus") or ""
	if grading and grading != "not_ready":
		doc.db_set("assessment_score", result.get("score") if result.get("score") is not None else "")
		outcome = []
		if result.get("passed") is not None:
			outcome.append(_("Passed: {0}").format(frappe.utils.cint(result["passed"])))
		if result.get("trustScore") is not None:
			outcome.append(_("Trust score: {0}").format(result["trustScore"]))
		if integrity.get("verdict") or result.get("integrityVerdict"):
			outcome.append(_("Integrity: {0}").format(integrity.get("verdict") or result["integrityVerdict"]))
		doc.db_set("assessment_result", "; ".join(outcome))

	return {
		"invitation": invitation,
		"session": session,
		"result": result,
		"integrity": integrity,
	}


def poll_assessments():
	"""Refresh existing invitations in a bounded local background job."""
	from hrms.pramaan import PramaanClient

	if not PramaanClient().configured:
		return
	previous_user = frappe.session.user
	try:
		frappe.set_user("Administrator")
		for name in frappe.get_all("Job Applicant", filters={
			"assessment_invitation_ref": ["is", "set"],
			"assessment_status": ["not in", ["Completed", "Withdrawn", "Expired", "Revoked"]],
		}, pluck="name", limit_page_length=20):
			try:
				refresh_assessment_status(name)
			except Exception:
				frappe.log_error(title="Assessment refresh failed", message="Refresh the invitation from the applicant before trying again.")
	finally:
		frappe.set_user(previous_user)
