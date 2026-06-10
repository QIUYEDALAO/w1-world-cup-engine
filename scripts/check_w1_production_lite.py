#!/usr/bin/env python3
"""Self-test for W1_PRODUCTION_LITE artifacts.

Uses only the Python standard library so the check is local and dependency-free.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "docs/W1_PRODUCTION_LITE.md",
    "config/w1_match_card_schema.json",
    "config/w1_decision_policy.json",
    "config/w1_ledger_schema.json",
    "examples/w1_match_card_sample.json",
    "examples/w1_match_card_sample.md",
    "scripts/check_w1_production_lite.py",
]

EXPECTED_LABELS = ["W1_PLAY", "W1_WATCH", "W1_WAIT", "W1_PASS"]
FORBIDDEN_KEY = "opening_odds"
FORBIDDEN_COMMITMENT_TEXT = ["稳赚", "命中率"]


class CheckError(Exception):
    pass


def load_json(path: str) -> Any:
    with (ROOT / path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def fail(message: str) -> None:
    raise CheckError(message)


def assert_required_files() -> None:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).is_file()]
    if missing:
        fail(f"Missing required files: {', '.join(missing)}")


def walk_values(value: Any, path: str = "$") -> list[tuple[str, Any]]:
    items = [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            items.extend(walk_values(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            items.extend(walk_values(child, f"{path}[{index}]"))
    return items


def assert_no_forbidden_key(value: Any, allow_policy_terms: bool = False) -> None:
    for path, child in walk_values(value):
        if path.split(".")[-1] == FORBIDDEN_KEY:
            fail(f"Forbidden key found: {path}")
        if allow_policy_terms and path.startswith("$.forbidden_terms"):
            continue
        if isinstance(child, str) and FORBIDDEN_KEY in child and "not official opening odds" not in child:
            fail(f"Forbidden odds wording found at {path}")


def assert_labels(policy: dict[str, Any], match_schema: dict[str, Any], ledger_schema: dict[str, Any]) -> None:
    labels = policy.get("decision_labels")
    if labels != EXPECTED_LABELS:
        fail(f"Decision labels mismatch: {labels}")

    card_labels = match_schema["properties"]["decision"]["properties"]["label"]["enum"]
    ledger_labels = ledger_schema["properties"]["decision_label"]["enum"]
    if card_labels != EXPECTED_LABELS:
        fail(f"Match card schema labels mismatch: {card_labels}")
    if ledger_labels != EXPECTED_LABELS:
        fail(f"Ledger schema labels mismatch: {ledger_labels}")


def require_gap(card: dict[str, Any], field_prefix: str) -> None:
    gaps = card.get("data_gaps", [])
    if not any(str(gap.get("field", "")).startswith(field_prefix) for gap in gaps):
        fail(f"Missing required data_gaps entry for {field_prefix}")


def require_risk(card: dict[str, Any], code: str) -> None:
    flags = card.get("risk_flags", [])
    if not any(flag.get("code") == code for flag in flags):
        fail(f"Missing required risk flag {code}")


def assert_sample_hard_rules(card: dict[str, Any]) -> None:
    decision = card["decision"]
    label = decision["label"]

    if not isinstance(card.get("risk_flags"), list):
        fail("risk_flags must be present as an array")
    if not isinstance(card.get("data_gaps"), list):
        fail("data_gaps must be present as an array")

    if not card["lineups"]["confirmed_lineup_available"]:
        if label != "W1_WAIT":
            fail("Missing confirmed_lineup must force W1_WAIT")
        require_gap(card, "lineups.confirmed_lineup")

    for market_name in ("odds_1X2", "odds_AH", "odds_OU"):
        if not card["markets"][market_name]["available"]:
            if label != "W1_WAIT":
                fail(f"Missing {market_name} must force W1_WAIT")
            require_gap(card, f"markets.{market_name}")

    home_squad = card["squad"]["home"]["available"]
    away_squad = card["squad"]["away"]["available"]
    if not (home_squad and away_squad):
        if label not in ("W1_WAIT", "W1_WATCH"):
            fail("Missing squad must force W1_WAIT or degrade to W1_WATCH")
        require_gap(card, "squad")

    if card["context"]["suspensions"]["status"] == "PARTIAL":
        require_risk(card, "SUSPENSIONS_PARTIAL")

    if card["context"]["travel_distance"]["status"] == "PARTIAL":
        require_risk(card, "TRAVEL_DISTANCE_PARTIAL")

    if label == "W1_PLAY" and decision["ledger_required"] is not True:
        fail("W1_PLAY must set ledger_required=true")

    if decision["no_betting_commitment"] is not True:
        fail("Match card must set no_betting_commitment=true")


def assert_required_schema_shape(schema: dict[str, Any]) -> None:
    required = schema.get("required", [])
    for key in ("risk_flags", "data_gaps", "decision", "markets", "lineups", "squad"):
        if key not in required:
            fail(f"Match card schema must require {key}")
    market_required = schema["properties"]["markets"]["required"]
    for key in ("first_seen_odds_proxy", "odds_1X2", "odds_AH", "odds_OU"):
        if key not in market_required:
            fail(f"Markets schema must require {key}")


def assert_docs_boundary() -> None:
    sample_text = read_text("examples/w1_match_card_sample.json") + "\n" + read_text("examples/w1_match_card_sample.md")
    for term in FORBIDDEN_COMMITMENT_TEXT:
        if term in sample_text:
            fail(f"Forbidden commitment term found: {term}")

    docs = read_text("docs/W1_PRODUCTION_LITE.md")
    for required in ("不接 QQ", "不写 old official/pending", "不改 V3/V4/M1", "不调用外部 API"):
        if required not in docs:
            fail(f"Boundary missing from docs: {required}")


def main() -> int:
    try:
        assert_required_files()
        policy = load_json("config/w1_decision_policy.json")
        match_schema = load_json("config/w1_match_card_schema.json")
        ledger_schema = load_json("config/w1_ledger_schema.json")
        sample = load_json("examples/w1_match_card_sample.json")

        assert_no_forbidden_key(policy, allow_policy_terms=True)
        for document in (match_schema, ledger_schema, sample):
            assert_no_forbidden_key(document)

        assert_labels(policy, match_schema, ledger_schema)
        assert_required_schema_shape(match_schema)
        assert_sample_hard_rules(sample)
        assert_docs_boundary()
    except CheckError as exc:
        print(f"W1_PRODUCTION_LITE self-test FAIL: {exc}", file=sys.stderr)
        return 1

    print("W1_PRODUCTION_LITE self-test PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
