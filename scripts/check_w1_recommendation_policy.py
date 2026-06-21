#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Checker for W1 Scout recommendation policy enforced mode."""
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
SNAPSHOT_STORE = ROOT / "scripts/w1_odds_snapshot_store.py"

sys.path.insert(0, str(ROOT / "scripts"))
import w1_recommendation_policy as W1REC  # noqa: E402

DECISIONS = {"RECOMMEND", "OBSERVE", "PASS"}
GRADES = {"A", "A-", "B+", "B", "PASS"}
GRADE_ORDER = {"PASS": 0, "B": 1, "B+": 2, "A-": 3, "A": 4}


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
    if result.get("policy_mode") != "enforced":
        fail(f"{label}.policy_mode must be enforced")
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
    snapshots = result.get("snapshots")
    if not isinstance(snapshots, dict):
        fail(f"{label}.snapshots must be object")
    for key in ("snapshots_count", "snapshots_source", "snapshots_used", "first_stage_id", "latest_stage_id", "first_captured_at", "latest_captured_at"):
        if key not in snapshots:
            fail(f"{label}.snapshots.{key} missing")
    movement = result.get("movement")
    if not isinstance(movement, dict):
        fail(f"{label}.movement must be object")
    for key in ("selected_side", "first_selected_handicap", "latest_selected_handicap", "first_selected_price", "latest_selected_price", "line_delta", "price_delta"):
        if key not in movement:
            fail(f"{label}.movement.{key} missing")
    flags = result.get("movement_flags")
    if not isinstance(flags, list):
        fail(f"{label}.movement_flags must be list")
    if not str(result.get("movement_summary_cn") or "").strip():
        fail(f"{label}.movement_summary_cn missing")
    cfg = load_json(CONFIG)
    min_snapshots = int((cfg.get("movement_policy") or {}).get("min_snapshots", 2))
    if int(snapshots.get("snapshots_used") or 0) < min_snapshots and "stale_or_missing_snapshots" not in flags:
        fail(f"{label} insufficient snapshots must flag stale_or_missing_snapshots")
    if "stale_or_missing_snapshots" in flags and probability.get("calibration_status") == "untrained" and GRADE_ORDER[grade] > GRADE_ORDER["B+"]:
        fail(f"{label} stale/untrained must cap grade to B+")
    caps = result.get("grade_caps_applied")
    if not isinstance(caps, list):
        fail(f"{label}.grade_caps_applied must be list")
    if "line_moved_against_pick" in flags and not any("line_moved_against_pick" in str(item) for item in caps):
        fail(f"{label} line_moved_against_pick must record downgrade")
    if "price_moved_against_pick" in flags and not any("price_moved_against_pick" in str(item) for item in caps):
        fail(f"{label} price_moved_against_pick must record downgrade")
    if "reverse_move_late" in flags and decision not in {"OBSERVE", "PASS"}:
        fail(f"{label} reverse_move_late must OBSERVE/PASS")
    if decision in {"OBSERVE", "PASS"} and result.get("main_ah_pick"):
        fail(f"{label} OBSERVE/PASS must clear main_ah_pick")
    if any(flag in flags for flag in ("line_moved_against_pick", "price_moved_against_pick", "reverse_move_late")) and decision in {"OBSERVE", "PASS"}:
        reason = str(result.get("observe_reason") or result.get("pass_reason") or "")
        if not any(token in reason for token in ("盘口", "水位", "反向", "退盘", "升水")):
            fail(f"{label} movement-driven OBSERVE/PASS must explain market movement")
    if probability.get("market_prob_fair") is None and decision != "PASS":
        fail(f"{label} missing market_prob_fair outside PASS")
    if probability.get("calibration_status") == "untrained" and grade == "A":
        fail(f"{label} calibration_status=untrained must not produce A")
    calibration = result.get("calibration")
    if not isinstance(calibration, dict):
        fail(f"{label}.calibration must be object")
    for key in (
        "status",
        "method",
        "sample_scope",
        "independent_settled_recommend_samples",
        "required_for_global_sigmoid",
        "required_for_line_family",
        "readiness",
        "reason",
        "calibration_artifact",
        "trained_artifact_loaded",
    ):
        if key not in calibration:
            fail(f"{label}.calibration.{key} missing")
    if calibration.get("status") != probability.get("calibration_status"):
        fail(f"{label}.calibration.status must match probability.calibration_status")
    if calibration.get("status") != "untrained":
        fail(f"{label} S24 must not claim trained calibration")
    if calibration.get("method") != "raw_passthrough":
        fail(f"{label} S24 calibration method must be raw_passthrough")
    if calibration.get("trained_artifact_loaded") is not False:
        fail(f"{label} S24 must not load trained calibration artifact")
    if calibration.get("calibration_artifact"):
        fail(f"{label} S24 must not expose calibration artifact")
    readiness = calibration.get("readiness")
    if not isinstance(readiness, dict):
        fail(f"{label}.calibration.readiness must be object")
    for key in ("global_sigmoid", "line_family", "isotonic"):
        if readiness.get(key) != "insufficient_sample":
            fail(f"{label}.calibration.readiness.{key} must be insufficient_sample")
    if probability.get("calibration_status") == "untrained":
        if probability.get("cover_prob_calibrated") != probability.get("cover_prob_raw"):
            fail(f"{label} untrained cover_prob_calibrated must equal raw")
        if probability.get("edge_calibrated") != probability.get("edge_raw"):
            fail(f"{label} untrained edge_calibrated must equal raw")
    if grade == "B" and decision != "OBSERVE":
        fail(f"{label} B grade must map to OBSERVE")
    if failed and decision != "PASS":
        fail(f"{label} hard gate failure must map to PASS")
    if decision == "RECOMMEND" and not result.get("main_ah_pick"):
        fail(f"{label} RECOMMEND must have main_ah_pick")
    if decision == "RECOMMEND" and not result.get("main_ah_side"):
        fail(f"{label} RECOMMEND must have main_ah_side")
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
    if W1REC.validate_ah_market(W1REC._sample_bundle(0.06, home_handicap=-1.5, away_handicap=1.5)).get("ah_sign_valid") is not True:
        fail("reverse AH symmetry: home favorite -1.5/+1.5 must be valid")
    if W1REC.validate_ah_market(W1REC._sample_bundle(0.06, home_handicap=1.5, away_handicap=-1.5)).get("ah_sign_valid") is not True:
        fail("reverse AH symmetry: away favorite +1.5/-1.5 must be valid")
    if W1REC.validate_ah_market(W1REC._sample_bundle(0.06, home_handicap=0.0, away_handicap=0.0)).get("ah_sign_valid") is not True:
        fail("reverse AH symmetry: level ball 0/0 must be valid")
    for label, home_line, away_line in (
        ("both_positive", 0.5, 0.5),
        ("both_negative", -0.5, -0.5),
        ("asymmetric", 0.5, -1.0),
    ):
        if W1REC.validate_ah_market(W1REC._sample_bundle(0.06, home_handicap=home_line, away_handicap=away_line)).get("ah_sign_valid") is not False:
            fail(f"reverse AH symmetry: {label} must be invalid")
    recommend = W1REC.build_policy_result(W1REC._sample_bundle(0.06), cfg)
    validate_policy_result(recommend, "reverse.recommend")
    a_cap = W1REC.build_policy_result(W1REC._sample_bundle(0.08), cfg)
    if a_cap.get("recommendation_grade") != "A-":
        fail("reverse A cap failed")
    stale = W1REC.build_policy_result(W1REC._sample_bundle(0.08, stale=True), cfg)
    if stale.get("recommendation_grade") != "B+":
        fail("reverse stale cap failed")
    if "stale_or_missing_snapshots" not in stale.get("movement_flags", []):
        fail("reverse stale must flag stale_or_missing_snapshots")
    one = W1REC.build_policy_result(W1REC._sample_bundle(0.08, movement="one"), cfg)
    if "stale_or_missing_snapshots" not in one.get("movement_flags", []) or one.get("recommendation_grade") != "B+":
        fail("reverse one snapshot stale cap failed")
    line_against = W1REC.build_policy_result(W1REC._sample_bundle(0.06, movement="line_against"), cfg)
    if "line_moved_against_pick" not in line_against.get("movement_flags", []) or line_against.get("recommendation_grade") != "B+":
        fail("reverse line moved against downgrade failed")
    price_against = W1REC.build_policy_result(W1REC._sample_bundle(0.06, movement="price_against"), cfg)
    if "price_moved_against_pick" not in price_against.get("movement_flags", []) or price_against.get("recommendation_grade") != "B+":
        fail("reverse price moved against downgrade failed")
    double_against = W1REC.build_policy_result(W1REC._sample_bundle(0.06, movement="double_against"), cfg)
    if double_against.get("decision_state") != "OBSERVE" or "double_adverse_move_min_observe" not in double_against.get("grade_caps_applied", []):
        fail("reverse double adverse OBSERVE failed")
    reverse_late = W1REC.build_policy_result(W1REC._sample_bundle(0.06, movement="reverse_late"), cfg)
    if reverse_late.get("decision_state") not in {"OBSERVE", "PASS"} or "reverse_move_late" not in reverse_late.get("movement_flags", []):
        fail("reverse late move OBSERVE/PASS failed")
    steam = W1REC.build_policy_result(W1REC._sample_bundle(0.04, movement="steam"), cfg)
    if steam.get("recommendation_grade") != "B+" or "selected_side_steam" not in steam.get("movement_flags", []):
        fail("reverse selected side steam must not upgrade")
    line_with = W1REC.build_policy_result(W1REC._sample_bundle(0.04, movement="line_with"), cfg)
    if line_with.get("recommendation_grade") != "B+" or "line_moved_with_pick" not in line_with.get("movement_flags", []):
        fail("reverse line moved with pick must not upgrade")
    observe = W1REC.build_policy_result(W1REC._sample_bundle(0.02), cfg)
    if observe.get("decision_state") != "OBSERVE" or observe.get("main_ah_pick"):
        fail("reverse observe mapping failed")
    for name, bundle in {
        "low_edge": W1REC._sample_bundle(0.01),
        "missing_ah": W1REC._sample_bundle(0.06, missing_ah=True),
        "missing_price": W1REC._sample_bundle(0.06, missing_price=True),
        "missing_score": W1REC._sample_bundle(0.06, missing_score=True),
        "invalid_sign": W1REC._sample_bundle(0.06, invalid_sign=True),
        "invalid_asymmetric": W1REC._sample_bundle(0.06, home_handicap=0.5, away_handicap=-1.0),
    }.items():
        result = W1REC.build_policy_result(bundle, cfg)
        validate_policy_result(result, f"reverse.{name}")
        if result.get("decision_state") != "PASS":
            fail(f"reverse {name} must PASS")


