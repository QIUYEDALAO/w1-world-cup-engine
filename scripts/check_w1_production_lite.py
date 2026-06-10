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
EXPECTED_PLAY_GUARD_VERSION = "W1_PLAY_GUARD_V1"
FORBIDDEN_KEY = "opening_odds"
FORBIDDEN_COMMITMENT_TEXT = ["稳赚", "命中率"]
EXPECTED_PLAY_GUARD_RULES = {
    "risk_flags_count_max_2": ("risk_flags.count", "<=", 2),
    "blocking_data_gaps_zero": ("blocking_data_gaps", "==", 0),
    "odds_snapshot_age_under_60m": ("odds_snapshot_age_minutes", "<", 60),
    "confirmed_lineup_exists": ("confirmed_lineup_exists", "==", True),
    "odds_1X2_overround_under_1_12": ("odds_1X2_overround", "<", 1.12),
    "ah_direction_consistent_with_elo": ("AH_direction_consistent_with_elo", "==", True),
    "supporting_factors_min_2": ("supporting_factors.count", ">=", 2),
    "counter_factors_min_1": ("counter_factors.count", ">=", 1),
    "ledger_required_true": ("ledger_required", "==", True),
}


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


def assert_play_guard_policy(policy: dict[str, Any]) -> None:
    if policy.get("play_guard_version") != EXPECTED_PLAY_GUARD_VERSION:
        fail("Policy must declare W1_PLAY_GUARD_V1")

    guard = policy.get("play_guard_v1")
    if not isinstance(guard, dict):
        fail("Policy must include play_guard_v1")
    if guard.get("applies_to") != "W1_PLAY":
        fail("PLAY_GUARD must apply to W1_PLAY")
    if guard.get("all_required") is not True:
        fail("PLAY_GUARD must require all rules")

    rules = {rule.get("id"): rule for rule in guard.get("rules", [])}
    for rule_id, (field, operator, value) in EXPECTED_PLAY_GUARD_RULES.items():
        rule = rules.get(rule_id)
        if not rule:
            fail(f"Missing PLAY_GUARD rule: {rule_id}")
        if (rule.get("field"), rule.get("operator"), rule.get("value")) != (field, operator, value):
            fail(f"PLAY_GUARD rule mismatch for {rule_id}: {rule}")

    hard_rule_ids = {rule.get("id") for rule in policy.get("hard_rules", [])}
    if "play_guard_v1_required_for_play" not in hard_rule_ids:
        fail("Hard rules must require PLAY_GUARD_V1 for W1_PLAY")


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

    if card["match"]["referee"]["available"] is False:
        require_risk(card, "REFEREE_UNASSIGNED")

    if label == "W1_PLAY" and decision["ledger_required"] is not True:
        fail("W1_PLAY must set ledger_required=true")

    if decision["no_betting_commitment"] is not True:
        fail("Match card must set no_betting_commitment=true")

    reasons = decision.get("reasons")
    if not isinstance(reasons, dict):
        fail("decision.reasons must be an object with supporting/counter factors")
    for key in ("summary", "supporting_factors", "counter_factors"):
        if not isinstance(reasons.get(key), list):
            fail(f"decision.reasons.{key} must be an array")
    if decision.get("play_guard_version") != EXPECTED_PLAY_GUARD_VERSION:
        fail("Sample card must include W1_PLAY_GUARD_V1")

    if not isinstance(card.get("odds_movement"), dict):
        fail("Sample card must include odds_movement")
    if not isinstance(card.get("market_signal"), dict):
        fail("Sample card must include market_signal")
    if len(card["market_signal"].get("supporting_factors", [])) < 2:
        fail("Sample market_signal must include at least two supporting factors")
    if len(card["market_signal"].get("counter_factors", [])) < 1:
        fail("Sample market_signal must include at least one counter factor")


def assert_required_schema_shape(schema: dict[str, Any]) -> None:
    required = schema.get("required", [])
    for key in ("risk_flags", "data_gaps", "decision", "markets", "lineups", "squad", "odds_movement", "market_signal"):
        if key not in required:
            fail(f"Match card schema must require {key}")
    market_required = schema["properties"]["markets"]["required"]
    for key in ("first_seen_odds_proxy", "odds_1X2", "odds_AH", "odds_OU"):
        if key not in market_required:
            fail(f"Markets schema must require {key}")
    decision_required = schema["properties"]["decision"]["required"]
    for key in ("play_guard_version", "reasons"):
        if key not in decision_required:
            fail(f"Decision schema must require {key}")
    reasons_schema = schema["properties"]["decision"]["properties"]["reasons"]
    for key in ("supporting_factors", "counter_factors"):
        if key not in reasons_schema.get("required", []):
            fail(f"Decision reasons schema must require {key}")


def assert_ledger_play_guard_shape(schema: dict[str, Any]) -> None:
    required = schema.get("required", [])
    for key in ("calibration_cycle", "override_reason", "play_guard_version"):
        if key not in required:
            fail(f"Ledger schema must require {key}")
        if key not in schema.get("properties", {}):
            fail(f"Ledger schema must define {key}")
    enum = schema["properties"]["play_guard_version"].get("enum")
    if enum != [EXPECTED_PLAY_GUARD_VERSION]:
        fail("Ledger schema play_guard_version enum mismatch")


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
        assert_play_guard_policy(policy)
        assert_required_schema_shape(match_schema)
        assert_ledger_play_guard_shape(ledger_schema)
        assert_sample_hard_rules(sample)
        assert_docs_boundary()
    except CheckError as exc:
        print(f"W1_PRODUCTION_LITE self-test FAIL: {exc}", file=sys.stderr)
        return 1

    print("W1_PRODUCTION_LITE self-test PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
