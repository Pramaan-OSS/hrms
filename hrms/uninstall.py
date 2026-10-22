import click

from hrms.setup import before_uninstall as remove_custom_fields


def before_uninstall():
	try:
		print("Removing customizations created by the HRMS app...")
		remove_custom_fields()

	except Exception as e:
		click.secho(
			"Removing Customizations for HRMS failed due to an error."
			" Check the local error log and try again.",
			fg="bright_red",
		)
		raise e

	click.secho("HRMS app customizations have been removed successfully...", fg="green")
