"""Local account sign-in is the only enabled sign-in method."""
import frappe


@frappe.whitelist(allow_guest=True)
def oauth_providers():
	"""Do not expose authorization links from saved external-provider settings."""
	return []
