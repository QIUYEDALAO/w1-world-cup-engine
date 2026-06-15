#!/usr/bin/env python3
"""Validate W1 dashboard and report templates."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "reports/dashboard/W1_LIVE_DASHBOARD.md"
TEMPLATES = ROOT / "docs/W1_REPORT_TEMPLATES.md"
STATE = ROOT / "state/w1_refresh_state.json"
POLICY = ROOT / "config/w1_decision_policy.json"
DECISION_LABELS = {"W1_WAIT", "W1_WATCH", "W1_PLAY", "W1_PASS", "W1_SKIP", "W1_BLOCKED"}

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


def current_state() -> tuple[dict, dict]:
    state = json.loads(read(STATE))
    policy = json.loads(read(POLICY))
    return state, policy


def require_section(text: str, heading: str) -> None:
    if heading not in text:
        fail(f"Dashboard section missing: {heading}")


def parse_decision_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for match in re.finditer(r"\| (W1_[A-Z]+) \| (\d+) \|", text):
        counts[match.group(1)] = int(match.group(2))
    missing = {"W1_WAIT", "W1_WATCH", "W1_PLAY", "W1_PASS"} - set(counts)
    if missing:
        fail(f"Dashboard decision count labels missing: {sorted(missing)}")
    invalid = set(counts) - DECISION_LABELS
    if invalid:
        fail(f"Dashboard decision count labels invalid: {sorted(invalid)}")
    return counts


def assert_dashboard() -> None:
    if not DASHBOARD.is_file():
        fail("Dashboard file is missing")
    assert_no_forbidden_terms(DASHBOARD)

    text = read(DASHBOARD)
    state, policy = current_state()
    for section in ("## Decision Counts", "## First Match", "## Runtime", "## Unresolved Data Gaps", "## Notes"):
        require_section(text, section)
    counts = parse_decision_counts(text)
    if sum(counts.values()) <= 0:
        fail("Dashboard decision counts must be numeric and non-empty")
    required_tokens = [
        "| fixture_id |",
        "| match |",
        "| kickoff_utc |",
        "| current_decision |",
        "| lineup_status |",
        "| referee_status |",
        "| ledger_required |",
        "| next_refresh |",
        state["watcher_version"],
        policy["play_guard_version"],
        "confirmed_lineup",
        "suspensions",
        "travel_distance",
    ]
    for token in required_tokens:
        if token not in text:
            fail(f"Dashboard missing token: {token}")
    next_refresh_match = re.search(r"\| next_refresh \| ([^|]+) \|", text)
    if not next_refresh_match:
        fail("Dashboard next_refresh field missing")
    if not re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} CST$", next_refresh_match.group(1).strip()):
        fail(f"Dashboard next_refresh format invalid: {next_refresh_match.group(1).strip()}")


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
