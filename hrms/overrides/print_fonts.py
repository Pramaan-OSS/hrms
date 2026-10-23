"""Print fonts are immutable image assets, never fetched while rendering."""
import json
from pathlib import Path

FONT_ROOT = Path('/app/hrms/public/fonts')
FAMILIES = ('Inter', 'Noto Sans', 'DejaVu Sans', 'Liberation Sans')
MISSING_FONTS = 'Local print fonts are missing. Rebuild the application image to restore printing.'


def font_family(family=None):
	return family if family in FAMILIES else 'Inter'


def ensure_print_fonts(family=None):
	try:
		manifest = json.loads((FONT_ROOT / 'font-manifest.json').read_text())
		if not (FONT_ROOT / 'print-fonts.css').is_file() or not manifest:
			raise ValueError
		if not all(Path(name).name == name and (FONT_ROOT / name).is_file() for name in manifest):
			raise ValueError
	except (OSError, ValueError, TypeError):
		raise RuntimeError(MISSING_FONTS) from None


def font_paths():
	ensure_print_fonts()
	return ['/usr/share/fonts', str(FONT_ROOT)]
