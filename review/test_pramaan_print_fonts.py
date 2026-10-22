"""Printing uses complete local image assets with no download fallback."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class LocalPrintFontTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        scratch = root / '.scratch'
        scratch.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        spec = importlib.util.spec_from_file_location('print_fonts_test', root / 'hrms/overrides/print_fonts.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        patcher = patch.object(self.module, 'FONT_ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_assets(self):
        (self.root / 'print-fonts.css').write_text('local font faces')
        (self.root / 'font-manifest.json').write_text(json.dumps(['Inter-regular.otf', 'Inter-bold.otf']))
        for name in ['Inter-regular.otf', 'Inter-bold.otf']:
            (self.root / name).write_bytes(b'local fixture font')

    def test_supported_families_are_preserved_and_unknown_names_fall_back_locally(self):
        self.assertEqual(self.module.font_family('Noto Sans'), 'Noto Sans')
        self.assertEqual(self.module.font_family(None), 'Inter')
        self.assertEqual(self.module.font_family('../../remote-font'), 'Inter')

    def test_missing_font_assets_require_a_build_instead_of_a_download(self):
        with self.assertRaisesRegex(RuntimeError, 'Rebuild the application image'):
            self.module.ensure_print_fonts('Inter')

    def test_complete_font_paths_exclude_the_old_site_download_cache(self):
        self.make_assets()
        self.module.ensure_print_fonts('Inter')
        self.assertEqual(self.module.font_paths(), ['/usr/share/fonts', str(self.root)])

    def test_partial_assets_are_not_used_as_a_completed_bundle(self):
        self.make_assets()
        (self.root / 'Inter-bold.otf').unlink()
        with self.assertRaisesRegex(RuntimeError, 'Rebuild the application image'):
            self.module.font_paths()
