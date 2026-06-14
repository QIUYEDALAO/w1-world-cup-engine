#!/usr/bin/env python3
"""Validate W1 manual lineup override hotfix."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERRIDE = ROOT / "data/manual_lineups/66456942.json"
SERVER = ROOT / "scripts/w1_local_predict_server.py"
BUILD = ROOT / "scripts/build_w1_dashboard_data.py"
DASHBOARD = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
FORBIDDEN = ["建议下注", "推荐投注", "稳赚", "必胜", "保证命中", "bet", "stake", "profit", "guaranteed"]


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_no_forbidden(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for term in FORBIDDEN:
        pattern = rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])" if term.isascii() else re.escape(term)
        if re.search(pattern, text, re.I):
            fail(f"{path.relative_to(ROOT)} contains forbidden term: {term}")


def assert_override_file() -> None:
    if not OVERRIDE.is_file():
        fail("manual lineup override file missing")
    data = read_json(OVERRIDE)
    expected = {
        "fixture_id": "66456942",
        "source": "Sky Sports",
        "source_type": "manual_verified",
        "status": "confirmed",
        "home_team": "Australia",
        "away_team": "Turkey",
        "home_formation": "3-4-2-1",
        "away_formation": "4-2-3-1",
    }
    for key, value in expected.items():
        if data.get(key) != value:
            fail(f"override {key} mismatch: {data.get(key)}")
    if len(data.get("home_starting_xi", [])) != 11 or len(data.get("away_starting_xi", [])) != 11:
        fail("override must contain 11 starters per side")
    notes = " ".join(data.get("notes_cn", []))
    for token in ("Sky Sports", "Kenan Yildiz", "Mathew Ryan", "BC Place"):
        if token not in notes:
            fail(f"override notes missing {token}")


def assert_code_paths() -> None:
    server = SERVER.read_text(encoding="utf-8")
    for token in (
        "MANUAL_LINEUPS_DIR",
        "manual_lineup_payload",
        "manual_lineup_payload_for_match",
        "card_path_for_manual_lineup",
        'source="manual_verified"',
        "Sky Sports",
    ):
        if token not in server:
            fail(f"server missing manual override token: {token}")
    build = BUILD.read_text(encoding="utf-8")
    for token in (
        "MANUAL_LINEUPS_DIR",
        "manual_lineup_for_card",
        "apply_manual_lineup_override",
        "lineup_source_name",
        "manual_lineup_fixture_id",
    ):
        if token not in build:
            fail(f"build script missing manual override token: {token}")


def assert_dashboard_data() -> None:
    result = subprocess.run([sys.executable, str(BUILD)], cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        fail(f"build_w1_dashboard_data.py failed: {result.stderr or result.stdout}")
    data = read_json(DASHBOARD)
    row = next((item for item in data.get("match_records", []) if item.get("match_en") in {"Australia vs Türkiye", "Australia vs Turkey"}), None)
    if not row:
        fail("Australia vs Turkey match record missing")
    if row.get("confirmed_lineup_available") is not True:
        fail("Australia vs Turkey confirmed_lineup_available must be true")
    expected = {
        "home_formation": "3-4-2-1",
        "away_formation": "4-2-3-1",
        "home_starting_count": 11,
        "away_starting_count": 11,
    }
    for key, value in expected.items():
        if row.get(key) != value:
            fail(f"Australia vs Turkey {key} mismatch: {row.get(key)}")
    lineups = row.get("lineups", {})
    if lineups.get("source") != "manual_verified" or lineups.get("source_name") != "Sky Sports":
        fail("Australia vs Turkey lineups source must be manual_verified / Sky Sports")
    if row.get("data_quality", {}).get("lineup", {}).get("status") != "ready":
        fail("Australia vs Turkey data_quality.lineup.status must be ready")
    if row.get("lineup_effect", {}).get("status") != "ready":
        fail("Australia vs Turkey lineup_effect.status must be ready")
    tactical = row.get("tactical_effect", {})
    if tactical.get("status") != "ready":
        fail("Australia vs Turkey tactical_effect.status must be ready")
    tactical_text = " ".join(tactical.get("home_style_tags", []) + tactical.get("away_style_tags", []))
    for token in ("三中卫", "翼卫推进", "中路保护", "中路组织", "攻守平衡", "控球推进"):
        if token not in tactical_text:
            fail(f"Australia vs Turkey tactical tags missing {token}")
    html = HTML.read_text(encoding="utf-8")
    for token in ("manual_verified", "Sky Sports", "3-4-2-1", "4-2-3-1"):
        if token not in html:
            fail(f"dashboard HTML missing {token}")


def main() -> int:
    try:
        assert_override_file()
        assert_code_paths()
        assert_dashboard_data()
        for path in (OVERRIDE, SERVER, BUILD, DASHBOARD, HTML):
            assert_no_forbidden(path)
    except (CheckError, json.JSONDecodeError) as exc:
        print(f"W1 manual lineup override check FAIL: {exc}", file=sys.stderr)
        return 1
    print("W1 manual lineup override check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
