import frappe


def get_setup_stages(wizard_args=None):
	"""No hosted-setup personalization stages; local setup only."""
	return []
