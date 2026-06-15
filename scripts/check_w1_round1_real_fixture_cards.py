#!/usr/bin/env python3
"""Validate W1 Group Stage Round 1 cards after real fixture replacement."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_JSON = ROOT / "data/snapshots/group_stage_round1/w1_round1_fixture_details_20260610_1445.json"
FIXTURE_CSV = ROOT / "data/snapshots/group_stage_round1/w1_round1_fixture_details_20260610_1445.csv"
SUMMARY = ROOT / "data/snapshots/group_stage_round1/w1_round1_snapshot_summary.json"
CARDS_DIR = ROOT / "data/processed/match_cards/group_stage_round1"
LEDGER = ROOT / "data/processed/ledger/w1_ledger_group_stage_round1.csv"
REPORT = ROOT / "reports/match_previews/W1_GROUP_STAGE_ROUND1_REAL_FIXTURE_CARDS.md"

EXPECTED_COUNT = 24
ALLOWED_DECISIONS = {"W1_WAIT", "W1_PLAY", "W1_SKIP", "W1_BLOCKED", "W1_WATCH", "W1_PASS"}
WAITING_LINEUP_STATUSES = {"WAIT_EVENT", "WAIT", "MISSING"}
CONFIRMED_LINEUP_STATUSES = {"CONFIRMED", "READY"}
FORBIDDEN_KEYS = {"opening" + "_odds"}
FORBIDDEN_TEXT = [
    "\u63a8" + "\u8350",
    "\u9884\u6d4b" + "\u65b9\u5411",
    "offi" + "cial",
    "pend" + "ing",
    "Q" + "Q",
    "\u7a33" + "\u8d5a",
    "\u547d\u4e2d" + "\u7387",
]


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def walk(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_KEYS:
                fail(f"Forbidden key found at {path}.{key}")
            walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            walk(child, f"{path}[{index}]")


def assert_no_forbidden_text(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for term in FORBIDDEN_TEXT:
        if term in text:
            fail(f"Forbidden text found in {path.relative_to(ROOT)}")


def load_fixture_rows() -> list[dict[str, Any]]:
    payload = load_json(FIXTURE_JSON)
    rows = payload.get("matches", [])
    if payload.get("matches_found") != EXPECTED_COUNT:
        fail("fixture JSON matches_found must be 24")
    if len(rows) != EXPECTED_COUNT:
        fail(f"fixture JSON rows must be 24, got {len(rows)}")
    with FIXTURE_CSV.open("r", encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    if len(csv_rows) != EXPECTED_COUNT:
        fail(f"fixture CSV rows must be 24, got {len(csv_rows)}")
    if [str(row["fixture_id"]) for row in csv_rows] != [str(row["fixture_id"]) for row in rows]:
        fail("fixture JSON/CSV fixture_id order mismatch")
    return rows


def assert_summary() -> None:
    summary = load_json(SUMMARY)
    walk(summary)
    checks = {
        "matches_found": summary.get("matches_found"),
        "fixture_rows_json": summary.get("fixture_rows_json"),
        "fixture_rows_csv": summary.get("fixture_rows_csv"),
        "cards_updated": summary.get("cards_updated"),
        "ledger_rows": summary.get("ledger_rows"),
    }
    for key, value in checks.items():
        if value != EXPECTED_COUNT:
            fail(f"summary {key} must be 24, got {value}")
    distribution = summary.get("decision_distribution", {})
    if set(distribution) - ALLOWED_DECISIONS:
        fail(f"summary decision_distribution contains invalid labels: {sorted(set(distribution) - ALLOWED_DECISIONS)}")
    if sum(int(value or 0) for value in distribution.values()) != EXPECTED_COUNT:
        fail("summary decision_distribution must sum to 24")
    if summary["lineup_status"]["status"] not in {"WAIT_EVENT", "WAIT"}:
        fail("summary lineup_status must be WAIT_EVENT or WAIT")
    if summary["referee_status"]["status"] not in {"MISSING", "WAIT_EVENT"}:
        fail("summary referee_status must be MISSING or WAIT_EVENT")


def assert_card(path: Path, fixture: dict[str, Any]) -> str:
    card = load_json(path)
    walk(card)
    assert_no_forbidden_text(path)

    fixture_id = str(fixture["fixture_id"])
    if card["match"]["match_id"] != f"api-football:{fixture_id}":
        fail(f"{path.name}: match_id does not match fixture_id")
    if card["teams"]["home"]["name"] != fixture["home_team"]:
        fail(f"{path.name}: home_team mismatch")
    if card["teams"]["away"]["name"] != fixture["away_team"]:
        fail(f"{path.name}: away_team mismatch")
    if card["match"]["venue"]["name"] != fixture["venue"]:
        fail(f"{path.name}: venue mismatch")
    if card["match"]["round"] != fixture["group"]:
        fail(f"{path.name}: group mismatch")

    decision = card["decision"]
    label = decision["label"]
    if label not in ALLOWED_DECISIONS:
        fail(f"{path.name}: final_decision invalid: {label}")
    if decision["ledger_required"] is not True:
        fail(f"{path.name}: ledger_required must be true")
    if decision["no_betting_commitment"] is not True:
        fail(f"{path.name}: no_betting_commitment must be true")
    reasons = decision.get("reasons", {})
    reason_text = json.dumps(reasons, ensure_ascii=False) if isinstance(reasons, (dict, list)) else str(reasons)
    lineup = card.get("lineups", {})
    kickoff_utc = card.get("match", {}).get("kickoff_utc")
    if not kickoff_utc or "T" not in kickoff_utc:
        fail(f"{path.name}: kickoff_utc must be present and ISO-like")

    for market in ("odds_1X2", "odds_AH", "odds_OU"):
        block = card["markets"][market]
        if block["available"] is not True:
            fail(f"{path.name}: {market} must be available")
        if not any(line.get("status") == "READY" for line in block.get("lines", [])):
            fail(f"{path.name}: {market} must be READY")

    if not card["squad"]["home"]["available"] or not card["squad"]["away"]["available"]:
        fail(f"{path.name}: squad must be available")
    if card["context"]["standings"]["status"] != "OK":
        fail(f"{path.name}: standings must be READY/OK")
    if card["context"]["h2h"]["status"] not in {"OK", "READY", "PARTIAL", "MISSING"}:
        fail(f"{path.name}: H2H status invalid")
    lineup_confirmed = lineup.get("confirmed_lineup_available") is True
    lineup_status = lineup.get("status")
    if label == "W1_WAIT":
        if lineup_status not in WAITING_LINEUP_STATUSES | CONFIRMED_LINEUP_STATUSES:
            fail(f"{path.name}: W1_WAIT lineup status invalid")
        if not any(token in reason_text for token in ("confirmed_lineup missing", "W1 hard rule", "WAIT")):
            fail(f"{path.name}: W1_WAIT reason must explain waiting/blocking condition")
    if label == "W1_PLAY":
        if not lineup_confirmed or lineup_status not in CONFIRMED_LINEUP_STATUSES:
            fail(f"{path.name}: W1_PLAY must have confirmed lineup state")
        if decision.get("play_guard_version") != "W1_PLAY_GUARD_V1":
            fail(f"{path.name}: W1_PLAY must carry W1_PLAY_GUARD_V1")
        if "W1_PLAY_GUARD_V1" not in reason_text and "all rules pass" not in reason_text:
            fail(f"{path.name}: W1_PLAY reason must explain play guard pass")
    if card["match"]["referee"]["available"] is not False:
        fail(f"{path.name}: referee must remain unavailable")

    gap_fields = {gap["field"] for gap in card["data_gaps"]}
    if label == "W1_WAIT" and not lineup_confirmed and "lineups.confirmed_lineup" not in gap_fields:
        fail(f"{path.name}: missing confirmed lineup gap")
    if label == "W1_PLAY" and "lineups.confirmed_lineup" in gap_fields:
        fail(f"{path.name}: W1_PLAY must not retain confirmed lineup gap")
    return label


def assert_ledger(fixtures_by_id: dict[str, dict[str, Any]]) -> None:
    with LEDGER.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != EXPECTED_COUNT:
        fail(f"ledger rows must be 24, got {len(rows)}")
    seen = set()
    for row in rows:
        fixture_id = row["fixture_id"]
        if fixture_id not in fixtures_by_id:
            fail(f"ledger unknown fixture_id {fixture_id}")
        fixture = fixtures_by_id[fixture_id]
        seen.add(fixture_id)
        if row["home_team"] != fixture["home_team"] or row["away_team"] != fixture["away_team"]:
            fail(f"ledger team mismatch for fixture {fixture_id}")
        if row["final_decision"] not in ALLOWED_DECISIONS:
            fail(f"ledger final_decision invalid for fixture {fixture_id}: {row['final_decision']}")
        if row["ledger_required"] != "true":
            fail(f"ledger_required must be true for fixture {fixture_id}")
        if row["lineup_status"] not in WAITING_LINEUP_STATUSES | CONFIRMED_LINEUP_STATUSES:
            fail(f"ledger lineup_status invalid for fixture {fixture_id}")
        if row["referee_status"] not in {"MISSING", "WAIT_EVENT"}:
            fail(f"ledger referee_status invalid for fixture {fixture_id}")
        if row["final_decision"] == "W1_WAIT" and "confirmed_lineup missing" not in row["reason"]:
            fail(f"ledger reason must contain confirmed_lineup missing for fixture {fixture_id}")
    if len(seen) != EXPECTED_COUNT:
        fail("ledger fixture_id set must contain 24 unique fixtures")


def main() -> int:
    try:
        for path in (FIXTURE_JSON, FIXTURE_CSV, SUMMARY, LEDGER, REPORT):
            if not path.is_file():
                fail(f"Missing required artifact: {path.relative_to(ROOT)}")

        fixtures = load_fixture_rows()
        fixtures_by_id = {str(row["fixture_id"]): row for row in fixtures}
        assert_summary()

        json_cards = sorted(CARDS_DIR.glob("*.json"))
        md_cards = sorted(CARDS_DIR.glob("*.md"))
        if len(json_cards) != EXPECTED_COUNT:
            fail(f"JSON cards must be 24, got {len(json_cards)}")
        if len(md_cards) != EXPECTED_COUNT:
            fail(f"Markdown cards must be 24, got {len(md_cards)}")

        distribution = Counter()
        for fixture in fixtures:
            fixture_id = str(fixture["fixture_id"])
            matches = [path for path in json_cards if path.name.startswith(f"fixture_{fixture_id}_")]
            if len(matches) != 1:
                fail(f"Expected exactly one JSON card for fixture {fixture_id}")
            distribution[assert_card(matches[0], fixture)] += 1
            md_matches = [path for path in md_cards if path.name.startswith(f"fixture_{fixture_id}_")]
            if len(md_matches) != 1:
                fail(f"Expected exactly one Markdown card for fixture {fixture_id}")
            assert_no_forbidden_text(md_matches[0])
            text = md_matches[0].read_text(encoding="utf-8")
            if "Final Decision:**" not in text:
                fail(f"{md_matches[0].name}: markdown final decision field missing")

        if sum(distribution.values()) != EXPECTED_COUNT or set(distribution) - ALLOWED_DECISIONS:
            fail(f"decision distribution invalid: {dict(distribution)}")

        assert_ledger(fixtures_by_id)
        assert_no_forbidden_text(REPORT)
    except CheckError as exc:
        print(f"W1 Round1 real fixture cards self-test FAIL: {exc}", file=sys.stderr)
        return 1

    print("W1 Round1 real fixture cards self-test PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
