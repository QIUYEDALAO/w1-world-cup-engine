#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 Scout AH recommendation policy engine (enforced mode).

This layer turns already-built W1 AH cover probabilities and market prices into
a structured policy_result. It is intentionally read-only: no score-engine,
lambda, probability-model, Primary Read, or DeepSeek behavior is changed here.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import w1_odds_snapshot_store as SNAPSHOTS

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config/w1_recommendation_policy.json"
CALIBRATION_CONFIG = ROOT / "config/w1_calibration_policy.json"
BUNDLES = ROOT / "state/w1_scout_bundles.json"
BUNDLE_SCRIPT = ROOT / "scripts/w1_scout_bundle.py"
CALLS = ROOT / "state/w1_scout_calls.json"

GRADE_ORDER = {"PASS": 0, "B": 1, "B+": 2, "A-": 3, "A": 4}
GRADE_BY_ORDER = {value: key for key, value in GRADE_ORDER.items()}


def load_policy_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    mode = os.environ.get("W1_RECOMMENDATION_POLICY_MODE")
    if mode:
        config["mode"] = mode.strip().lower()
    return config


def load_calibration_config(path: str | Path = CALIBRATION_CONFIG) -> dict[str, Any]:
    if not Path(path).is_file():
        return {
            "schema_version": "w1_calibration_policy_v1",
            "status": "untrained",
            "method": "raw_passthrough",
            "sample_scope": "independent_settled_recommend",
            "thresholds": {
                "global_sigmoid_min_samples": 100,
                "line_family_min_samples": 100,
                "isotonic_min_samples": 100,
            },
            "untrained_behavior": {
                "trained_artifact_loaded": False,
                "reason_cn": "样本量不足，当前仅使用 raw passthrough；不声称已完成校准。",
            },
        }
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _root_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def _load_local_results_for_calibration() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    # Keep this lightweight and read-only so recommendation policy never imports
    # the backtest module. Overlay is later in the list, so it overrides legacy.
    for rel in (
        "data/results/round1_results.json",
        "data/results/world_cup_2026_results.json",
    ):
        path = _root_path(rel)
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for fid, row in (payload.get("results") or {}).items():
            if not isinstance(row, dict):
                continue
            out[str(fid)] = row
            for alias in row.get("alias_fixture_ids", []) or []:
                out[str(alias)] = row
    return out


