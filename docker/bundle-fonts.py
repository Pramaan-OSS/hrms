"""Copy installed print fonts and notices into the image's local web assets."""
from pathlib import Path
import json
import shutil
import subprocess

families = {
    'Inter': 'fonts-inter',
    'Noto Sans': 'fonts-noto-core',
    'DejaVu Sans': 'fonts-dejavu-core',
    'Liberation Sans': 'fonts-liberation',
}
target = Path('hrms/public/fonts')
target.mkdir(parents=True, exist_ok=True)
manifest = []
css = []
for family, package in families.items():
    slug = family.replace(' ', '-')
    for style, weight in [('Regular', 400), ('Bold', 700)]:
        found = subprocess.check_output(['fc-match', '-f', '%{family}\n%{file}\n', f'{family}:style={style}'], text=True).splitlines()
        if family.casefold() not in found[0].casefold():
            raise SystemExit(f'The installed print font is missing: {family}.')
        source = Path(found[1])
        suffix = source.suffix.lower()
        if suffix not in {'.ttf', '.otf'}:
            raise SystemExit('The installed print font has an unsupported format.')
        name = f'{slug}-{style.lower()}{suffix}'
        shutil.copyfile(source, target / name)
        manifest.append(name)
        kind = 'truetype' if suffix == '.ttf' else 'opentype'
        css.append(f'@font-face {{ font-family: "{family}"; font-style: normal; font-weight: {weight}; font-display: swap; src: url("/assets/hrms/fonts/{name}") format("{kind}"); }}')
    shutil.copyfile(Path('/usr/share/doc') / package / 'copyright', target / f'{slug}-LICENSE.txt')
(target / 'print-fonts.css').write_text('\n'.join(css) + '\n')
(target / 'font-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('Bundled four print font families and their license notices.')
