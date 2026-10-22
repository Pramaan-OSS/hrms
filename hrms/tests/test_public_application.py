"""The guest label endpoint never reveals hidden or closed hiring records."""
import frappe
from frappe.tests import IntegrationTestCase

from hrms.hr.web_form.job_application.job_application import get_opening_title


class TestPublicApplication(IntegrationTestCase):
	def setUp(self):
		designation = "QA Public Designation"
		if not frappe.db.exists("Designation", designation):
			frappe.get_doc({"doctype": "Designation", "designation_name": designation}).insert()
		self.opening = frappe.get_doc({"doctype": "Job Opening", "job_title": "QA Public " + frappe.generate_hash(),
			"company": "_Test Company", "designation": designation, "status": "Open", "publish": 0}).insert()

	def test_hidden_opening_has_no_public_label(self):
		self.assertEqual(get_opening_title(self.opening.name), {})

	def test_published_opening_label_is_available_to_guest(self):
		self.opening.db_set("publish", 1)
		frappe.set_user("Guest")
		try:
			self.assertEqual(get_opening_title(self.opening.name), {"job_title": self.opening.job_title})
		finally:
			frappe.set_user("Administrator")

	def test_closed_opening_has_no_public_label(self):
		self.opening.db_set({"publish": 1, "status": "Closed"})
		self.assertEqual(get_opening_title(self.opening.name), {})
