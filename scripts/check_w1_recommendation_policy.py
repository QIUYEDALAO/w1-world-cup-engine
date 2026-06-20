#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Checker for W1 Scout recommendation policy shadow mode."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/w1_recommendation_policy.json"
POLICY = ROOT / "scripts/w1_recommendation_policy.py"
BUNDLE = ROOT / "scripts/w1_scout_bundle.py"
BUNDLES = ROOT / "state/w1_scout_bundles.json"
MARKET_DEBUG = ROOT / "scripts/w1_scout_market_debug.py"

sys.path.insert(0, str(ROOT / "scripts"))
import w1_recommendation_policy as W1REC  # noqa: E402

DECISIONS = {"RECOMMEND", "OBSERVE", "PASS"}
GRADES = {"A", "A-", "B+", "B", "PASS"}


def fail(message: str) -> None:
    raise SystemExit(f"W1 recommendation policy check FAIL: {message}")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_file_contains(path: Path, tokens: list[str]) -> None:
    if not path.is_file():
        fail(f"missing file: {path.relative_to(ROOT)}")
    text = path.read_text(encoding="utf-8")
    for token in tokens:
        if token not in text:
            fail(f"{path.relative_to(ROOT)} missing token {token}")


def validate_policy_result(result: dict[str, Any], label: str = "policy_result") -> None:
    if not isinstance(result, dict):
        fail(f"{label} must be object")
    if result.get("policy_version") != "w1_recommendation_policy_v1":
        fail(f"{label}.policy_version mismatch")
    if result.get("policy_mode") not in {"shadow"}:
        fail(f"{label}.policy_mode invalid")
    decision = result.get("decision_state")
    grade = result.get("recommendation_grade")
    if decision not in DECISIONS:
        fail(f"{label}.decision_state invalid: {decision}")
    if grade not in GRADES:
        fail(f"{label}.recommendation_grade invalid: {grade}")
    probability = result.get("probability")
    if not isinstance(probability, dict):
        fail(f"{label}.probability must be object")
    for key in ("calibration_status", "edge_raw", "edge_calibrated", "market_prob_method"):
        if key not in probability:
            fail(f"{label}.probability.{key} missing")
    hard_gates = result.get("hard_gates")
    if not isinstance(hard_gates, dict):
        fail(f"{label}.hard_gates must be object")
    failed = result.get("failed_gates")
    if not isinstance(failed, list):
        fail(f"{label}.failed_gates must be list")
    if probability.get("market_prob_fair") is None and decision != "PASS":
        fail(f"{label} missing market_prob_fair outside PASS")
    if probability.get("calibration_status") == "untrained" and grade == "A":
        fail(f"{label} calibration_status=untrained must not produce A")
    if grade == "B" and decision != "OBSERVE":
        fail(f"{label} B grade must map to OBSERVE")
    if failed and decision != "PASS":
        fail(f"{label} hard gate failure must map to PASS")
    if decision == "RECOMMEND" and not result.get("main_ah_pick"):
        fail(f"{label} RECOMMEND must have main_ah_pick")
    if decision == "OBSERVE":
        if result.get("main_ah_pick"):
            fail(f"{label} OBSERVE must not have main_ah_pick")
        if not result.get("observe_reason"):
            fail(f"{label} OBSERVE must have observe_reason")
    if decision == "PASS":
        if result.get("main_ah_pick"):
            fail(f"{label} PASS must not have main_ah_pick")
        if not result.get("pass_reason"):
            fail(f"{label} PASS must have pass_reason")


def ensure_bundles() -> dict[str, Any]:
    subprocess.check_call([sys.executable, str(BUNDLE)], cwd=str(ROOT))
    payload = load_json(BUNDLES)
    if not payload.get("bundles"):
        fail("scout bundle output has no bundles")
    return payload


def reverse_tests() -> None:
    cfg = W1REC.load_policy_config(CONFIG)
    recommend = W1REC.build_policy_result(W1REC._sample_bundle(0.06), cfg)
    validate_policy_result(recommend, "reverse.recommend")
    a_cap = W1REC.build_policy_result(W1REC._sample_bundle(0.08), cfg)
    if a_cap.get("recommendation_grade") != "A-":
        fail("reverse A cap failed")
    stale = W1REC.build_policy_result(W1REC._sample_bundle(0.08, stale=True), cfg)
    if stale.get("recommendation_grade") != "B+":
        fail("reverse stale cap failed")
    observe = W1REC.build_policy_result(W1REC._sample_bundle(0.02), cfg)
    if observe.get("decision_state") != "OBSERVE" or observe.get("main_ah_pick"):
        fail("reverse observe mapping failed")
    for name, bundle in {
        "low_edge": W1REC._sample_bundle(0.01),
        "missing_ah": W1REC._sample_bundle(0.06, missing_ah=True),
        "missing_price": W1REC._sample_bundle(0.06, missing_price=True),
        "missing_score": W1REC._sample_bundle(0.06, missing_score=True),
        "invalid_sign": W1REC._sample_bundle(0.06, invalid_sign=True),
    }.items():
        result = W1REC.build_policy_result(bundle, cfg)
        validate_policy_result(result, f"reverse.{name}")
        if result.get("decision_state") != "PASS":
            fail(f"reverse {name} must PASS")


def main() -> int:
    cfg = load_json(CONFIG)
    if cfg.get("mode") != "shadow":
        fail("config mode must be shadow")
    assert_file_contains(POLICY, [
        "def implied_probs_two_way",
        "def build_policy_result",
        "calibration_status",
        "multiplicative",
        "TODO",
    ])
    assert_file_contains(BUNDLE, ["policy_result", "build_policy_result"])
    assert_file_contains(MARKET_DEBUG, ["policy_version", "decision_state", "policy_summary_cn"])
    payload = ensure_bundles()
    seen_decisions = set()
    for bundle in payload.get("bundles", []):
        result = bundle.get("policy_result")
        if not isinstance(result, dict):
            fail(f"bundle {bundle.get('fixture_id')} missing policy_result")
        validate_policy_result(result, f"bundle {bundle.get('fixture_id')}.policy_result")
        seen_decisions.add(result.get("decision_state"))
    reverse_tests()
    subprocess.check_call([sys.executable, str(POLICY), "--self-test"], cwd=str(ROOT))
    print(f"W1 recommendation policy check PASS (bundles={len(payload.get('bundles', []))}, decisions={sorted(seen_decisions)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
