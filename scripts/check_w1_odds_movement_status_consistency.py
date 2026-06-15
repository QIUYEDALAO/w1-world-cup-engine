#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 odds_movement.status consistency checker.

Stage: W1_P0_CONSISTENCY_AND_AUDIT_REFRESH_V1.

Enforces, as a single source of truth shared with build_w1_dashboard_data.py:
  1. status enum membership (canonical set + deprecated THIN_MARKET_SKIP -> WARN).
  2. READY must never appear in odds_movement.status (it is a market_signal value).
  3. status_reason_code must match the explicit allowlist for that status.
  4. status -> play_guard_input / calibration.gate_effect must not contradict the
     shared gate map (resolve_odds_movement_gate).
  5. cascade / dominance priority is explicit:
     HARD_THIN > SOFT_THIN > MARKET_CONFLICT > MARKET_ALERT > MARKET_MOVING > MARKET_STABLE

It does NOT change any gate behavior or thresholds; it only validates them.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# scripts/ is on sys.path[0] when run as `python3 scripts/check_*.py`, so the
# build module's constants/helpers import directly -> code and checker can't drift.
import build_w1_dashboard_data as B

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_JSON = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
BUILD_SRC = ROOT / "scripts/build_w1_dashboard_data.py"
CARDS_DIR = ROOT / "data/processed/match_cards/group_stage_round1"
V1_SCHEMA = "W1_ODDS_MOVEMENT_MONITOR_V1"

EXPECTED_PRIORITY = [
    "HARD_THIN",
    "SOFT_THIN",
    "MARKET_CONFLICT",
    "MARKET_ALERT",
    "MARKET_MOVING",
    "MARKET_STABLE",
]
DEPRECATED_REMOVAL_NOTE = (
    "THIN_MARKET_SKIP is accepted-but-deprecated (alias of HARD_THIN); "
    "planned removal after odds snapshot collection lands."
)

errors: list[str] = []
warnings: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def check_priority_is_explicit() -> None:
    if B.ODDS_MOVEMENT_STATUS_PRIORITY != EXPECTED_PRIORITY:
        fail(
            "ODDS_MOVEMENT_STATUS_PRIORITY mismatch: "
            f"{B.ODDS_MOVEMENT_STATUS_PRIORITY} != {EXPECTED_PRIORITY}"
        )
    if B.ODDS_MOVEMENT_DEPRECATED_STATUS_ALIASES.get("THIN_MARKET_SKIP") != "HARD_THIN":
        fail("THIN_MARKET_SKIP must alias to HARD_THIN in build constants")


def check_cascade_source_order() -> None:
    """Static check: the implemented cascade matches the documented priority."""
    src = BUILD_SRC.read_text(encoding="utf-8")
    # Use the cascade's `status, reason = ...` assignment tuples, which are unique
    # to the cascade (the reason strings also appear in the allowlist constant, so
    # a bare reason-code search would match the constant block instead).
    markers = [
        '"HARD_THIN", "HARD_THIN_NO_1X2"',     # HARD_THIN
        '"SOFT_THIN", "SOFT_THIN_FEW_BOOKS"',  # SOFT_THIN
        '"MARKET_ALERT", "ALERT_FAVORITE_FLIP"',   # MARKET_ALERT
        '"MARKET_MOVING", "MOVING_LINEUP_WINDOW"',  # MARKET_MOVING
    ]
    positions = [src.find(m) for m in markers]
    if any(p < 0 for p in positions):
        fail(f"cascade markers missing in build source: {list(zip(markers, positions))}")
        return
    if positions != sorted(positions):
        fail(f"cascade order does not follow status priority: {list(zip(markers, positions))}")
    for const in ("ODDS_MOVEMENT_STATUS_PRIORITY", "ODDS_MOVEMENT_GATE_MAP", "resolve_odds_movement_gate"):
        if const not in src:
            fail(f"single-source-of-truth symbol missing from build: {const}")


def check_status_value(status, where: str) -> None:
    if status in (None, ""):
        return
    if status == "READY":
        fail(f"{where}: READY must not appear in odds_movement.status (it is a market_signal value)")
        return
    if status not in B.ODDS_MOVEMENT_STATUS_ENUM:
        fail(f"{where}: odds_movement.status '{status}' not in enum {sorted(B.ODDS_MOVEMENT_STATUS_ENUM)}")
        return
    if status in B.ODDS_MOVEMENT_DEPRECATED_STATUS_ALIASES:
        warn(f"{where}: deprecated status '{status}'. {DEPRECATED_REMOVAL_NOTE}")


def check_v1_block(block: dict, where: str) -> None:
    status = block.get("status")
    check_status_value(status, where)
    canonical = B.normalize_odds_movement_status(status) if status else status

    # (3) reason allowlist
    reason = block.get("status_reason_code")
    allowed = B.ODDS_MOVEMENT_REASON_BY_STATUS.get(canonical)
    if allowed is None:
        fail(f"{where}: no reason allowlist for status '{canonical}'")
    elif reason not in allowed:
        fail(f"{where}: status_reason_code '{reason}' not allowed for '{canonical}' (allowed: {sorted(allowed)})")

    # (4) status -> gate must not contradict the shared map
    calibration = block.get("calibration", {}) or {}
    calibrated = calibration.get("calibrated", "none")
    tier = calibration.get("tier", "C")
    hard_movement_gate = calibrated == "full" and tier == "A"
    magnitude = (block.get("cumulative_move", {}) or {}).get("magnitude_overall", "minor")
    expected = B.resolve_odds_movement_gate(
        canonical, hard_movement_gate=hard_movement_gate, magnitude_overall=magnitude
    )
    pgi = block.get("play_guard_input", {}) or {}
    for key in ("recommended_gate", "allow_formal_judgment", "reference_action"):
        if pgi.get(key) != expected[key]:
            fail(f"{where}: play_guard_input.{key}={pgi.get(key)!r} contradicts shared map ({expected[key]!r})")
    if calibration.get("gate_effect") != expected["gate_effect"]:
        fail(f"{where}: calibration.gate_effect={calibration.get('gate_effect')!r} contradicts shared map ({expected['gate_effect']!r})")


def check_dashboard() -> int:
    data = read_json(DASHBOARD_JSON)
    records = data.get("match_records", [])
    checked = 0
    for row in records:
        block = row.get("odds_movement", {}) or {}
        if block.get("schema_version") != V1_SCHEMA:
            continue
        check_v1_block(block, f"dashboard:{row.get('fixture_id')}")
        checked += 1
    return checked


def check_cards() -> int:
    checked = 0
    for path in sorted(CARDS_DIR.glob("*.json")):
        card = read_json(path)
        block = card.get("odds_movement", {}) or {}
        status = block.get("status")
        if status is None:
            continue
        # Cards may carry a legacy (non-V1) odds_movement block; only the status
        # enum / no-READY invariant is enforced there.
        check_status_value(status, f"card:{path.name}")
        if block.get("schema_version") == V1_SCHEMA:
            check_v1_block(block, f"card:{path.name}")
        checked += 1
    return checked


def main() -> int:
    check_priority_is_explicit()
    check_cascade_source_order()
    n_dash = check_dashboard()
    n_cards = check_cards()

    for w in warnings:
        print(f"WARN: {w}")
    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        print(f"W1 odds_movement status consistency check FAIL ({len(errors)} error(s))")
        return 1
    print(
        f"W1 odds_movement status consistency check PASS "
        f"(dashboard_blocks={n_dash}, card_blocks={n_cards}, warnings={len(warnings)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
