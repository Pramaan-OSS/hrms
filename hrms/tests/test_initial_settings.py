"""Installed defaults preserve configured notification templates and local choices."""
import frappe
from frappe.tests import IntegrationTestCase

from hrms.setup import restore_notification_defaults, set_single_defaults


class TestInitialSettings(IntegrationTestCase):
	def test_default_values_preserve_notification_links(self):
		frappe.db.set_single_value("HR Settings", "leave_approval_notification_template", "Leave Approval Notification")
		set_single_defaults()
		self.assertEqual(frappe.db.get_single_value("HR Settings", "leave_approval_notification_template"), "Leave Approval Notification")

	def test_disabled_notification_setting_is_preserved(self):
		frappe.db.set_single_value("HR Settings", "send_leave_notification", 0)
		set_single_defaults()
		self.assertFalse(frappe.db.get_single_value("HR Settings", "send_leave_notification"))

	def test_migration_restores_missing_template_links(self):
		frappe.db.set_single_value("HR Settings", "leave_status_notification_template", "")
		restore_notification_defaults()
		self.assertEqual(frappe.db.get_single_value("HR Settings", "leave_status_notification_template"), "Leave Status Notification")