def call_for_policy(policy: dict[str, Any], text_patch: dict[str, Any] | None = None, ah_patch: dict[str, Any] | None = None) -> dict[str, Any]:
    text_patch = text_patch or {}
    ah_patch = ah_patch or {}
    main = policy.get("main_ah_pick") or policy.get("candidate_ah_pick") or "客队 +0.5"
    grade = policy.get("recommendation_grade") or "PASS"
    call = {
        "fixture_id": "X",
        "policy_result": policy,
        "policy_enforced": True,
        "read": {
            "recommendation_text": {
                "headline_cn": f"AI亚盘推荐：{main}" if policy.get("decision_state") == "RECOMMEND" else "AI亚盘结论：PASS / 观察",
                "grade_cn": f"{grade}｜信心：中",
                "core_judgement_cn": "Policy Engine 结论优先，AI 只解释不改写。",
                "reason_bullets_cn": ["Policy Engine 已放行或拦截。", "AI 不改写方向。", "等待临场复核。"],
                "score_recommendation_cn": "主比分：1-0；备选：0-0 / 1-1",
                "ou_aux_cn": "小2.5｜信心：中｜失效：早球",
                "live_invalidation_cn": ["盘口反向则降级。", "早球则失效。", "首发反转则复核。"],
                **text_patch,
            },
            "asian_handicap_card": {
                "main_ah_pick_cn": policy.get("main_ah_pick") or "亚盘结论：PASS / 观察",
                "recommendation_grade": grade,
                **ah_patch,
            },
        },
    }
    if policy.get("decision_state") != "RECOMMEND":
        W1REC.enforce_call_with_policy(call, policy)
    return call


