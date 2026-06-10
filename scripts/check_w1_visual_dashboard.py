#!/usr/bin/env python3
"""Validate W1_VISUAL_DASHBOARD_V1 static artifacts."""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
DATA_JSON = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
GROUP_CONTEXT = ROOT / "data/static/world_cup_2026_groups.json"
LEDGER = ROOT / "data/processed/ledger/w1_ledger_group_stage_round1.csv"
DOC = ROOT / "docs/W1_VISUAL_DASHBOARD.md"
FORBIDDEN_TERMS = ["Q" + "Q", "offi" + "cial", "pend" + "ing", "V" + "3", "V" + "4", "M" + "1"]


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(read(path))


def assert_no_forbidden_terms(path: Path) -> None:
    text = read(path)
    for term in FORBIDDEN_TERMS:
        if term in text:
            fail(f"Forbidden term found in {path.relative_to(ROOT)}")


def current_fixture_teams() -> set[str]:
    with LEDGER.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 24:
        fail(f"Expected 24 ledger rows, found {len(rows)}")
    teams: set[str] = set()
    for row in rows:
        teams.add(row["home_team"])
        teams.add(row["away_team"])
    if len(teams) != 48:
        fail(f"Expected 48 unique fixture teams, found {len(teams)}")
    return teams


def assert_dashboard_data(data: dict) -> None:
    if data.get("schema_version") != "W1_VISUAL_DASHBOARD_V1":
        fail("Dashboard data schema_version mismatch")

    groups = data.get("groups", [])
    if len(groups) != 12:
        fail(f"Expected 12 groups, found {len(groups)}")
    expected_letters = list("ABCDEFGHIJKL")
    if [group.get("group") for group in groups] != expected_letters:
        fail("Groups must be A-L in order")

    teams: list[str] = []
    for group in groups:
        group_teams = group.get("teams", [])
        if len(group_teams) != 4:
            fail(f"Group {group.get('group')} must contain 4 teams")
        teams.extend(group_teams)
        template = group.get("standings_template", [])
        if len(template) != 4:
            fail(f"Group {group.get('group')} standings template must contain 4 rows")
        for row in template:
            for key in ("P", "W", "D", "L", "GF", "GA", "GD", "PTS"):
                if key not in row:
                    fail(f"Standings template missing {key}")

    if len(teams) != 48:
        fail(f"Expected 48 teams, found {len(teams)}")
    if len(set(teams)) != 48:
        fail("Duplicate team found in group context")

    fixture_teams = current_fixture_teams()
    missing = sorted(fixture_teams - set(teams))
    if missing:
        fail(f"Fixture teams missing from group context: {missing}")

    rules = data.get("advancement_rules", {})
    expected_rules = {
        "direct_qualifiers": 24,
        "best_third_qualifiers": 8,
        "round_of_32_total": 32,
        "groups_total": 12,
        "teams_per_group": 4,
    }
    for key, expected in expected_rules.items():
        if rules.get(key) != expected:
            fail(f"Advancement rule mismatch for {key}: {rules.get(key)}")
    if rules["direct_qualifiers"] + rules["best_third_qualifiers"] != rules["round_of_32_total"]:
        fail("Advancement rule totals do not sum to Round of 32")
    for key in ("points", "goal_diff", "goals_for", "fair_play", "drawing_of_lots"):
        if key not in rules.get("third_place_tiebreakers", []):
            fail(f"Missing third-place tiebreaker: {key}")

    if len(data.get("third_place_ranking_template", [])) != 12:
        fail("Third-place ranking template must contain 12 rows")

    first = data.get("first_match", {})
    if first.get("match") != "Mexico vs South Africa":
        fail("First match must be Mexico vs South Africa")
    if first.get("decision") != "W1_WAIT":
        fail("First match decision must be W1_WAIT")
    if first.get("odds_status") != "READY":
        fail("First match odds status must be READY")
    if first.get("play_guard_pass") is not False:
        fail("First match play_guard_pass must be false while lineup is missing")


def assert_html(data: dict) -> None:
    if not HTML.is_file():
        fail("HTML dashboard is missing")
    assert_no_forbidden_terms(HTML)
    text = read(HTML)
    required = [
        "W1 Visual Dashboard V1",
        "W1_PLAY_GUARD_V1",
        "Mexico vs South Africa",
        "Round of 32",
        "direct qualifiers",
        "best third-place qualifiers",
        "'P'",
        "'PTS'",
        "drawing_of_lots",
        "W1_LIVE_DASHBOARD.md",
        "W1_REPORT_TEMPLATES.md",
        "W1_PROJECT_REPORT_FOR_EXPERT_REVIEW.md",
    ]
    for token in required:
        if token not in text:
            fail(f"HTML missing token: {token}")
    if "fetch(" in text:
        fail("HTML should not require fetch for double-click use")

    embedded = re.search(r'<script id="w1-data" type="application/json">(.*?)</script>', text, re.S)
    if not embedded:
        fail("HTML must embed dashboard data for file-open use")
    try:
        embedded_data = json.loads(embedded.group(1))
    except json.JSONDecodeError as exc:
        fail(f"Embedded dashboard JSON is not parseable: {exc}")
    if embedded_data != data:
        fail("Embedded dashboard JSON must match asset data JSON")


def main() -> int:
    try:
        for path in (DATA_JSON, GROUP_CONTEXT, DOC):
            if not path.is_file():
                fail(f"Missing artifact: {path.relative_to(ROOT)}")
            assert_no_forbidden_terms(path)
        data = load_json(DATA_JSON)
        group_context = load_json(GROUP_CONTEXT)
        if data != group_context:
            fail("Dashboard data and group context JSON must match")
        assert_dashboard_data(data)
        assert_html(data)
    except CheckError as exc:
        print(f"W1 visual dashboard self-test FAIL: {exc}", file=sys.stderr)
        return 1

    print("W1 visual dashboard self-test PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
