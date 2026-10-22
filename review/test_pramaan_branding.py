"""Template titles and launcher visibility without a running site."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class BrandingTests(unittest.TestCase):
    def setUp(self):
        self.values = {"Website Settings": "Frappe", "System Settings": ""}
        self.frappe = types.ModuleType("frappe")
        self.frappe.get_meta = lambda doctype: types.SimpleNamespace(has_field=lambda name: True)
        self.frappe.db = types.SimpleNamespace(
            get_single_value=lambda doctype, field: self.values[doctype],
            set_single_value=lambda doctype, field, value: self.values.update({doctype: value}),
        )
        with patch.dict(sys.modules, {"frappe": self.frappe}):
            spec = importlib.util.spec_from_file_location("branding_test", Path(__file__).resolve().parents[1] / "hrms/overrides/branding.py")
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)

    def test_inherited_and_missing_titles_become_the_template_title(self):
        self.module.apply_branding()
        self.assertEqual(set(self.values.values()), {"HRMS"})

    def test_owner_title_is_preserved(self):
        self.values["Website Settings"] = "Team Workspace"
        self.module.apply_branding()
        self.assertEqual(self.values["Website Settings"], "Team Workspace")

    def test_launcher_hides_dependencies_without_removing_their_routes(self):
        boot = {"app_data": [{"app_name": name, "on_apps_screen": True, "dock": ["entry"]} for name in ("hrms", "erpnext", "frappe")]}
        self.module.extend_bootinfo(boot)
        self.assertEqual([app["app_name"] for app in boot["app_data"] if app["on_apps_screen"]], ["hrms"])
        self.assertTrue(all(app["dock"] == ["entry"] for app in boot["app_data"]))
