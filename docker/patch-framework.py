"""Apply local rendering fixes to the pinned framework."""
from pathlib import Path

path = Path("vendor/framework/frappe/public/js/frappe/widgets/chart_widget.js")
source = path.read_text()
old = """\t\t\t} else if (is_circular_chart) {
\t\t\t\tthis.chart_wrapper.empty();"""
new = """\t\t\t} else if (is_circular_chart) {
\t\t\t\tthis.dashboard_chart.destroy();
\t\t\t\tthis.chart_wrapper.empty();"""
if new not in source:
    if source.count(old) != 1:
        raise SystemExit("The pinned dashboard chart source changed; review its instance cleanup.")
    path.write_text(source.replace(old, new, 1))

old = "\t\treturn chart_args;"
new = "\t\tchart_args.animate = 0;\n\t\tchart_args.disableEntryAnimation = true;\n\t\treturn chart_args;"
source = path.read_text()
if new not in source:
    if source.count(old) != 1:
        raise SystemExit("The pinned dashboard chart options changed; review animation handling.")
    path.write_text(source.replace(old, new, 1))


path = Path("vendor/framework/frappe/utils/chromium/download.py")
source = path.read_text()
local_finder = """def find_or_download_chromium_executable():
	from hrms.overrides.chromium import find_local_chromium_executable

	return find_local_chromium_executable()


"""
blocked_download = """def download_chromium():
	from hrms.overrides.chromium import refuse_chromium_download

	return refuse_chromium_download()


"""
for start, end, replacement, expected in [
    ("def find_or_download_chromium_executable():", "def download_chromium():", local_finder, "exec_path.exists()"),
    ("def download_chromium():", "def get_chromium_download_url():", blocked_download, "requests.get(download_url"),
]:
    if replacement in source:
        continue
    if source.count(start) != 1 or source.count(end) != 1:
        raise SystemExit("The pinned PDF browser helpers changed; review local browser selection.")
    first, last = source.index(start), source.index(end)
    if expected not in source[first:last]:
        raise SystemExit("The pinned PDF browser helper changed; review runtime download removal.")
    source = source[:first] + replacement + source[last:]
path.write_text(source)


path = Path('vendor/framework/frappe/utils/typst_emitter.py')
source = path.read_text()
for start, end, replacement, expected in [
    ('def typst_font_paths()', 'def compile_typst_source(', 'def typst_font_paths() -> list[str]:\n\tfrom hrms.overrides.print_fonts import font_paths\n\n\treturn font_paths()\n\n\n', 'typst_fonts'),
    ('def font_family(', 'def ensure_typst_fonts(', 'def font_family(font: str | None) -> str:\n\tfrom hrms.overrides.print_fonts import font_family as local_family\n\n\treturn local_family(font)\n\n\n', 'DEFAULT_FONT'),
    ('def ensure_typst_fonts(', 'def _font_cache_path(', 'def ensure_typst_fonts(family: str | None):\n\tfrom hrms.overrides.print_fonts import ensure_print_fonts\n\n\treturn ensure_print_fonts(family)\n\n\n', 'frappe.enqueue'),
    ('def fetch_typst_font(', '_CONTROL_CHARS =', 'def fetch_typst_font(family: str):\n\tfrom hrms.overrides.print_fonts import ensure_print_fonts\n\n\treturn ensure_print_fonts(family)\n\n\n', 'requests.get'),
]:
    if replacement in source:
        continue
    if source.count(start) != 1 or source.count(end) != 1:
        raise SystemExit('The pinned print font helpers changed; review local font handling.')
    first, last = source.index(start), source.index(end)
    if expected not in source[first:last]:
        raise SystemExit('The pinned print font helper changed; review runtime download removal.')
    source = source[:first] + replacement + source[last:]
path.write_text(source)

path = Path('vendor/framework/frappe/templates/print_format/print_format_font.css')
local_css = Path('docker/print-format-font.css').read_text()
if path.read_text() != local_css:
    if 'fonts.googleapis.com' not in path.read_text():
        raise SystemExit('The pinned print font stylesheet changed; review local font assets.')
    path.write_text(local_css)

import json
import re
families = ['Inter', 'Noto Sans', 'DejaVu Sans', 'Liberation Sans']
Path('vendor/framework/frappe/data/google_fonts.json').write_text(json.dumps(families, indent=2) + '\n')
path = Path('vendor/framework/frappe/printing/page/print/print.js')
source = path.read_text()
pattern = r'(fieldname: "print_font",\s+label: __\("Font"\),\s+options: \[)(.*?)(\n\s+\],)'
matched = list(re.finditer(pattern, source, flags=re.S))
if len(matched) != 1:
    raise SystemExit('The pinned print font picker changed; review its bundled choices.')
match = matched[0]
if '"DejaVu Sans"' not in match[2]:
    if '"Merriweather"' not in match[2]:
        raise SystemExit('The pinned print font picker changed; review its external choices.')
    choices = '\n\t\t\t\t\t{ label: __("Default"), value: "" },\n' + ''.join(f'\t\t\t\t\t"{family}",\n' for family in families)
    source = source[:match.start(2)] + choices.rstrip('\n') + source[match.end(2):]
    path.write_text(source)

# Controls can initialize before a saved document has finished loading.
old = '\tpreview() {\n\t\tthis.toggle_style_picker();'
new = '\tpreview() {\n\t\tif (!this.frm?.doc) return;\n\t\tthis.toggle_style_picker();'
source = path.read_text()
if new not in source:
    if source.count(old) != 1:
        raise SystemExit('The pinned print preview changed; review document initialization.')
    path.write_text(source.replace(old, new, 1))
