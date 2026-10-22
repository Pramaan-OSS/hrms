"""Standalone checks: python3 -m unittest discover -s review -p 'test_*.py'."""

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "hrms" / "pramaan.py"
SPEC = importlib.util.spec_from_file_location("pramaan_stub_boundary", MODULE_PATH)
boundary = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = boundary
SPEC.loader.exec_module(boundary)
