#!/usr/bin/env python3
"""Validate W1 Group Stage Round 1 initial cards.

This checker is intentionally local-only. It reads generated artifacts and does
not call external APIs.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "data/snapshots/group_stage_round1/w1_round1_snapshot_summary.json"
CARDS_DIR = ROOT / "data/processed/match_cards/group_stage_round1"
LEDGER = ROOT / "data/processed/ledger/w1_ledger_group_stage_round1.csv"
REPORT = ROOT / "reports/match_previews/W1_GROUP_STAGE_ROUND1_INITIAL_CARDS.md"

FORBIDDEN_KEYS = {"opening" + "_odds"}
FORBIDDEN_DECISIONS = {"W1_PLAY", "W1_WATCH", "W1_PASS"}
FORBIDDEN_TEXT = [
    "\u63a8" + "\u8350",
    "\u9884\u6d4b" + "\u65b9\u5411",
    "offi" + "cial",
    "pend" + "ing",
    "Q" + "Q",
    "\u7a33" + "\u8d5a",
    "\u547d\u4e2d" + "\u7387",
]
EXPECTED_COUNT = 24


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def walk(value: Any, path: str = "$") -> list[tuple[str, Any]]:
    items = [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_KEYS:
                fail(f"Forbidden key found at {path}.{key}")
            items.extend(walk(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            items.extend(walk(child, f"{path}[{index}]"))
    return items


def assert_no_forbidden_text(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    allowed_phrases = [
        "No prediction direction or recommendation is produced",
        "no prediction direction or recommendation is produced",
        "do not include prediction direction, recommendation",
    ]
    scrubbed = text
    for phrase in allowed_phrases:
        scrubbed = scrubbed.replace(phrase, "")
    for term in FORBIDDEN_TEXT:
        if term in scrubbed:
            fail(f"Forbidden text '{term}' found in {path.relative_to(ROOT)}")


def assert_card(path: Path) -> str:
    card = load_json(path)
    walk(card)

    label = card["decision"]["label"]
    if label != "W1_WAIT":
        fail(f"{path.name}: final_decision must be W1_WAIT, got {label}")
    if label in FORBIDDEN_DECISIONS:
        fail(f"{path.name}: forbidden decision {label}")
    if card["decision"]["ledger_required"] is not True:
        fail(f"{path.name}: ledger_required must be true")
    if card["decision"]["no_betting_commitment"] is not True:
        fail(f"{path.name}: no_betting_commitment must be true")

    reasons = " ".join(card["decision"].get("reasons", []))
    if "confirmed_lineup missing" not in reasons:
        fail(f"{path.name}: reason must contain 'confirmed_lineup missing'")

    for market in ("odds_1X2", "odds_AH", "odds_OU"):
        block = card["markets"][market]
        if block["available"] is not True:
            fail(f"{path.name}: {market} must be available")
        statuses = [line.get("status") for line in block.get("lines", []) if isinstance(line, dict)]
        if "READY" not in statuses:
            fail(f"{path.name}: {market} must contain READY line status")

    if not (card["squad"]["home"]["available"] and card["squad"]["away"]["available"]):
        fail(f"{path.name}: squads must be available")
    if card["context"]["standings"]["status"] != "OK":
        fail(f"{path.name}: standings must be READY/OK")
    if card["context"]["h2h"]["status"] != "OK":
        fail(f"{path.name}: H2H must be READY/OK")
    if card["lineups"]["confirmed_lineup_available"] is not False:
        fail(f"{path.name}: confirmed_lineup must be missing")
    if card["lineups"]["status"] != "MISSING":
        fail(f"{path.name}: lineup status must be MISSING")
    if card["match"]["referee"]["available"] is not False:
        fail(f"{path.name}: referee must be unavailable")

    risk_codes = {flag["code"] for flag in card["risk_flags"]}
    if "CONFIRMED_LINEUP_MISSING" not in risk_codes:
        fail(f"{path.name}: missing CONFIRMED_LINEUP_MISSING risk flag")
    if "REFEREE_WAIT_EVENT" not in risk_codes:
        fail(f"{path.name}: missing REFEREE_WAIT_EVENT risk flag")

    gap_fields = {gap["field"] for gap in card["data_gaps"]}
    if "lineups.confirmed_lineup" not in gap_fields:
        fail(f"{path.name}: missing confirmed lineup data gap")

    assert_no_forbidden_text(path)
    return label


def main() -> int:
    try:
        for path in (SUMMARY, LEDGER, REPORT):
            if not path.is_file():
                fail(f"Missing required artifact: {path.relative_to(ROOT)}")

        summary = load_json(SUMMARY)
        walk(summary)
        if summary.get("matches_found") != EXPECTED_COUNT:
            fail("summary matches_found must be 24")
        if summary.get("cards_created") != EXPECTED_COUNT:
            fail("summary cards_created must be 24")
        if summary["final_decision_distribution"] != {"W1_WAIT": 24, "W1_PLAY": 0, "W1_WATCH": 0, "W1_PASS": 0}:
            fail("summary decision distribution mismatch")
        if summary["lineup"]["status"] != "WAIT_EVENT":
            fail("summary lineup status must be WAIT_EVENT")
        if summary["referee"]["status"] != "WAIT_EVENT":
            fail("summary referee status must be WAIT_EVENT")
        for key in ("odds_1X2", "odds_AH", "odds_OU"):
            if summary[key]["status"] != "READY" or summary[key]["ready"] != EXPECTED_COUNT:
                fail(f"summary {key} must be READY 24/24")

        json_cards = sorted(CARDS_DIR.glob("*.json"))
        md_cards = sorted(CARDS_DIR.glob("*.md"))
        if len(json_cards) != EXPECTED_COUNT:
            fail(f"Expected 24 JSON cards, found {len(json_cards)}")
        if len(md_cards) != EXPECTED_COUNT:
            fail(f"Expected 24 Markdown cards, found {len(md_cards)}")

        distribution = Counter(assert_card(path) for path in json_cards)
        if distribution != Counter({"W1_WAIT": EXPECTED_COUNT}):
            fail(f"Card decision distribution mismatch: {dict(distribution)}")

        for path in md_cards:
            assert_no_forbidden_text(path)
            text = path.read_text(encoding="utf-8")
            if "confirmed_lineup missing" not in text:
                fail(f"{path.name}: markdown must mention confirmed_lineup missing")
            if "Final Decision:** `W1_WAIT`" not in text:
                fail(f"{path.name}: markdown final decision must be W1_WAIT")

        with LEDGER.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != EXPECTED_COUNT:
            fail(f"Expected 24 ledger rows, found {len(rows)}")
        for row in rows:
            if row["final_decision"] != "W1_WAIT":
                fail(f"Ledger row {row['ledger_id']} must be W1_WAIT")
            if row["ledger_required"] != "true":
                fail(f"Ledger row {row['ledger_id']} must set ledger_required=true")
            if "confirmed_lineup missing" not in row["reason"]:
                fail(f"Ledger row {row['ledger_id']} reason must contain confirmed_lineup missing")

        assert_no_forbidden_text(REPORT)
    except CheckError as exc:
        print(f"W1 Round1 initial cards self-test FAIL: {exc}", file=sys.stderr)
        return 1

    print("W1 Round1 initial cards self-test PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