def independent_settled_recommend_sample_count() -> int:
    bundle_policy_by_fixture: dict[str, dict[str, Any]] = {}
    if BUNDLES.is_file():
        try:
            bundle_payload = json.loads(BUNDLES.read_text(encoding="utf-8"))
            for bundle in bundle_payload.get("bundles") or []:
                if isinstance(bundle, dict) and isinstance(bundle.get("policy_result"), dict):
                    bundle_policy_by_fixture[str(bundle.get("fixture_id") or "")] = bundle["policy_result"]
        except json.JSONDecodeError:
            bundle_policy_by_fixture = {}
    if not CALLS.is_file():
        calls = [{"fixture_id": fid, "policy_result": policy} for fid, policy in bundle_policy_by_fixture.items()]
    else:
        try:
            payload = json.loads(CALLS.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        calls = payload.get("calls") or []
    results = _load_local_results_for_calibration()
    seen: set[str] = set()
    for call in calls:
        if not isinstance(call, dict):
            continue
        fid = str(call.get("fixture_id") or "")
        if not fid or fid in seen or fid not in results:
            continue
        policy = call.get("policy_result") if isinstance(call.get("policy_result"), dict) else bundle_policy_by_fixture.get(fid, {})
        if policy.get("decision_state") == "RECOMMEND":
            score = results.get(fid, {}).get("actual_score")
            if isinstance(score, dict) and score.get("home") is not None and score.get("away") is not None:
                seen.add(fid)
    return len(seen)


def build_calibration_metadata(sample_count: int | None = None) -> dict[str, Any]:
    cfg = load_calibration_config()
    thresholds = cfg.get("thresholds") or {}
    samples = int(independent_settled_recommend_sample_count() if sample_count is None else sample_count)
    global_required = int(thresholds.get("global_sigmoid_min_samples", 100))
    line_required = int(thresholds.get("line_family_min_samples", 100))
    iso_required = int(thresholds.get("isotonic_min_samples", 100))
    readiness = {
        "global_sigmoid": "ready" if samples >= global_required else "insufficient_sample",
        "line_family": "ready" if samples >= line_required else "insufficient_sample",
        "isotonic": "ready" if samples >= iso_required else "insufficient_sample",
    }
    return {
        "status": "untrained",
        "method": "raw_passthrough",
        "sample_scope": str(cfg.get("sample_scope") or "independent_settled_recommend"),
        "independent_settled_recommend_samples": samples,
        "required_for_global_sigmoid": global_required,
        "required_for_line_family": line_required,
        "readiness": readiness,
        "reason": str((cfg.get("untrained_behavior") or {}).get("reason_cn") or "样本量不足，当前仅使用 raw passthrough；不声称已完成校准。"),
        "calibration_artifact": "",
        "trained_artifact_loaded": False,
    }


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
        "candidate_ah_side": "",
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
        "calibration": build_calibration_metadata(),
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
        "snapshots": {
            "snapshots_count": 0,
            "snapshots_source": "missing",
            "snapshots_used": 0,
            "first_stage_id": None,
            "latest_stage_id": None,
            "first_captured_at": None,
            "latest_captured_at": None,
        },
        "movement": {
            "selected_side": "",
            "first_selected_handicap": None,
            "latest_selected_handicap": None,
            "first_selected_price": None,
            "latest_selected_price": None,
            "line_delta": None,
            "price_delta": None,
        },
        "conflict_flags": [],
        "grade_caps_applied": [],
        "reassess_triggers": [],
        "pass_reason": "",
        "observe_reason": "",
        "movement_summary_cn": "",
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


def _downgrade_grade(grade: str, steps: int = 1) -> str:
    return GRADE_BY_ORDER[max(0, GRADE_ORDER.get(grade, 0) - int(steps))]


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


def _selected_values(snapshot: dict[str, Any], side: str) -> tuple[float | None, float | None]:
    if side == "home":
        return _num(snapshot.get("home_handicap")), _num(snapshot.get("home_price"))
    if side == "away":
        return _num(snapshot.get("away_handicap")), _num(snapshot.get("away_price"))
    return None, None


def _snapshot_meta(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "snapshots_count": int(summary.get("snapshots_count") or 0),
        "snapshots_source": summary.get("snapshots_source") or "missing",
        "snapshots_used": int(summary.get("snapshots_used") or 0),
        "first_stage_id": summary.get("first_stage_id"),
        "latest_stage_id": summary.get("latest_stage_id"),
        "first_captured_at": summary.get("first_captured_at"),
        "latest_captured_at": summary.get("latest_captured_at"),
    }


def analyze_movement(bundle: dict[str, Any], selected_side: str, config: dict[str, Any]) -> dict[str, Any]:
    movement_cfg = config.get("movement_policy") or {}
    min_snapshots = int(movement_cfg.get("min_snapshots", 2))
    price_threshold = float(movement_cfg.get("price_move_threshold", 0.04))
    late_stage_ids = set(str(item) for item in movement_cfg.get("late_stage_ids", ["official_1h", "final_30m"]))
    fid = str(bundle.get("fixture_id") or "")
    summary = SNAPSHOTS.summarize_fixture(fid, bundle)
    snapshots = summary.get("snapshots") or []
    flags: list[str] = []
    stale_reason = None
    if len(snapshots) < min_snapshots:
        stale_reason = "valid snapshots fewer than minimum"
    if not selected_side:
        stale_reason = stale_reason or "selected side missing"
    first = snapshots[0] if snapshots else {}
    latest = snapshots[-1] if snapshots else {}
    first_line, first_price = _selected_values(first, selected_side)
    latest_line, latest_price = _selected_values(latest, selected_side)
    if first_line is None or latest_line is None or first_price is None or latest_price is None:
        stale_reason = stale_reason or "selected line/price missing"
    if any(not str((row or {}).get("captured_at") or "").strip() for row in snapshots):
        stale_reason = stale_reason or "captured_at missing"
    if stale_reason:
        flags.append("stale_or_missing_snapshots")
        return {
            "snapshots": _snapshot_meta(summary),
            "movement": {
                "selected_side": selected_side,
                "first_selected_handicap": _round(first_line),
                "latest_selected_handicap": _round(latest_line),
                "first_selected_price": _round(first_price, 3),
                "latest_selected_price": _round(latest_price, 3),
                "line_delta": None if first_line is None or latest_line is None else _round(latest_line - first_line),
                "price_delta": None if first_price is None or latest_price is None else _round(latest_price - first_price, 3),
            },
            "movement_flags": flags,
            "movement_summary_cn": "盘口快照不足，无法验证早盘到临场变化；在未校准状态下，推荐等级最高限制为 B+。",
        }
    line_delta = float(latest_line) - float(first_line)
    price_delta = float(latest_price) - float(first_price)
    if line_delta < 0:
        flags.append("line_moved_against_pick")
    elif line_delta > 0:
        flags.append("line_moved_with_pick")
    if price_delta > price_threshold:
        flags.extend(["price_moved_against_pick", "selected_side_drift"])
    elif price_delta < -price_threshold:
        flags.append("selected_side_steam")

    if len(snapshots) >= 2:
        prev = snapshots[-2]
        prev_line, prev_price = _selected_values(prev, selected_side)
        late_stage = str(latest.get("stage_id") or "") in late_stage_ids or str(prev.get("stage_id") or "") in late_stage_ids
        if prev_line is not None and latest_line is not None and prev_price is not None and latest_price is not None:
            late_line_delta = float(latest_line) - float(prev_line)
            late_price_delta = float(latest_price) - float(prev_price)
            if late_stage and (late_line_delta < 0 or late_price_delta > price_threshold):
                flags.append("reverse_move_late")

    flags = list(dict.fromkeys(flags))
    if "stale_or_missing_snapshots" in flags:
        summary_cn = "盘口快照不足，无法验证早盘到临场变化；在未校准状态下，推荐等级最高限制为 B+。"
    elif not flags or set(flags).issubset({"selected_side_steam", "line_moved_with_pick"}):
        summary_cn = (
            f"盘口快照充足，候选方向 {selected_side or 'unknown'} 未出现退盘；"
            f"盘口变化 {line_delta:+.2f}，水位变化 {price_delta:+.2f}，未触发反向风险。"
        )
    else:
        summary_cn = (
            f"盘口快照显示候选方向出现反向变化：盘口变化 {line_delta:+.2f}，"
            f"水位变化 {price_delta:+.2f}，触发 {', '.join(flags)}。"
        )
    return {
        "snapshots": _snapshot_meta(summary),
        "movement": {
            "selected_side": selected_side,
            "first_selected_handicap": _round(first_line),
            "latest_selected_handicap": _round(latest_line),
            "first_selected_price": _round(first_price, 3),
            "latest_selected_price": _round(latest_price, 3),
            "line_delta": _round(line_delta),
            "price_delta": _round(price_delta, 3),
        },
        "movement_flags": flags,
        "movement_summary_cn": summary_cn,
    }


def apply_movement_policy(grade: str, movement_flags: list[str], config: dict[str, Any]) -> tuple[str, list[str], list[str], str]:
    movement_cfg = config.get("movement_policy") or {}
    caps: list[str] = []
    conflicts: list[str] = []
    observe_reason = ""
    if "reverse_move_late" in movement_flags:
        conflicts.append("reverse_move_late")
        if GRADE_ORDER.get(grade, 0) > GRADE_ORDER["B"]:
            grade = "B"
            caps.append("reverse_move_late_observe")
        observe_reason = "临场盘口出现反向变化，降为观察。"
    adverse_line = "line_moved_against_pick" in movement_flags
    adverse_price = "price_moved_against_pick" in movement_flags
    if adverse_line:
        conflicts.append("line_moved_against_pick")
        steps = int(movement_cfg.get("line_moved_against_pick_downgrade", 1))
        before = grade
        grade = _downgrade_grade(grade, steps)
        if grade != before:
            caps.append("line_moved_against_pick_downgrade")
    if adverse_price:
        conflicts.append("price_moved_against_pick")
        steps = int(movement_cfg.get("price_moved_against_pick_downgrade", 1))
        before = grade
        grade = _downgrade_grade(grade, steps)
        if grade != before:
            caps.append("price_moved_against_pick_downgrade")
    if adverse_line and adverse_price:
        if GRADE_ORDER.get(grade, 0) > GRADE_ORDER["B"]:
            grade = "B"
        caps.append("double_adverse_move_min_observe")
        observe_reason = observe_reason or "盘口和水位同时朝候选方向反向变化，降为观察。"
    return grade, caps, list(dict.fromkeys(conflicts)), observe_reason


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
    candidate_side = str(candidate.get("side") or "")
    movement_info = analyze_movement(bundle, candidate_side, config)
    movement_flags = movement_info["movement_flags"]
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
    movement_caps: list[str] = []
    movement_conflicts: list[str] = []
    movement_observe_reason = ""
    if grade != "PASS":
        grade, movement_caps, movement_conflicts, movement_observe_reason = apply_movement_policy(grade, movement_flags, config)
    if grade != "PASS":
        grade, caps = apply_grade_caps(grade, context, config)
    else:
        caps = []
    decision = map_grade_to_decision_state(grade, failed_info["failed_gates"], config)
    candidate_pick = _pick_text(bundle, candidate_side, candidate.get("handicap"))
    selected_handicap = _round(candidate.get("handicap"))
    selected_price = _round(candidate.get("price"), 3)
    result["recommendation_grade"] = grade
    result["decision_state"] = decision
    result["candidate_ah_pick"] = candidate_pick
    result["candidate_ah_side"] = candidate_side
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
    result["calibration"] = build_calibration_metadata()
    result["hard_gates"] = failed_info["hard_gates"]
    result["failed_gates"] = failed_info["failed_gates"]
    result["gate_severity"] = "hard" if result["failed_gates"] else "none"
    result["movement_flags"] = movement_flags
    result["snapshots"] = movement_info["snapshots"]
    result["movement"] = movement_info["movement"]
    result["movement_summary_cn"] = movement_info["movement_summary_cn"]
    result["conflict_flags"] = movement_conflicts
    result["grade_caps_applied"] = movement_caps + caps
    result["reassess_triggers"] = _clean_list([
        "等待盘口快照后复核退盘/升水" if "stale_or_missing_snapshots" in movement_flags else None,
        "首发确认后复核" if context["lineup_unconfirmed"] else None,
    ])
    if decision == "PASS":
        result["main_ah_pick"] = ""
        result["main_ah_side"] = ""
        if movement_conflicts:
            result["pass_reason"] = "盘口变化触发 PASS：候选方向出现退盘、升水或临场反向变化。"
        else:
            result["pass_reason"] = _pass_reason(result["failed_gates"] or ["edge_below_threshold"])
    elif decision == "OBSERVE":
        result["main_ah_pick"] = ""
        result["observe_reason"] = movement_observe_reason or f"{candidate_pick} 有边际优势但等级为 B，仅观察，不作为强推荐。"
    result["policy_summary_cn"] = (
        f"{decision} / {grade}: {candidate_pick or '无候选主推'}; "
        f"edge={_round(edge)}; calibration={calibration_status}; mode={result['policy_mode']}"
    )
    return result


def _read(call: dict[str, Any]) -> dict[str, Any]:
    return call.get("read") if isinstance(call.get("read"), dict) else {}


def _ah_card(call: dict[str, Any]) -> dict[str, Any]:
    read = _read(call)
    return read.get("asian_handicap_card") if isinstance(read.get("asian_handicap_card"), dict) else {}


def _rec_text(call: dict[str, Any]) -> dict[str, Any]:
    read = _read(call)
    return read.get("recommendation_text") if isinstance(read.get("recommendation_text"), dict) else {}


def visible_text_values(call: dict[str, Any]) -> list[str]:
    read = _read(call)
    out: list[str] = []
    for value in read.values():
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, list):
            out.extend(str(item) for item in value if not isinstance(item, dict))
        elif isinstance(value, dict):
            for nested in value.values():
                if isinstance(nested, str):
                    out.append(nested)
                elif isinstance(nested, list):
                    out.extend(str(item) for item in nested if not isinstance(item, dict))
    out.extend(str(call.get(key) or "") for key in ("honesty_label", "safety_label"))
    return out


