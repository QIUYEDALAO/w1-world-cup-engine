#!/usr/bin/env python3
"""Compatibility wrapper for the W1 safe-view checker."""

from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
runpy.run_path(str(ROOT / "scripts/check_w1_output_safe_view.py"), run_name="__main__")
