#!/usr/bin/env python3
"""Validate W1 odds movement threshold calibration guardrails."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/w1_odds_movement_thresholds.json"
DATA_JSON = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
BUILD = ROOT / "scripts/build_w1_dashboard_data.py"
SCORE_ENGINE = ROOT / "scripts/w1_score_engine.py"
RHO_PROVENANCE = ROOT / "config/w1_rho_provenance.json"
DECISION_POLICY = ROOT / "config/w1_decision_policy.json"

FORBIDDEN = (
    "投注建议",
    "下注",
    "资金建议",
    "稳赚",
    "必胜",
    "保证命中",
    "建议下注",
    "推荐投注",
)


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def assert_no_forbidden(path: Path) -> None:
    text = read(path)
    for term in FORBIDDEN:
        if term in text:
            fail(f"Forbidden wording found in {path.relative_to(ROOT)}: {term}")
    for term in ("stake", "profit", "guaranteed"):
        if re.search(rf"(?<![A-Za-z]){term}(?![A-Za-z])", text, re.I):
            fail(f"Forbidden English wording found in {path.relative_to(ROOT)}: {term}")


def assert_default_thresholds(config: dict) -> None:
    if config.get("schema_version") != "W1_ODDS_MOVEMENT_THRESHOLD_CALIBRATION_V1":
        fail("threshold schema_version mismatch")
    if config.get("calibrated") != "none":
        fail("V1 default must keep calibrated=none")
    if config.get("tier") != "C":
        fail("V1 default must keep tier=C")
    provenance = config.get("provenance", {})
    if provenance.get("source_report") is not None:
        fail("Uncalibrated default must keep source_report=null")
    expected = {
        ("x2_tv", "minor_max"): 0.03,
        ("x2_tv", "major_min"): 0.07,
        ("x2_tv_recent", "minor_max"): 0.03,
        ("x2_tv_recent", "major_min"): 0.05,
        ("ou_mu", "minor_max"): 0.15,
        ("ou_mu", "major_min"): 0.35,
        ("ou_mu_recent", "minor_max"): 0.10,
        ("ou_mu_recent", "major_min"): 0.20,
        ("ou_line_move", "medium_min"): 0.25,
        ("ou_line_move", "major_min"): 0.50,
    }
    thresholds = config.get("thresholds", {})
    for (section, key), value in expected.items():
        got = thresholds.get(section, {}).get(key)
        if got != value:
            fail(f"default threshold mismatch {section}.{key}: {got}")
    liquidity = config.get("liquidity", {})
    if liquidity.get("min_books_1x2") != 3 or liquidity.get("min_books_ou") != 2:
        fail("default min books must be 1X2=3 and OU=2")
    windows = config.get("windows", {})
    if windows.get("lineup_window_start_minutes") != 75 or windows.get("lineup_window_end_minutes") != 45:
        fail("lineup window must default to T-75m ~ T-45m")


def assert_calibrated_provenance(config: dict) -> None:
    calibrated = config.get("calibrated")
    if calibrated == "none":
        return
    provenance = config.get("provenance", {})
    required = (
        "source_report",
        "n_positive",
        "n_negative",
        "auc",
        "major_false_positive_rate",
        "labeler_agreement_kappa",
    )
    for key in required:
        if provenance.get(key) in (None, "", {}):
            fail(f"calibrated={calibrated} missing provenance.{key}")
    if config.get("tier") == "A":
        if int(provenance.get("n_positive", 0)) < 40 or int(provenance.get("n_negative", 0)) < 150:
            fail("Tier A requires n_positive>=40 and n_negative>=150")
        auc = provenance.get("auc", {})
        if min(float(v) for v in auc.values() if v is not None) < 0.65:
            fail("Tier A requires AUC>=0.65")


def assert_play_guard_tier_rules(data: dict) -> None:
    for row in data.get("match_records", []):
        movement = row.get("odds_movement", {})
        status = movement.get("status")
        calibration = movement.get("calibration", {})
        gate = movement.get("play_guard_input", {}).get("recommended_gate")
        effect = calibration.get("gate_effect")
        if status == "THIN_MARKET_SKIP" and gate != "SKIP":
            fail(f"{row.get('fixture_id')}: THIN_MARKET_SKIP must always SKIP")
        if status == "MARKET_MOVING" and effect != "WARN_ONLY":
            fail(f"{row.get('fixture_id')}: MARKET_MOVING must be WARN_ONLY")
        if status in {"MARKET_ALERT", "MARKET_CONFLICT"}:
            if not (calibration.get("tier") == "A" and calibration.get("calibrated") == "full"):
                if effect != "WARN_ONLY":
                    fail(f"{row.get('fixture_id')}: Tier B/C or uncalibrated alert/conflict must be WARN_ONLY")


def assert_no_single_fixture_threshold_logic() -> None:
    build = read(BUILD)
    bad_patterns = (
        r'if\s+fid\s*==',
        r'fixture_id[\'"]?\s*==\s*[\'"]1489',
        r'fixture_id[\'"]?\s*==\s*[\'"]1539',
        r'fixture_id[\'"]?\s*==\s*[\'"]664',
    )
    for pattern in bad_patterns:
        if re.search(pattern, build):
            fail("threshold or monitor logic must not branch on a single fixture_id")
    if "actual_score" in build[build.find("def odds_movement_monitor"):build.find("def status_for_fixture")]:
        fail("odds movement thresholds must not use match results")


def assert_core_unchanged() -> None:
    if "DEFAULT_RHO = -0.057766" not in read(SCORE_ENGINE):
        fail("DEFAULT_RHO changed")
    rho = json.loads(read(RHO_PROVENANCE))
    if rho.get("default_rho") != -0.057766 or rho.get("calibrated") is not True:
        fail("rho provenance changed unexpectedly")
    policy_text = read(DECISION_POLICY)
    if "W1_PLAY_GUARD_V1" not in policy_text:
        fail("PLAY_GUARD missing from decision policy")


def main() -> int:
    try:
        for path in (CONFIG, DATA_JSON, BUILD):
            if not path.is_file():
                fail(f"Missing artifact: {path.relative_to(ROOT)}")
            assert_no_forbidden(path)
        config = json.loads(read(CONFIG))
        data = json.loads(read(DATA_JSON))
        assert_default_thresholds(config)
        assert_calibrated_provenance(config)
        assert_play_guard_tier_rules(data)
        assert_no_single_fixture_threshold_logic()
        assert_core_unchanged()
    except (CheckError, json.JSONDecodeError, ValueError) as exc:
        print(f"W1 odds movement threshold calibration check FAIL: {exc}", file=sys.stderr)
        return 1
    print("W1 odds movement threshold calibration check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