def _joined_visible(call: dict[str, Any]) -> str:
    return "\n".join(visible_text_values(call))


def _clean_non_recommend_visible(value: Any) -> Any:
    replacements = (
        ("AI亚盘推荐：", "AI亚盘结论："),
        ("亚盘推荐：", "亚盘结论："),
        ("亚盘主推：", "亚盘结论："),
        ("重点推荐", "重点观察"),
        ("强推", "强判断"),
        ("主推", "方向输出"),
        ("推荐：", "结论："),
    )
    if isinstance(value, str):
        out = value
        for src, dst in replacements:
            out = out.replace(src, dst)
        return out
    if isinstance(value, list):
        return [_clean_non_recommend_visible(item) for item in value]
    if isinstance(value, dict):
        return {key: _clean_non_recommend_visible(item) for key, item in value.items()}
    return value


def policy_consistency_issues(call: dict[str, Any]) -> list[str]:
    policy = call.get("policy_result") if isinstance(call.get("policy_result"), dict) else {}
    if not policy:
        return ["policy_result missing"]
    issues: list[str] = []
    if policy.get("policy_mode") != "enforced":
        issues.append("policy_mode must be enforced")
    decision = str(policy.get("decision_state") or "")
    grade = str(policy.get("recommendation_grade") or "")
    main_pick = str(policy.get("main_ah_pick") or "")
    text = _rec_text(call)
    ah = _ah_card(call)
    joined = _joined_visible(call)
    if policy.get("failed_gates") and policy.get("gate_severity") == "hard" and decision != "PASS":
        issues.append("hard gate failed but decision_state is not PASS")
    if (policy.get("probability") or {}).get("calibration_status") == "untrained" and grade == "A":
        issues.append("untrained policy must not grade A")
    calibration = policy.get("calibration") if isinstance(policy.get("calibration"), dict) else {}
    if not calibration:
        issues.append("calibration metadata missing")
    elif calibration.get("status") != "untrained":
        issues.append("S24 calibration status must remain untrained")
    elif calibration.get("method") != "raw_passthrough":
        issues.append("S24 calibration method must be raw_passthrough")
    elif calibration.get("trained_artifact_loaded") is not False:
        issues.append("S24 must not load trained calibration artifact")
    if calibration and calibration.get("status") != (policy.get("probability") or {}).get("calibration_status"):
        issues.append("probability.calibration_status must match calibration.status")
    if grade == "B" and decision != "OBSERVE":
        issues.append("B grade must be OBSERVE")
    if decision == "RECOMMEND":
        if not main_pick:
            issues.append("RECOMMEND must have main_ah_pick")
        if main_pick and main_pick not in str(text.get("headline_cn") or ""):
            issues.append("RECOMMEND headline must include policy main_ah_pick")
        if grade and grade not in str(text.get("grade_cn") or ""):
            issues.append("RECOMMEND grade text must match policy grade")
        if main_pick and str(ah.get("main_ah_pick_cn") or "") not in {main_pick, f"亚盘主推：{main_pick}"} and main_pick not in str(ah.get("main_ah_pick_cn") or ""):
            issues.append("asian_handicap_card main pick conflicts with policy")
    elif decision in {"OBSERVE", "PASS"}:
        if policy.get("main_ah_pick"):
            issues.append(f"{decision} must not have policy main_ah_pick")
        forbidden = ("主推", "强推", "重点推荐", "AI亚盘推荐：", "推荐：", "A-", "B+", "A｜信心", "A | 信心")
        for token in forbidden:
            if token in joined:
                issues.append(f"{decision} visible text contains forbidden token: {token}")
        if str(ah.get("main_ah_pick_cn") or "") and "PASS" not in str(ah.get("main_ah_pick_cn")) and "观察" not in str(ah.get("main_ah_pick_cn")):
            issues.append(f"{decision} asian_handicap_card must not show main pick")
        if str(ah.get("recommendation_grade") or "") not in {"PASS", "B", "C/观察", "观察"}:
            issues.append(f"{decision} asian_handicap_card grade must not show strong grade")
    else:
        issues.append(f"invalid decision_state: {decision}")
    return issues