def consistency_reverse_tests() -> None:
    cfg = W1REC.load_policy_config(CONFIG)
    recommend_policy = W1REC.build_policy_result(W1REC._sample_bundle(0.06), cfg)
    pass_policy = W1REC.build_policy_result(W1REC._sample_bundle(0.01), cfg)
    observe_policy = W1REC.build_policy_result(W1REC._sample_bundle(0.02), cfg)
    if W1REC.policy_consistency_issues(call_for_policy(recommend_policy)):
        fail("reverse consistency: clean RECOMMEND should pass")
    bad_pass = call_for_policy(pass_policy)
    bad_pass["read"]["recommendation_text"]["headline_cn"] = "AI亚盘推荐：客队 +0.5"
    if not W1REC.policy_consistency_issues(bad_pass):
        fail("reverse consistency: PASS with recommendation wording must fail")
    bad_observe = call_for_policy(observe_policy)
    bad_observe["read"]["recommendation_text"]["headline_cn"] = "AI亚盘推荐：客队 +0.5"
    if not W1REC.policy_consistency_issues(bad_observe):
        fail("reverse consistency: OBSERVE with recommendation wording must fail")
    bad_direction = call_for_policy(recommend_policy, {"headline_cn": "AI亚盘推荐：主队 -0.5"})
    if not W1REC.policy_consistency_issues(bad_direction):
        fail("reverse consistency: RECOMMEND direction mismatch must fail")
    bad_untrained = dict(recommend_policy)
    bad_untrained["recommendation_grade"] = "A"
    bad_untrained["probability"] = dict(recommend_policy.get("probability") or {}, calibration_status="untrained")
    if not W1REC.policy_consistency_issues(call_for_policy(bad_untrained)):
        fail("reverse consistency: untrained A must fail")
    fake_trained = dict(recommend_policy)
    fake_trained["calibration"] = dict(recommend_policy.get("calibration") or {}, status="trained", method="global_sigmoid", trained_artifact_loaded=True)
    fake_trained["probability"] = dict(recommend_policy.get("probability") or {}, calibration_status="trained")
    if not W1REC.policy_consistency_issues(call_for_policy(fake_trained)):
        fail("reverse consistency: fake trained calibration must fail")
    bad_b = dict(observe_policy, recommendation_grade="B", decision_state="RECOMMEND", main_ah_pick="客队 +0.5", main_ah_side="away")
    if not W1REC.policy_consistency_issues(call_for_policy(bad_b)):
        fail("reverse consistency: B as RECOMMEND must fail")
    bad_hard = dict(recommend_policy, failed_gates=["missing_ah"], gate_severity="hard", decision_state="RECOMMEND")
    if not W1REC.policy_consistency_issues(call_for_policy(bad_hard)):
        fail("reverse consistency: hard gate RECOMMEND must fail")


