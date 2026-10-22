"""Shared boundary for whitelisted Pramaan-backed actions.

Every endpoint returns a plain ``available`` flag with a short message, so the
interface never shows a provider name, a price or a provider id.
"""

from functools import wraps

from hrms.pramaan import (
    ConnectionRequired,
    OrganizationNameRequired,
    MissingPramaanKey,
    PramaanError,
    PramaanNotAvailable,
)

UNCERTAIN_MESSAGE = (
	"The action may already have completed. Check its status before trying again."
)
GENERIC_MESSAGE = "Pramaan could not complete this request. Please try again later."
NOT_AVAILABLE_MESSAGE = "This feature is not available yet."


def respond(fn):
	"""Run one endpoint and turn client errors into plain, safe messages."""

	@wraps(fn)
	def wrapper(*args, **kwargs):
		try:
			result = fn(*args, **kwargs) or {}
		except MissingPramaanKey as error:
			return {"available": False, "message": str(error)}
		except (ConnectionRequired, OrganizationNameRequired) as error:
			return {"available": False, "message": str(error)}
		except PramaanNotAvailable as error:
			return {"available": False, "message": str(error)}
		except PramaanError as error:
			if error.code in {"upstream_unavailable", "not_available_yet", "not_available"}:
				message = NOT_AVAILABLE_MESSAGE
			else:
				message = UNCERTAIN_MESSAGE if error.uncertain else GENERIC_MESSAGE
			return {"available": False, "message": message}
		result.setdefault("available", True)
		return result

	return wrapper


def get_client():
	from hrms.pramaan import PramaanClient

	return PramaanClient()