def enforce_call_with_policy(call: dict[str, Any], policy_result: dict[str, Any] | None = None) -> dict[str, Any]:
    if policy_result is not None:
        call["policy_result"] = json.loads(json.dumps(policy_result, ensure_ascii=False))
    policy = call.get("policy_result") if isinstance(call.get("policy_result"), dict) else None
    if not policy:
        return call
    call["policy_enforced"] = policy.get("policy_mode") == "enforced"
    read = call.setdefault("read", {})
    if not isinstance(read, dict):
        read = {}
        call["read"] = read
    text = read.setdefault("recommendation_text", {})
    if not isinstance(text, dict):
        text = {}
        read["recommendation_text"] = text
    ah = read.setdefault("asian_handicap_card", {})
    if not isinstance(ah, dict):
        ah = {}
        read["asian_handicap_card"] = ah

    decision = str(policy.get("decision_state") or "PASS")
    grade = str(policy.get("recommendation_grade") or "PASS")
    candidate = str(policy.get("candidate_ah_pick") or "")
    main_pick = str(policy.get("main_ah_pick") or "")
    probability = policy.get("probability") if isinstance(policy.get("probability"), dict) else {}
    edge = probability.get("edge_calibrated")
    market_prob = probability.get("market_prob_fair")

    if decision == "RECOMMEND":
        text["headline_cn"] = f"AI亚盘推荐：{main_pick}"
        text["grade_cn"] = f"{grade}｜信心：中高" if grade in {"A", "A-"} else f"{grade}｜信心：中"
        text.setdefault("core_judgement_cn", policy.get("policy_summary_cn") or f"Policy Engine 允许输出 {main_pick}，edge={edge}，市场公平概率={market_prob}。")
        ah["main_ah_pick_cn"] = main_pick
        ah["recommendation_grade"] = grade
        ah["final_action_cn"] = f"亚盘主推：{main_pick}；若临场条件反向，降级观察。"
    elif decision == "OBSERVE":
        text["headline_cn"] = "AI亚盘结论：观察，不进入强判断"
        text["grade_cn"] = "B｜观察"
        text["core_judgement_cn"] = policy.get("observe_reason") or "Policy Engine 仅允许观察，不允许写成强判断。"
        text["reason_bullets_cn"] = [
            policy.get("observe_reason") or "edge 只达到观察档，不进入强判断。",
            f"候选方向：{candidate or '无'}。",
            "等待盘口快照、首发或水位进一步确认。",
        ]
        text["live_invalidation_cn"] = [
            "若 edge 扩大并通过硬门槛，可重新评估。",
            "若盘口退盘或水位反向，继续降级观察。",
            "若首发关键点缺席，维持观察或 PASS。",
        ]
        ah["main_ah_pick_cn"] = "亚盘结论：PASS / 观察"
        ah["recommendation_grade"] = "B"
        ah["pass_reason_cn"] = policy.get("observe_reason") or ""
        ah["final_action_cn"] = f"观察方向：{candidate or '无'}；不进入强判断。"
    else:
        text["headline_cn"] = "AI亚盘结论：PASS / 观察"
        text["grade_cn"] = "PASS｜观察"
        text["core_judgement_cn"] = policy.get("pass_reason") or "Policy Engine 硬门槛未通过，不允许输出亚盘推荐。"
        text["reason_bullets_cn"] = [
            policy.get("pass_reason") or "Policy Engine 未放行。",
            "当前不形成方向输出。",
            "只保留重新评估条件。",
        ]
        text["live_invalidation_cn"] = [
            "若 AH、价格和 W1覆盖概率补齐，可重新评估。",
            "若 edge 达到 1.5pp 以上并通过硬门槛，可重新评估。",
            "若盘口和水位稳定，再复核。",
        ]
        ah["main_ah_pick_cn"] = "亚盘结论：PASS / 观察"
        ah["recommendation_grade"] = "PASS"
        ah["pass_reason_cn"] = policy.get("pass_reason") or ""
        ah["final_action_cn"] = "亚盘结论：PASS / 观察。"
    if decision in {"OBSERVE", "PASS"}:
        read = _clean_non_recommend_visible(read)
        call["read"] = read
        text = read.setdefault("recommendation_text", {})
    if not isinstance(text.get("reason_bullets_cn"), list) or len(text.get("reason_bullets_cn") or []) < 3:
        text["reason_bullets_cn"] = list(text.get("reason_bullets_cn") or []) + ["Policy Engine 结论优先，AI 只解释不改写。"]
    if not isinstance(text.get("live_invalidation_cn"), list) or len(text.get("live_invalidation_cn") or []) < 3:
        text["live_invalidation_cn"] = list(text.get("live_invalidation_cn") or []) + ["若关键输入变化，重新运行 policy。"]
    return call


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


