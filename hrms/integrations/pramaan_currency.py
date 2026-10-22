"""Local accounting rates first, with remote rates through the single client."""
import math
from datetime import date, datetime

import frappe
from frappe import _

from hrms.pramaan import PramaanClient, PramaanError


@frappe.whitelist()
def get_exchange_rate(from_currency: str, to_currency: str, transaction_date: str | date | datetime | None = None, args: str | dict | None = None) -> float:
	if not from_currency or not to_currency:
		frappe.throw(_("Choose both currencies first."))
	if from_currency == to_currency:
		return 1.0
	filters = {"from_currency": from_currency, "to_currency": to_currency}
	if transaction_date:
		filters["date"] = ["<=", transaction_date]
	if isinstance(args, str) and args in {"for_buying", "for_selling"}:
		filters[args] = 1
	stored = frappe.db.get_value("Currency Exchange", filters, "exchange_rate", order_by="date desc")
	if stored:
		return float(stored)
	try:
		result = PramaanClient().call("finance.exchange-rate.get", {"from": from_currency, "to": to_currency})
		rate = result.get("rate")
		if rate is None and result.get("inverseRate"):
			rate = 1 / float(result["inverseRate"])
		rate = float(rate)
		if not math.isfinite(rate) or rate <= 0:
			raise ValueError
	except (PramaanError, TypeError, ValueError, ZeroDivisionError):
		frappe.throw(_("The exchange rate is not available yet. Enter a local Currency Exchange rate and try again."))
	return rate
