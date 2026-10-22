import click

from hrms.setup import after_install as setup


def after_install():
	try:
		print("Setting up HRMS...")
		setup()
		from hrms.overrides.branding import apply_branding

		apply_branding()

		click.secho("Thank you for installing HRMS!", fg="green")

	except Exception as e:
		click.secho(
			"Installation for the HRMS app failed due to an error."
			" Please try re-installing the app.",
			fg="bright_red",
		)
		raise e