def _sample_snapshots(kind: str = "stable") -> list[dict[str, Any]]:
    base = [
        {
            "fixture_id": "test",
            "stage_id": "early_24h",
            "captured_at": "2026-06-20T00:00:00Z",
            "home_handicap": -0.5,
            "away_handicap": 0.5,
            "home_price": 2.0,
            "away_price": 1.86,
            "bookmaker_count": 8,
            "source": "self-test",
        },
        {
            "fixture_id": "test",
            "stage_id": "watch_6h",
            "captured_at": "2026-06-20T01:00:00Z",
            "home_handicap": -0.5,
            "away_handicap": 0.5,
            "home_price": 2.05,
            "away_price": 1.80,
            "bookmaker_count": 8,
            "source": "self-test",
        },
    ]
    if kind == "one":
        return base[:1]
    if kind == "line_against":
        base[-1]["home_handicap"] = -0.25
        base[-1]["away_handicap"] = 0.25
    elif kind == "price_against":
        base[-1]["away_price"] = 1.92
    elif kind == "double_against":
        base[-1]["home_handicap"] = -0.25
        base[-1]["away_handicap"] = 0.25
        base[-1]["away_price"] = 1.92
    elif kind == "reverse_late":
        base.append({
            "fixture_id": "test",
            "stage_id": "final_30m",
            "captured_at": "2026-06-20T01:30:00Z",
            "home_handicap": -0.25,
            "away_handicap": 0.25,
            "home_price": 1.9,
            "away_price": 1.98,
            "bookmaker_count": 8,
            "source": "self-test",
        })
    elif kind == "steam":
        base[-1]["away_price"] = 1.76
    elif kind == "line_with":
        base[-1]["home_handicap"] = -0.75
        base[-1]["away_handicap"] = 0.75
    return base


