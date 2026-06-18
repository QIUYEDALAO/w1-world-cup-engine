#!/usr/bin/env python3
"""Shared W1 result overlay loader.

Reads result overlays from config/w1_competition_scope.json. Legacy result files
are loaded first and the configured tournament overlay is loaded last, so the
newer overlay wins on duplicate fixture ids. Alias fixture ids are expanded to
the same row. This module is read-only and never writes match cards or Scout
state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCOPE_JSON = ROOT / "config/w1_competition_scope.json"


def root_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def competition_scope() -> dict[str, Any]:
    if not SCOPE_JSON.is_file():
        raise FileNotFoundError(f"missing competition scope: {SCOPE_JSON.relative_to(ROOT)}")
    return json.loads(SCOPE_JSON.read_text(encoding="utf-8"))


def configured_result_paths() -> list[Path]:
    scope = competition_scope()
    paths: list[Path] = []
    for path in scope.get("legacy_results", []) or []:
        paths.append(root_path(path))
    overlay = scope.get("results_overlay")
    if overlay:
        paths.append(root_path(overlay))
    return paths


def load_results_map() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in configured_result_paths():
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for fid, row in payload.get("results", {}).items():
            row = dict(row)
            row.setdefault("result_overlay_path", str(path.relative_to(ROOT)))
            out[str(fid)] = row
            for alias in row.get("alias_fixture_ids", []) or []:
                out[str(alias)] = row
    return out
