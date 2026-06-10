#!/usr/bin/env python3
"""Validate W1 dashboard and report templates."""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "reports/dashboard/W1_LIVE_DASHBOARD.md"
TEMPLATES = ROOT / "docs/W1_REPORT_TEMPLATES.md"
CARDS_DIR = ROOT / "data/processed/match_cards/group_stage_round1"
LEDGER = ROOT / "data/processed/ledger/w1_ledger_group_stage_round1.csv"
STATE = ROOT / "state/w1_refresh_state.json"
POLICY = ROOT / "config/w1_decision_policy.json"

FORBIDDEN_TERMS = ["Q" + "Q", "offi" + "cial", "pend" + "ing"]


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def assert_no_forbidden_terms(path: Path) -> None:
    text = read(path)
    for term in FORBIDDEN_TERMS:
        if term in text:
            fail(f"Forbidden term found in {path.relative_to(ROOT)}")


def current_state() -> tuple[Counter, dict[str, str], dict, dict]:
    cards = []
    for path in sorted(CARDS_DIR.glob("*.json")):
        cards.append(json.loads(read(path)))
    if len(cards) != 24:
        fail(f"Expected 24 current match cards, found {len(cards)}")

    with LEDGER.open("r", encoding="utf-8", newline="") as handle:
        ledger_rows = list(csv.DictReader(handle))
    if len(ledger_rows) != 24:
        fail(f"Expected 24 ledger rows, found {len(ledger_rows)}")

    distribution = Counter(card["decision"]["label"] for card in cards)
    first = next((row for row in ledger_rows if row["fixture_id"] == "1489369"), None)
    if not first:
        fail("First fixture 1489369 not found in ledger")

    state = json.loads(read(STATE))
    policy = json.loads(read(POLICY))
    return distribution, first, state, policy


def assert_dashboard() -> None:
    if not DASHBOARD.is_file():
        fail("Dashboard file is missing")
    assert_no_forbidden_terms(DASHBOARD)

    text = read(DASHBOARD)
    distribution, first, state, policy = current_state()
    expected_counts = {
        "W1_WAIT": distribution.get("W1_WAIT", 0),
        "W1_WATCH": distribution.get("W1_WATCH", 0),
        "W1_PLAY": distribution.get("W1_PLAY", 0),
        "W1_PASS": distribution.get("W1_PASS", 0),
    }
    for label, count in expected_counts.items():
        pattern = rf"\\| {label} \\| {count} \\|"
        if not re.search(pattern, text):
            fail(f"Dashboard count mismatch for {label}")

    required_values = [
        first["home_team"] + " vs " + first["away_team"],
        first["final_decision"],
        first["lineup_status"],
        first["referee_status"],
        state["next_run_cst"],
        state["watcher_version"],
        policy["play_guard_version"],
        "confirmed_lineup",
        "suspensions",
        "travel_distance",
    ]
    for value in required_values:
        if value not in text:
            fail(f"Dashboard missing value: {value}")


def assert_templates() -> None:
    if not TEMPLATES.is_file():
        fail("Template file is missing")
    assert_no_forbidden_terms(TEMPLATES)

    text = read(TEMPLATES)
    required_sections = [
        "## 1. No-Change Watcher Status Report",
        "## 2. Match Update Report",
        "## 3. Formal Pre-Match W1 Report",
        "## 4. Stage-End Summary",
    ]
    for section in required_sections:
        if section not in text:
            fail(f"Template section missing: {section}")
    for required in ("W1_PLAY_GUARD_V1", "substantial change", "ledger_required", "calibration_cycle"):
        if required not in text:
            fail(f"Template missing required token: {required}")


def main() -> int:
    try:
        assert_dashboard()
        assert_templates()
    except CheckError as exc:
        print(f"W1 report templates self-test FAIL: {exc}", file=sys.stderr)
        return 1

    print("W1 report templates self-test PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

