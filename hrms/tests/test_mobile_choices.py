"""Self-service lookups do not grant access to another employee or company."""
import frappe
from frappe.tests import IntegrationTestCase

from erpnext.setup.doctype.employee.test_employee import make_employee
from hrms.api import get_holidays_for_employee, get_shift_request_approvers, search_mobile_link


class TestMobileChoices(IntegrationTestCase):
	def setUp(self):
		self.user = "qa.choices@example.test"
		self.employee = make_employee(self.user, company="_Test Company")
		self.other = make_employee("qa.other.choices@example.test", company="_Test Company")
		frappe.set_user(self.user)
		self.addCleanup(frappe.set_user, "Administrator")

	def test_own_approvers_and_holidays_do_not_need_master_read_access(self):
		self.assertIsInstance(get_shift_request_approvers(self.employee), list)
		self.assertIsInstance(get_holidays_for_employee(self.employee), list)

	def test_another_employee_holidays_remain_private(self):
		with self.assertRaises(frappe.PermissionError):
			get_holidays_for_employee(self.other)

	def test_account_choices_remain_inside_current_company(self):
		self.assertEqual(search_mobile_link("Account", filters={"company": "Other Company"}), [])
		for choice in search_mobile_link("Account"):
			self.assertEqual(frappe.db.get_value("Account", choice["value"], "company"), "_Test Company")
		self.assertEqual(search_mobile_link("Account", filters={"account_type": "Bank"}), [])