def main() -> int:
    cfg = load_json(CONFIG)
    if cfg.get("mode") != "enforced":
        fail("config mode must be enforced")
    assert_file_contains(POLICY, [
        "def implied_probs_two_way",
        "_ah_lines_symmetric",
        "def build_policy_result",
        "calibration_status",
        "multiplicative",
        "W1_RECOMMENDATION_POLICY_MODE",
        "enforce_call_with_policy",
        "policy_consistency_issues",
        "analyze_movement",
        "apply_movement_policy",
        "build_calibration_metadata",
    ])
    assert_file_contains(BUNDLE, ["policy_result", "build_policy_result"])
    assert_file_contains(SNAPSHOT_STORE, ["fixture_snapshots", "summarize_fixture", "home_handicap", "away_price"])
    assert_file_contains(MARKET_DEBUG, ["policy_version", "decision_state", "policy_summary_cn", "movement_summary_cn", "home_handicap=", "away_handicap=", "ah_sign_valid="])
    payload = ensure_bundles()
    seen_decisions = set()
    for bundle in payload.get("bundles", []):
        result = bundle.get("policy_result")
        if not isinstance(result, dict):
            fail(f"bundle {bundle.get('fixture_id')} missing policy_result")
        validate_policy_result(result, f"bundle {bundle.get('fixture_id')}.policy_result")
        seen_decisions.add(result.get("decision_state"))
    reverse_tests()
    consistency_reverse_tests()
    subprocess.check_call([sys.executable, str(POLICY), "--self-test"], cwd=str(ROOT))
    print(f"W1 recommendation policy check PASS (bundles={len(payload.get('bundles', []))}, decisions={sorted(seen_decisions)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
