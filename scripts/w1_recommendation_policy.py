#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 Scout AH recommendation policy engine (shadow mode).

This layer turns already-built W1 AH cover probabilities and market prices into
a structured policy_result. It is intentionally read-only: no score-engine,
lambda, probability-model, Primary Read, or DeepSeek behavior is changed here.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config/w1_recommendation_policy.json"
BUNDLES = ROOT / "state/w1_scout_bundles.json"
BUNDLE_SCRIPT = ROOT / "scripts/w1_scout_bundle.py"

GRADE_ORDER = {"PASS": 0, "B": 1, "B+": 2, "A-": 3, "A": 4}
GRADE_BY_ORDER = {value: key for key, value in GRADE_ORDER.items()}


def load_policy_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _num(value: Any) -> float | None:
    if value in (None, "", [], {}):
        return None
    try:
        out = float(str(value).replace("+", ""))
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _round(value: Any, digits: int = 4) -> float | None:
    number = _num(value)
    return round(number, digits) if number is not None else None


def _clean_list(values: list[str | None]) -> list[str]:
    return [str(value) for value in values if value]


def _empty_result(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy_version": config.get("policy_version", "w1_recommendation_policy_v1"),
        "policy_mode": config.get("mode", "shadow"),
        "decision_state": "PASS",
        "recommendation_grade": "PASS",
        "main_ah_pick": "",
        "candidate_ah_pick": "",
        "main_ah_side": "",
        "market": {
            "home_handicap": None,
            "away_handicap": None,
            "selected_handicap": None,
            "home_price": None,
            "away_price": None,
            "selected_price": None,
        },
        "probability": {
            "cover_prob_raw": None,
            "cover_prob_calibrated": None,
            "market_prob_raw": None,
            "market_prob_fair": None,
            "market_prob_method": (config.get("market_probability") or {}).get("method", "multiplicative"),
            "overround": None,
            "edge_raw": None,
            "edge_calibrated": None,
            "calibration_status": (config.get("calibration") or {}).get("default_status", "untrained"),
        },
        "hard_gates": {
            "has_ah": False,
            "has_price": False,
            "has_score_matrix": False,
            "has_market_fair_prob": False,
            "edge_sufficient": False,
            "ah_sign_valid": False,
            "dirty_data_free": True,
            "score_path_not_conflict": True,
            "no_strong_reverse_movement": True,
        },
        "failed_gates": [],
        "gate_severity": "none",
        "movement_flags": [],
        "conflict_flags": [],
        "grade_caps_applied": [],
        "reassess_triggers": [],
        "pass_reason": "",
        "observe_reason": "",
        "policy_summary_cn": "",
    }


def implied_probs_two_way(home_price: float, away_price: float) -> dict[str, float]:
    # TODO(S21+): Shin / power de-vig are listed in config but intentionally
    # not implemented in S20 shadow mode.
    if home_price <= 1.0 or away_price <= 1.0:
        raise ValueError("two-way prices must be > 1.0")
    raw_home = 1.0 / home_price
    raw_away = 1.0 / away_price
    total = raw_home + raw_away
    if total <= 0:
        raise ValueError("invalid two-way market total")
    return {
        "home_raw": round(raw_home, 4),
        "away_raw": round(raw_away, 4),
        "home_fair": round(raw_home / total, 4),
        "away_fair": round(raw_away / total, 4),
        "overround": round(total - 1.0, 4),
        "method": "multiplicative",
    }


def _ah_market(bundle: dict[str, Any]) -> dict[str, Any]:
    market = bundle.get("market") if isinstance(bundle.get("market"), dict) else {}
    ah = market.get("ah") if isinstance(market.get("ah"), dict) else {}
    line = _num(ah.get("home_handicap", market.get("ah_line")))
    home_price = _num(ah.get("home_price", market.get("ah_home_price")))
    away_price = _num(ah.get("away_price", market.get("ah_away_price")))
    away_line = _num(ah.get("away_handicap"))
    if away_line is None and line is not None:
        away_line = -line
    return {
        "home_handicap": line,
        "away_handicap": away_line,
        "home_price": home_price,
        "away_price": away_price,
        "home_cover_prob": _num(ah.get("home_cover_prob")),
        "away_cover_prob": _num(ah.get("away_cover_prob")),
        "line_movement": ah.get("line_movement"),
        "water_movement": ah.get("water_movement"),
        "odds_updated_at": ah.get("odds_updated_at") or market.get("odds_updated_at"),
        "snapshots_count": _num(ah.get("snapshots_count", market.get("odds_snapshots_count"))),
        "snapshots_source": ah.get("snapshots_source") or market.get("odds_snapshots_source"),
    }