def _sample_bundle(edge: float | None = 0.06, *, missing_ah: bool = False, missing_price: bool = False, missing_score: bool = False, invalid_sign: bool = False, stale: bool = False, lineup_confirmed: bool = True, movement: str = "stable") -> dict[str, Any]:
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
    bundle = {
        "fixture_id": "test",
        "home": "主队",
        "away": "客队",
        "lineup": {"confirmed": lineup_confirmed},
        "market": {"ah": ah},
    }
    if not missing_ah and not stale:
        bundle["odds_snapshots"] = _sample_snapshots(movement)
    elif stale and not missing_ah:
        bundle["odds_snapshots"] = _sample_snapshots("one")
    return bundle


def self_test() -> None:
    cfg = load_policy_config()
    cases = [
        ("recommend_a_minus", _sample_bundle(0.06), "A-", "RECOMMEND"),
        ("a_cap_untrained", _sample_bundle(0.08), "A-", "RECOMMEND"),
        ("stale_cap", _sample_bundle(0.08, stale=True), "B+", "RECOMMEND"),
        ("line_against_downgrade", _sample_bundle(0.06, movement="line_against"), "B+", "RECOMMEND"),
        ("price_against_downgrade", _sample_bundle(0.06, movement="price_against"), "B+", "RECOMMEND"),
        ("double_against_observe", _sample_bundle(0.06, movement="double_against"), "B", "OBSERVE"),
        ("reverse_late_pass", _sample_bundle(0.06, movement="reverse_late"), "PASS", "PASS"),
        ("selected_side_steam_no_upgrade", _sample_bundle(0.04, movement="steam"), "B+", "RECOMMEND"),
        ("line_with_pick_no_upgrade", _sample_bundle(0.04, movement="line_with"), "B+", "RECOMMEND"),
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
        calibration = result.get("calibration") or {}
        _assert(calibration.get("status") == "untrained", f"{name}: calibration must stay untrained")
        _assert(calibration.get("method") == "raw_passthrough", f"{name}: calibration method must be raw_passthrough")
        _assert(calibration.get("trained_artifact_loaded") is False, f"{name}: trained artifact must not load")
        _assert((result.get("probability") or {}).get("cover_prob_calibrated") == (result.get("probability") or {}).get("cover_prob_raw"), f"{name}: cover calibrated must equal raw")
        _assert((result.get("probability") or {}).get("edge_calibrated") == (result.get("probability") or {}).get("edge_raw"), f"{name}: edge calibrated must equal raw")
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
