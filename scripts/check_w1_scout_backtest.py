#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Checker for W1 Scout AH settlement backtest framework."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTLEMENT = ROOT / "scripts/w1_ah_settlement.py"
BACKTEST = ROOT / "scripts/w1_scout_backtest.py"
CONFIG = ROOT / "config/w1_backtest_policy.json"

sys.path.insert(0, str(ROOT / "scripts"))
import w1_ah_settlement as AH  # noqa: E402
import w1_scout_backtest as BT  # noqa: E402


def fail(message: str) -> None:
    raise SystemExit(f"W1 scout backtest check FAIL: {message}")


def assert_contains(path: Path, tokens: list[str]) -> None:
    if not path.is_file():
        fail(f"missing {path.relative_to(ROOT)}")
    text = path.read_text(encoding="utf-8")
    for token in tokens:
        if token not in text:
            fail(f"{path.relative_to(ROOT)} missing token {token}")


def check_settlement_cases() -> None:
    cases = [
        ("-0.25 draw half_loss", 0, 0, -0.25, "half_loss"),
        ("+0.25 draw half_win", 0, 0, 0.25, "half_win"),
        ("-0.75 win one half_win", 1, 0, -0.75, "half_win"),
        ("+0.75 lose one half_loss", 0, 1, 0.75, "half_loss"),
        ("zero draw push", 0, 0, 0, "push"),
    ]
    for name, selected, opponent, line, expected in cases:
        got = AH.settle_ah_pick(selected, opponent, line)["settlement_result"]
        if got != expected:
            fail(f"{name}: {got} != {expected}")
    if AH.split_quarter_line(0.75) != [0.5, 1.0]:
        fail("+0.75 split incorrect")
    if AH.split_quarter_line(-0.25) != [-0.5, 0.0]:
        fail("-0.25 split incorrect")


def check_synthetic_summary() -> None:
    config = BT.load_config()
    calls, results = BT.synthetic_calls()
    selected = BT.select_calls(calls, config, all_stages=False)
    if len([call for call in selected if call["fixture_id"] == "A"]) != 1:
        fail("default selection must keep one sample per fixture")
    if next(call for call in selected if call["fixture_id"] == "A")["stage_id"] != "final_30m":
        fail("default selection must prefer final_30m over early_24h")
    summary = BT.summarize([BT.sample_from_call(call, results, config) for call in selected])
    for key in ("total_fixtures", "recommend_samples", "observe_samples", "pass_samples", "settled_recommend_samples", "missing_result_samples", "primary_performance", "groups"):
        if key not in summary:
            fail(f"summary missing {key}")
    for key in ("calibration_readiness", "calibration_status", "calibration_method", "independent_settled_recommend_samples", "calibration_sample_scope"):
        if key not in summary:
            fail(f"summary missing {key}")
    calibration = summary.get("calibration_readiness") or {}
    if calibration.get("status") != "untrained":
        fail("synthetic calibration status must be untrained")
    if calibration.get("method") != "raw_passthrough":
        fail("synthetic calibration method must be raw_passthrough")
    if calibration.get("independent_settled_recommend_samples") != 1:
        fail("synthetic calibration sample count must equal settled RECOMMEND samples")
    readiness = calibration.get("readiness") or {}
    if any(value != "insufficient_sample" for value in readiness.values()):
        fail("synthetic calibration readiness must be insufficient_sample")
    if summary["recommend_samples"] != 1 or summary["observe_samples"] != 1 or summary["pass_samples"] != 1:
        fail("RECOMMEND / OBSERVE / PASS routing failed")
    if summary["primary_performance"]["settled"] != 1:
        fail("OBSERVE/PASS must not enter primary recommendation settlement")
    if BT.summarize([BT.sample_from_call(selected[0], {}, config)])["missing_result_samples"] < 1:
        fail("missing result must not crash and must count as missing")
    if AH.line_bucket(1.18) != "1.25" or AH.side_role(-1) != "favorite" or AH.side_role(1) != "underdog" or AH.side_role(0) != "pickem":
        fail("line bucket / side role check failed")


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if config.get("version") != "w1_backtest_policy_v1":
        fail("config version mismatch")
    assert_contains(SETTLEMENT, ["split_quarter_line", "settle_single_line", "settle_ah_pick", "line_bucket", "side_role"])
    assert_contains(BACKTEST, ["one_sample_per_fixture", "diagnostic_only", "filter_only", "settled_recommend_samples", "missing_result_samples", "SKIP: missing runtime input", "calibration_readiness", "independent_settled_recommend_samples"])
    check_settlement_cases()
    check_synthetic_summary()
    subprocess.check_call([sys.executable, str(SETTLEMENT), "--self-test"], cwd=str(ROOT))
    subprocess.check_call([sys.executable, str(BACKTEST), "--self-test"], cwd=str(ROOT))
    out = subprocess.check_output([sys.executable, str(BACKTEST), "--json"], cwd=str(ROOT), text=True)
    parsed = json.loads(out)
    if "schema_version" not in parsed or "primary_performance" not in parsed or "calibration_readiness" not in parsed:
        fail("json output schema incomplete")
    print("W1 scout backtest check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
