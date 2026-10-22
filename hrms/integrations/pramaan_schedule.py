"""Interview scheduling with a calendar event and a meeting-room link.

Optional features: both need connected handles in HR Settings and stay off
until they are configured.
"""

import frappe
from frappe import _

from hrms.integrations.pramaan_common import get_client, respond

SETTING_INBOX = "connected_calendar_inbox"
SETTING_MEETING_APP = "connected_meeting_app"


def _setting(name: str) -> str:
	return (frappe.db.get_single_value("HR Settings", name) or "").strip()


def _require_setting(name: str, label: str) -> str:
	value = _setting(name)
	if not value:
		frappe.throw(_(f"{label} is not set up yet. Set {name} in HR Settings to turn this on."))
	return value


@frappe.whitelist()
@respond
def schedule_interview(interview: str) -> dict:
	"""Create the round's calendar event and meeting-room link, then store both."""
	doc = frappe.get_doc("Interview", interview)
	doc.check_permission("write")
	if not doc.scheduled_on or not doc.from_time or not doc.to_time:
		frappe.throw(_("Set the round's date and times first."))

	inbox = _require_setting(SETTING_INBOX, "A connected calendar")
	meeting_app = _require_setting(SETTING_MEETING_APP, "A connected meeting app")

	client = get_client()
	start = frappe.utils.get_datetime(f"{doc.scheduled_on} {doc.from_time}")
	end = frappe.utils.get_datetime(f"{doc.scheduled_on} {doc.to_time}")
	title = _("Interview round {0}").format(doc.name)

	room = client.call(
		"meetings.room.create",
		{
			"endUserRef": _setting("connected_calendar_inbox"),
			"app": meeting_app,
			"title": title,
			"start": start.isoformat(),
			"durationMinutes": max(5, int(frappe.utils.time_diff(end, start).total_seconds() // 60)),
		},
		idempotency_key=f"interview-room:{doc.name}",
	)
	event = client.call(
		"calendar.event.create",
		{
			"inbox": inbox,
			"title": title,
			"start": start.isoformat(),
			"end": end.isoformat(),
			"description": _("Interview round for {0}").format(getattr(doc, "job_applicant", "") or doc.name),
			"metadata": {"interview": doc.name},
		},
		idempotency_key=f"interview-event:{doc.name}",
	)

	doc.db_set(
		{
			"meeting_room_link": room.get("joinUrl") or "",
			"calendar_event_ref": event.get("ref") or "",
		}
	)
	return {"join_url": room.get("joinUrl") or "", "event_ref": event.get("ref") or ""}


@frappe.whitelist()
@respond
def reschedule_interview(interview: str) -> dict:
	"""Move the stored calendar event when the round's times change."""
	doc = frappe.get_doc("Interview", interview)
	doc.check_permission("write")
	if not doc.calendar_event_ref:
		frappe.throw(_("This round has no connected event yet. Schedule it first."))

	inbox = _require_setting(SETTING_INBOX, "A connected calendar")
	start = frappe.utils.get_datetime(f"{doc.scheduled_on} {doc.from_time}")
	end = frappe.utils.get_datetime(f"{doc.scheduled_on} {doc.to_time}")

	client = get_client()
	client.call(
		"calendar.event.update",
		{
			"inbox": inbox,
			"ref": doc.calendar_event_ref,
			"start": start.isoformat(),
			"end": end.isoformat(),
		},
		idempotency_key=f"interview-event-update:{doc.name}:{doc.scheduled_on}:{doc.from_time}",
	)
	return {"event_ref": doc.calendar_event_ref}