def validate_ah_market(bundle: dict[str, Any]) -> dict[str, Any]:
    ah = _ah_market(bundle)
    has_ah = ah["home_handicap"] is not None and ah["away_handicap"] is not None
    has_price = ah["home_price"] is not None and ah["away_price"] is not None and ah["home_price"] > 1.0 and ah["away_price"] > 1.0
    has_score_matrix = ah["home_cover_prob"] is not None and ah["away_cover_prob"] is not None
    ah_sign_valid = bool(has_ah and ah["home_handicap"] <= 0 and ah["away_handicap"] >= 0)
    dirty_data_free = all(
        value is None or (isinstance(value, (int, float)) and math.isfinite(value))
        for value in (
            ah["home_handicap"],
            ah["away_handicap"],
            ah["home_price"],
            ah["away_price"],
            ah["home_cover_prob"],
            ah["away_cover_prob"],
        )
    )
    return {
        **ah,
        "has_ah": has_ah,
        "has_price": has_price,
        "has_score_matrix": has_score_matrix,
        "ah_sign_valid": ah_sign_valid,
        "dirty_data_free": dirty_data_free,
    }


def compute_cover_edges(bundle: dict[str, Any], market_probs: dict[str, Any]) -> dict[str, Any]:
    ah = _ah_market(bundle)
    home_cover = ah["home_cover_prob"]
    away_cover = ah["away_cover_prob"]
    home_fair = market_probs.get("home_fair")
    away_fair = market_probs.get("away_fair")
    return {
        "home": {
            "side": "home",
            "cover_prob": home_cover,
            "market_prob_raw": market_probs.get("home_raw"),
            "market_prob_fair": home_fair,
            "edge": None if home_cover is None or home_fair is None else round(home_cover - home_fair, 4),
            "handicap": ah["home_handicap"],
            "price": ah["home_price"],
        },
        "away": {
            "side": "away",
            "cover_prob": away_cover,
            "market_prob_raw": market_probs.get("away_raw"),
            "market_prob_fair": away_fair,
            "edge": None if away_cover is None or away_fair is None else round(away_cover - away_fair, 4),
            "handicap": ah["away_handicap"],
            "price": ah["away_price"],
        },
    }


def choose_candidate_side(edge_result: dict[str, Any]) -> dict[str, Any]:
    sides = [edge_result.get("home") or {}, edge_result.get("away") or {}]
    sides = [side for side in sides if isinstance(side.get("edge"), (int, float))]
    if not sides:
        return {"side": "", "edge": None, "cover_prob": None, "market_prob_fair": None, "handicap": None, "price": None}
    return max(sides, key=lambda row: float(row.get("edge") or -999.0))


def _pick_text(bundle: dict[str, Any], side: str, handicap: float | None) -> str:
    if not side or handicap is None:
        return ""
    team = str(bundle.get("home") if side == "home" else bundle.get("away") or "")
    if not team:
        team = "主队" if side == "home" else "客队"
    sign = "+" if handicap > 0 else ""
    return f"{team} {sign}{handicap:g}"


