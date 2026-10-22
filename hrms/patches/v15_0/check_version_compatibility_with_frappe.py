import click

import frappe


def execute():
	frappe_v = frappe.get_attr("frappe" + ".__version__")
	hrms_v = frappe.get_attr("hrms" + ".__version__")

	if frappe_v.startswith("14") and hrms_v.startswith("15"):
		message = "This database needs a matching framework and base-app version before it can be upgraded."

		click.secho(message, fg="red")

		frappe.throw(message)  # nosemgrep