def detect_hard_gates(bundle: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    market_state = validate_ah_market(bundle)
    edge = candidate.get("edge")
    failed: list[str] = []
    if not market_state["has_ah"]:
        failed.append("missing_ah")
    if not market_state["has_price"]:
        failed.append("missing_price")
    if not market_state["has_score_matrix"]:
        failed.append("missing_score_matrix")
    if candidate.get("market_prob_fair") is None:
        failed.append("missing_market_fair_probability")
    if edge is None or float(edge) < 0.015:
        failed.append("edge_below_threshold")
    if not market_state["ah_sign_valid"]:
        failed.append("invalid_ah_sign")
    if not market_state["dirty_data_free"]:
        failed.append("dirty_data")
    return {
        "hard_gates": {
            "has_ah": market_state["has_ah"],
            "has_price": market_state["has_price"],
            "has_score_matrix": market_state["has_score_matrix"],
            "has_market_fair_prob": candidate.get("market_prob_fair") is not None,
            "edge_sufficient": edge is not None and float(edge) >= 0.015,
            "ah_sign_valid": market_state["ah_sign_valid"],
            "dirty_data_free": market_state["dirty_data_free"],
            "score_path_not_conflict": True,
            "no_strong_reverse_movement": True,
        },
        "failed_gates": failed,
    }


def apply_grade_thresholds(edge_pp: float | None, config: dict[str, Any]) -> str:
    if edge_pp is None:
        return "PASS"
    thresholds = config.get("edge_thresholds_pp") or {}
    if edge_pp >= float(thresholds.get("A", 7.0)):
        return "A"
    if edge_pp >= float(thresholds.get("A-", 5.0)):
        return "A-"
    if edge_pp >= float(thresholds.get("B+", 3.0)):
        return "B+"
    if edge_pp >= float(thresholds.get("B", 1.5)):
        return "B"
    return "PASS"


def _cap_grade(grade: str, max_grade: str) -> str:
    return GRADE_BY_ORDER[min(GRADE_ORDER.get(grade, 0), GRADE_ORDER.get(max_grade, 0))]


def apply_grade_caps(grade: str, context: dict[str, Any], config: dict[str, Any]) -> tuple[str, list[str]]:
    caps: list[str] = []
    calibration = config.get("calibration") or {}
    if context.get("calibration_status") == "untrained":
        capped = _cap_grade(grade, str(calibration.get("untrained_max_grade", "A-")))
        if capped != grade:
            caps.append("untrained_max_grade")
        grade = capped
        if "stale_or_missing_snapshots" in (context.get("movement_flags") or []):
            capped = _cap_grade(grade, str(calibration.get("untrained_with_stale_movement_max_grade", "B+")))
            if capped != grade:
                caps.append("untrained_with_stale_movement_max_grade")
            grade = capped
        if context.get("lineup_unconfirmed"):
            capped = _cap_grade(grade, str(calibration.get("untrained_with_lineup_unconfirmed_max_grade", "B+")))
            if capped != grade:
                caps.append("untrained_with_lineup_unconfirmed_max_grade")
            grade = capped
    return grade, caps


def map_grade_to_decision_state(grade: str, failed_gates: list[str], config: dict[str, Any]) -> str:
    if failed_gates or grade == "PASS":
        return "PASS"
    return str((config.get("grade_to_decision_state") or {}).get(grade, "PASS"))


def _pass_reason(failed: list[str]) -> str:
    if "invalid_ah_sign" in failed:
        return "AH 盘口符号异常，主队让球/客队受让方向不可信。"
    if "missing_ah" in failed:
        return "AH 盘口缺失，不形成亚盘推荐。"
    if "missing_price" in failed:
        return "AH 两边价格缺失或非法，不形成亚盘推荐。"
    if "missing_score_matrix" in failed:
        return "W1 score matrix 覆盖概率缺失，不形成亚盘推荐。"
    if "missing_market_fair_probability" in failed:
        return "市场公平概率缺失，不形成亚盘推荐。"
    if "edge_below_threshold" in failed:
        return "两边校准前 edge 均不足 1.5pp，不形成亚盘推荐价值。"
    if "dirty_data" in failed:
        return "输入数据存在异常值，不形成亚盘推荐。"
    return "hard gate 未通过，不形成亚盘推荐。"


def _movement_flags(bundle: dict[str, Any]) -> list[str]:
    ah = _ah_market(bundle)
    if not ah.get("snapshots_count") or float(ah.get("snapshots_count") or 0) <= 0:
        return ["stale_or_missing_snapshots"]
    return []


def build_policy_result(bundle: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_policy_config()
    result = _empty_result(config)
    ah_state = validate_ah_market(bundle)
    result["market"].update({
        "home_handicap": _round(ah_state.get("home_handicap")),
        "away_handicap": _round(ah_state.get("away_handicap")),
        "home_price": _round(ah_state.get("home_price"), 3),
        "away_price": _round(ah_state.get("away_price"), 3),
    })
    market_probs: dict[str, Any] = {}
    if ah_state["has_price"]:
        try:
            market_probs = implied_probs_two_way(float(ah_state["home_price"]), float(ah_state["away_price"]))
        except ValueError:
            market_probs = {}
    edge_result = compute_cover_edges(bundle, market_probs) if market_probs else {}
    candidate = choose_candidate_side(edge_result)
    failed_info = detect_hard_gates(bundle, candidate)
    movement_flags = _movement_flags(bundle)
    calibration_status = str((config.get("calibration") or {}).get("default_status", "untrained"))
    lineup = bundle.get("lineup") if isinstance(bundle.get("lineup"), dict) else {}
    context = {
        "calibration_status": calibration_status,
        "movement_flags": movement_flags,
        "lineup_unconfirmed": lineup.get("confirmed") is not True,
    }
    edge = candidate.get("edge")
    edge_pp = None if edge is None else float(edge) * 100.0
    grade = "PASS" if failed_info["failed_gates"] else apply_grade_thresholds(edge_pp, config)
    if grade != "PASS":
        grade, caps = apply_grade_caps(grade, context, config)
    else:
        caps = []
    decision = map_grade_to_decision_state(grade, failed_info["failed_gates"], config)
    candidate_side = str(candidate.get("side") or "")
    candidate_pick = _pick_text(bundle, candidate_side, candidate.get("handicap"))
    selected_handicap = _round(candidate.get("handicap"))
    selected_price = _round(candidate.get("price"), 3)
    result["recommendation_grade"] = grade
    result["decision_state"] = decision
    result["candidate_ah_pick"] = candidate_pick
    result["main_ah_side"] = candidate_side if decision == "RECOMMEND" else ""
    result["main_ah_pick"] = candidate_pick if decision == "RECOMMEND" else ""
    result["market"].update({
        "selected_handicap": selected_handicap,
        "selected_price": selected_price,
    })
    result["probability"].update({
        "cover_prob_raw": _round(candidate.get("cover_prob")),
        "cover_prob_calibrated": _round(candidate.get("cover_prob")),
        "market_prob_raw": _round(candidate.get("market_prob_raw")),
        "market_prob_fair": _round(candidate.get("market_prob_fair")),
        "market_prob_method": market_probs.get("method") or (config.get("market_probability") or {}).get("method", "multiplicative"),
        "overround": _round(market_probs.get("overround")),
        "edge_raw": _round(edge),
        "edge_calibrated": _round(edge),
        "calibration_status": calibration_status,
    })
    result["hard_gates"] = failed_info["hard_gates"]
    result["failed_gates"] = failed_info["failed_gates"]
    result["gate_severity"] = "hard" if result["failed_gates"] else "none"
    result["movement_flags"] = movement_flags
    result["grade_caps_applied"] = caps
    result["reassess_triggers"] = _clean_list([
        "等待盘口快照后复核退盘/升水" if "stale_or_missing_snapshots" in movement_flags else None,
        "首发确认后复核" if context["lineup_unconfirmed"] else None,
    ])
    if decision == "PASS":
        result["main_ah_pick"] = ""
        result["main_ah_side"] = ""
        result["pass_reason"] = _pass_reason(result["failed_gates"] or ["edge_below_threshold"])
    elif decision == "OBSERVE":
        result["main_ah_pick"] = ""
        result["observe_reason"] = f"{candidate_pick} 有边际优势但等级为 B，仅观察，不作为强推荐。"
    result["policy_summary_cn"] = (
        f"{decision} / {grade}: {candidate_pick or '无候选主推'}; "
        f"edge={_round(edge)}; calibration={calibration_status}; mode={result['policy_mode']}"
    )
    return result


def _load_bundle_by_fixture(fid: str) -> dict[str, Any]:
    if not BUNDLES.is_file():
        import subprocess

        subprocess.check_call([sys.executable, str(BUNDLE_SCRIPT)], cwd=str(ROOT))
    payload = json.loads(BUNDLES.read_text(encoding="utf-8"))
    for row in payload.get("bundles") or []:
        if str(row.get("fixture_id")) == str(fid):
            return row
    raise SystemExit(f"fixture_id not found in bundles: {fid}")


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _sample_bundle(edge: float | None = 0.06, *, missing_ah: bool = False, missing_price: bool = False, missing_score: bool = False, invalid_sign: bool = False, stale: bool = False, lineup_confirmed: bool = True) -> dict[str, Any]:
    home_price = None if missing_price else 2.0
    away_price = None if missing_price else 1.8
    home_handicap = 0.5 if invalid_sign else -0.5
    away_handicap = -0.5 if invalid_sign else 0.5
    fair = implied_probs_two_way(2.0, 1.8)
    away_cover = None if missing_score else round(fair["away_fair"] + (edge or 0.0), 4)
    home_cover = None if missing_score else round(1.0 - away_cover, 4)
    ah = {} if missing_ah else {
        "home_handicap": home_handicap,
        "away_handicap": away_handicap,
        "home_price": home_price,
        "away_price": away_price,
        "home_cover_prob": home_cover,
        "away_cover_prob": away_cover,
        "line_movement": None if stale else "盘口基本稳定",
        "odds_updated_at": None if stale else "2026-06-20T00:00:00Z",
        "snapshots_count": None if stale else 2,
        "snapshots_source": None if stale else "self-test",
    }
    return {
        "fixture_id": "test",
        "home": "主队",
        "away": "客队",
        "lineup": {"confirmed": lineup_confirmed},
        "market": {"ah": ah},
    }


def self_test() -> None:
    cfg = load_policy_config()
    cases = [
        ("recommend_a_minus", _sample_bundle(0.06), "A-", "RECOMMEND"),
        ("a_cap_untrained", _sample_bundle(0.08), "A-", "RECOMMEND"),
        ("stale_cap", _sample_bundle(0.08, stale=True), "B+", "RECOMMEND"),
        ("observe_b", _sample_bundle(0.02), "B", "OBSERVE"),
        ("pass_low_edge", _sample_bundle(0.01), "PASS", "PASS"),
        ("pass_missing_ah", _sample_bundle(0.06, missing_ah=True), "PASS", "PASS"),
        ("pass_missing_price", _sample_bundle(0.06, missing_price=True), "PASS", "PASS"),
        ("pass_missing_score", _sample_bundle(0.06, missing_score=True), "PASS", "PASS"),
        ("pass_invalid_sign", _sample_bundle(0.06, invalid_sign=True), "PASS", "PASS"),
    ]
    for name, bundle, grade, decision in cases:
        result = build_policy_result(bundle, cfg)
        _assert(result["recommendation_grade"] == grade, f"{name}: grade {result['recommendation_grade']} != {grade}")
        _assert(result["decision_state"] == decision, f"{name}: decision {result['decision_state']} != {decision}")
        if decision == "RECOMMEND":
            _assert(bool(result["main_ah_pick"]), f"{name}: recommend must have main pick")
        if decision in {"PASS", "OBSERVE"}:
            _assert(not result["main_ah_pick"], f"{name}: pass/observe must not have main pick")
        if decision == "PASS":
            _assert(bool(result["pass_reason"]), f"{name}: pass must have pass reason")
        if decision == "OBSERVE":
            _assert(bool(result["observe_reason"]), f"{name}: observe must have observe reason")
    print("W1 recommendation policy self-test PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build W1 Scout AH recommendation policy_result.")
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--fixture-id")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    config = load_policy_config(args.config)
    if args.bundle:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    elif args.fixture_id:
        bundle = _load_bundle_by_fixture(str(args.fixture_id))
    else:
        parser.error("--bundle, --fixture-id, or --self-test is required")
    print(json.dumps(build_policy_result(bundle, config), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
