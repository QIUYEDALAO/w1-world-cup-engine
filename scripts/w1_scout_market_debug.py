#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Debug Scout market inputs without dumping raw API payloads."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import w1_recommendation_policy as W1REC
import w1_scout_backtest as BT
import w1_decision_card as W1CARD


ROOT = Path(__file__).resolve().parents[1]
SCOUT_DIR = ROOT / "data/scout"
BUNDLES = ROOT / "state/w1_scout_bundles.json"
BUNDLE_SCRIPT = ROOT / "scripts/w1_scout_bundle.py"
DASHBOARD_DATA = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
CALLS = ROOT / "state/w1_scout_calls.json"
SCHEDULER_STATUS = ROOT / "state/w1_scout_scheduler_status.json"
SCOUT_LOCK = ROOT / "state/scout_lock.jsonl"
ODDS_RAW = ROOT / "data/odds_snapshots/raw"
STAGE_PRIORITY = {
    "final_30m": 7,
    "official_1h": 6,
    "watch_2h": 5,
    "watch_6h": 4,
    "watch_12h": 3,
    "early_24h": 2,
    "early_48h": 1,
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_bundles() -> None:
    if BUNDLES.is_file():
        return
    subprocess.check_call([sys.executable, str(BUNDLE_SCRIPT)], cwd=str(ROOT))


def bundle_for(fid: str) -> dict[str, Any]:
    ensure_bundles()
    payload = load_json(BUNDLES)
    for row in payload.get("bundles") or []:
        if str(row.get("fixture_id")) == fid:
            return row
    return {}


def fmt(value: Any) -> str:
    if value in (None, "", [], {}):
        return "missing"
    return str(value)


def parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def match_record(fid: str) -> dict[str, Any]:
    payload = load_json(DASHBOARD_DATA)
    for row in payload.get("match_records") or []:
        if str(row.get("fixture_id")) == fid:
            return row
    return {}


def current_stage(rec: dict[str, Any]) -> tuple[str, str, bool]:
    kickoff = parse_dt(rec.get("kickoff_utc") or rec.get("kickoff"))
    if kickoff is None:
        return "unknown", "未知阶段", False
    minutes = (kickoff - datetime.now(timezone.utc)).total_seconds() / 60.0
    if minutes <= 0:
        return "closed", "赛前窗口已关闭", False
    if minutes <= 30:
        return "final_30m", "最终版", True
    if minutes <= 60:
        return "official_1h", "正式判断", True
    if minutes <= 120:
        return "watch_2h", "赛前观察", True
    if minutes <= 360:
        return "watch_6h", "赛前观察", True
    if minutes <= 720:
        return "watch_12h", "赛前观察", True
    if minutes <= 1440:
        return "early_24h", "早盘参考", True
    if minutes <= 2880:
        return "early_48h", "早盘参考", True
    return "not_due", "尚未进入赛前生产窗口", False


def has_state_call(fid: str) -> bool:
    payload = load_json(CALLS)
    return any(str(call.get("fixture_id") or "") == fid and isinstance(call.get("read"), dict) for call in payload.get("calls") or [])


def state_call(fid: str) -> dict[str, Any]:
    payload = load_json(CALLS)
    rows = [call for call in payload.get("calls") or [] if isinstance(call, dict) and str(call.get("fixture_id") or "") == fid]
    if not rows:
        return {}
    def key(call: dict[str, Any]) -> tuple[int, int, str]:
        schema = 1 if str(call.get("schema_version") or "") == "scout_ah_recommendation_v2" else 0
        stage = STAGE_PRIORITY.get(str(call.get("stage_id") or ""), 0)
        generated = str(call.get("generated_at") or "")
        return (schema, stage, generated)
    return sorted(rows, key=key)[-1]


def lock_call(fid: str) -> dict[str, Any]:
    if not SCOUT_LOCK.is_file():
        return {}
    rows: list[dict[str, Any]] = []
    for line in SCOUT_LOCK.read_text(encoding="utf-8").splitlines():
        if fid not in line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("fixture_id") or "") == fid:
            rows.append(row)
    return rows[-1] if rows else {}


def in_scheduler_pending(fid: str) -> bool:
    payload = load_json(SCHEDULER_STATUS)
    rows = payload.get("pending_remaining_preview") or []
    return any(str((row or {}).get("fixture_id") or row) == fid for row in rows)


def pass_reason(bundle: dict[str, Any]) -> str:
    availability = bundle.get("availability") or {}
    market = bundle.get("market") or {}
    ah = market.get("ah") if isinstance(market.get("ah"), dict) else {}
    if availability.get("market_ah") != "available":
        return "AH missing: no real Asian Handicap line/price in Scout market."
    if availability.get("model_1x2") != "available":
        return "W1 matrix missing: model 1X2/score matrix unavailable."
    edge = ah.get("cover_edge")
    if edge is None:
        return "W1 cover missing: AH available but cover calculation did not complete."
    if isinstance(edge, (int, float)) and edge <= 0:
        return "No cover edge: model cover edge <= 0."
    return "Actionable AH read possible: positive cover edge present; still research-only."


def policy_result(bundle: dict[str, Any]) -> dict[str, Any]:
    try:
        return W1REC.build_policy_result(bundle)
    except Exception:
        result = bundle.get("policy_result")
        return result if isinstance(result, dict) else {}


def odds_snapshots_for_fixture(fid: str) -> tuple[int, str]:
    market = (bundle_for(fid).get("market") or {})
    ah = market.get("ah") if isinstance(market.get("ah"), dict) else {}
    count = ah.get("snapshots_count", market.get("odds_snapshots_count"))
    source = ah.get("snapshots_source") or market.get("odds_snapshots_source")
    if isinstance(count, int) and count > 0:
        return count, str(source or "bundle")
    matched = 0
    sources: set[str] = set()
    if ODDS_RAW.is_dir():
        for path in sorted(ODDS_RAW.glob("*/*.jsonl")):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines:
                if fid not in line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ids = {str(row.get("fixture_id") or ""), str(row.get("local_card_id") or "")}
                ids.update(str(item) for item in (row.get("alias_fixture_ids") or []))
                if fid not in ids:
                    continue
                matched += 1
                sources.add(str(path.relative_to(ROOT)))
    return matched, ",".join(sorted(sources)) if sources else "missing"


def consistency_for_fixture(fid: str, bundle: dict[str, Any], policy: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    call = state_call(fid)
    if not call:
        call = {"fixture_id": fid, "policy_result": policy, "read": {"recommendation_text": {}, "asian_handicap_card": {}}}
    else:
        call = json.loads(json.dumps(call, ensure_ascii=False))
        call["policy_result"] = policy
    W1REC.enforce_call_with_policy(call, policy)
    issues = W1REC.policy_consistency_issues(call)
    visible_conflicts = [item for item in issues if "visible text" in item or "headline" in item or "grade text" in item]
    return ("PASS" if not issues else "FAIL", issues, visible_conflicts)


def settlement_preview(fid: str) -> str:
    try:
        config = BT.load_config()
        results = BT.load_results(config)
        bundle = bundle_for(fid)
        call = state_call(fid) or {"fixture_id": fid, "stage_id": "", "policy_result": policy_result(bundle), "read": {}}
        call = BT.normalize_call(call, bundle)
        sample = BT.sample_from_call(call, results, config)
    except Exception as exc:  # debug-only path; never fail market debug on runtime gaps
        return f"SKIP: {exc}"
    if sample.get("settlement_value") is None:
        return f"SKIP: {sample.get('missing_result_reason') or 'not a settled RECOMMEND sample'}"
    score = sample.get("final_score") or {}
    return (
        f"final_score={score.get('home')}-{score.get('away')} "
        f"selected_side={sample.get('selected_side')} "
        f"selected_handicap={sample.get('selected_handicap')} "
        f"settlement_result={sample.get('settlement_result')} "
        f"settlement_value={sample.get('settlement_value')}"
    )


def dashboard_card_type(policy: dict[str, Any]) -> str:
    decision = str(policy.get("decision_state") or "PASS")
    if decision == "RECOMMEND":
        return "RECOMMEND_CARD"
    if decision == "OBSERVE":
        return "OBSERVE_CARD"
    return "PASS_CARD"


def dashboard_left_status_label(policy: dict[str, Any]) -> str:
    decision = str(policy.get("decision_state") or "")
    if decision == "RECOMMEND":
        return "已有AI推荐"
    if decision == "OBSERVE":
        return "AI观察"
    if decision == "PASS":
        return "AI PASS"
    return "待生成"


def dashboard_card_title(policy: dict[str, Any]) -> str:
    decision = str(policy.get("decision_state") or "PASS")
    if decision == "RECOMMEND":
        return "AI亚盘决策卡 · RECOMMEND"
    if decision == "OBSERVE":
        return "AI亚盘决策卡 · OBSERVE"
    return "AI亚盘决策卡 · PASS"


def dashboard_pass_reason_source(policy: dict[str, Any]) -> str:
    if policy.get("pass_reason"):
        return "policy_result.pass_reason"
    if policy.get("failed_gates"):
        return "policy_result.failed_gates"
    if policy.get("gate_severity") and policy.get("gate_severity") != "none":
        return "policy_result.gate_severity"
    if policy.get("conflict_flags"):
        return "policy_result.conflict_flags"
    if policy.get("movement_flags"):
        return "policy_result.movement_flags"
    calibration = policy.get("calibration") if isinstance(policy.get("calibration"), dict) else {}
    if calibration.get("reason"):
        return "policy_result.calibration.reason"
    probability = policy.get("probability") if isinstance(policy.get("probability"), dict) else {}
    if probability.get("edge_raw") is not None or probability.get("edge_calibrated") is not None:
        return "policy_result.probability.edge"
    return "policy_fallback"


def dashboard_contains_forbidden_recommend_words(policy: dict[str, Any]) -> bool:
    decision = str(policy.get("decision_state") or "PASS")
    if decision == "RECOMMEND":
        return False
    forbidden = ("亚盘推荐：", "AI亚盘推荐：", "主推：", "重点推荐", "强推", "A-", "B+")
    title = dashboard_card_title(policy)
    if any(token in title for token in forbidden):
        return True
    if decision == "PASS":
        candidate = str(policy.get("candidate_ah_pick") or "")
        pass_line = f"候选方向 / 参考方向：{candidate}，但仅观察" if candidate else "候选方向 / 参考方向：无正式方向，仅观察"
        return any(token in pass_line for token in forbidden)
    if decision == "OBSERVE":
        candidate = str(policy.get("candidate_ah_pick") or "")
        observe_line = f"候选方向：{candidate}" if candidate else "候选方向待确认"
        return any(token in observe_line for token in forbidden)
    return False


def decision_card_contains_forbidden_words(card: dict[str, Any]) -> bool:
    decision = str(card.get("decision_state") or "PASS")
    if decision == "RECOMMEND":
        return False
    forbidden = ("亚盘推荐：", "AI亚盘推荐：", "主推：", "重点推荐", "强推", "A-", "B+")
    text = json.dumps(card, ensure_ascii=False)
    return any(token in text for token in forbidden)


def pass_root_cause(policy: dict[str, Any]) -> str:
    decision = str(policy.get("decision_state") or "PASS")
    if decision != "PASS":
        return "not_applicable"
    failed = policy.get("failed_gates") if isinstance(policy.get("failed_gates"), list) else []
    for gate in (
        "missing_ah",
        "missing_price",
        "missing_score_matrix",
        "missing_market_fair_probability",
        "edge_below_threshold",
        "invalid_ah_sign",
        "dirty_data",
    ):
        if gate in failed:
            return gate
    if failed:
        return str(failed[0])
    return "failed_gates_empty"


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Scout market summary for one fixture.")
    parser.add_argument("--fixture-id", required=True)
    args = parser.parse_args()
    fid = str(args.fixture_id)
    scout_path = SCOUT_DIR / f"{fid}.json"
    scout = load_json(scout_path)
    bundle = bundle_for(fid)
    market = bundle.get("market") or {}
    availability = bundle.get("availability") or {}
    ah = market.get("ah") if isinstance(market.get("ah"), dict) else {}
    ou = market.get("ou") if isinstance(market.get("ou"), dict) else {}
    one_x_two = market.get("one_x_two") if isinstance(market.get("one_x_two"), dict) else {}
    policy = policy_result(bundle)
    state = state_call(fid) or {}
    decision_card = W1CARD.build_decision_card({**state, "fixture_id": fid, "policy_result": policy})
    probability = policy.get("probability") if isinstance(policy.get("probability"), dict) else {}
    calibration = policy.get("calibration") if isinstance(policy.get("calibration"), dict) else {}
    snapshots = policy.get("snapshots") if isinstance(policy.get("snapshots"), dict) else {}
    movement = policy.get("movement") if isinstance(policy.get("movement"), dict) else {}
    market_data_status = policy.get("market_data_status") if isinstance(policy.get("market_data_status"), dict) else {}
    movement_history_status = policy.get("movement_history_status") if isinstance(policy.get("movement_history_status"), dict) else {}
    snapshots_count, snapshots_source = odds_snapshots_for_fixture(fid)
    snapshots_count = int(snapshots.get("snapshots_count") or snapshots_count or 0)
    snapshots_source = str(snapshots.get("snapshots_source") or snapshots_source or "missing")
    consistency, conflict_flags, visible_conflicts = consistency_for_fixture(fid, bundle, policy)

    rec = match_record(fid)
    lock = lock_call(fid)
    lock_inner = lock.get("call") if isinstance(lock.get("call"), dict) else {}
    lock_policy = lock_inner.get("policy_result") if isinstance(lock_inner.get("policy_result"), dict) else {}
    stale_lock_override = bool(
        lock
        and lock_policy
        and lock_policy.get("decision_state") != policy.get("decision_state")
    )
    stage_id, stage_label, due = current_stage(rec)
    has_call = has_state_call(fid)
    pending = in_scheduler_pending(fid)
    reason = "has scout call" if has_call else "pending in scheduler queue" if pending else "not due or not generated yet" if due else stage_label

    print(f"fixture_id={fid}")
    print(f"match={fmt(rec.get('match'))}")
    print(f"current_stage={stage_id} label={stage_label} due={due}")
    print(f"has_state_scout_call={has_call}")
    print(f"in_scheduler_pending_remaining={pending}")
    print(f"scout_file_exists={scout_path.is_file()}")
    print(f"scout_market_source={fmt((scout.get('market') or {}).get('market_source')) if scout else 'missing'}")
    print(f"availability.market_1x2={fmt(availability.get('market_1x2'))}")
    print(f"availability.market_ah={fmt(availability.get('market_ah'))}")
    print(f"availability.market_ou={fmt(availability.get('market_ou'))}")
    print(f"availability.model_1x2={fmt(availability.get('model_1x2'))}")
    score_distribution = rec.get("score_distribution") if isinstance(rec.get("score_distribution"), dict) else {}
    score_summary = rec.get("score_matrix_summary") if isinstance(rec.get("score_matrix_summary"), dict) else {}
    market_panel = rec.get("market_probability_panel") if isinstance(rec.get("market_probability_panel"), dict) else {}
    comparison = market_panel.get("market_comparison") if isinstance(market_panel.get("market_comparison"), dict) else {}
    print(f"dashboard_score_distribution_status={fmt(score_distribution.get('status'))}")
    print(f"dashboard_score_matrix_status={fmt(score_summary.get('status'))}")
    print(f"dashboard_score_matrix_market_source={fmt(score_summary.get('market_source'))}")
    print(f"dashboard_local_market_overlay_source={fmt(score_summary.get('local_market_overlay_source') or score_distribution.get('market_input_overlay_source') or comparison.get('local_market_overlay_source'))}")
    print(f"dashboard_local_market_overlay_fields={json.dumps(score_summary.get('local_market_overlay_fields') or score_distribution.get('market_input_overlay_fields') or comparison.get('local_market_overlay_fields') or [], ensure_ascii=False)}")
    print(f"1x2={fmt(one_x_two.get('p_home'))}/{fmt(one_x_two.get('p_draw'))}/{fmt(one_x_two.get('p_away'))}")
    print(f"ah_line={fmt(ah.get('home_handicap'))} home_price={fmt(ah.get('home_price'))} away_price={fmt(ah.get('away_price'))}")
    print(f"ou_line={fmt(ou.get('line'))} over={fmt(ou.get('over_price'))} under={fmt(ou.get('under_price'))}")
    print(f"cover_probability_model={fmt(ah.get('cover_probability_model'))}")
    print(f"cover_probability_market={fmt(ah.get('cover_probability_market'))}")
    print(f"cover_edge={fmt(ah.get('cover_edge'))}")
    print("MARKET_DATA_STATUS")
    print(f"has_current_ah={fmt(market_data_status.get('has_current_ah'))}")
    print(f"has_current_ou={fmt(market_data_status.get('has_current_ou'))}")
    print(f"has_current_1x2={fmt(market_data_status.get('has_current_1x2'))}")
    print(f"market_data_source={fmt(market_data_status.get('market_data_source'))}")
    print(f"bookmaker_count={fmt(market_data_status.get('bookmaker_count'))}")
    print("MOVEMENT_HISTORY_STATUS")
    print(f"has_movement_history={fmt(movement_history_status.get('has_movement_history'))}")
    print(f"snapshots_count={fmt(movement_history_status.get('snapshots_count'))}")
    print(f"snapshots_used={fmt(movement_history_status.get('snapshots_used'))}")
    print(f"snapshots_source={fmt(movement_history_status.get('snapshots_source'))}")
    print(f"snapshot_type={fmt(movement_history_status.get('snapshot_type'))}")
    print(f"movement_history_status={fmt(movement_history_status.get('movement_history_status'))}")
    print(f"movement_history_reason={fmt(movement_history_status.get('reason'))}")
    print(f"snapshots_count={snapshots_count}")
    print(f"snapshots_source={snapshots_source}")
    print(f"snapshots_used={fmt(snapshots.get('snapshots_used'))}")
    print(f"first_stage_id={fmt(snapshots.get('first_stage_id'))}")
    print(f"latest_stage_id={fmt(snapshots.get('latest_stage_id'))}")
    print(f"first_captured_at={fmt(snapshots.get('first_captured_at'))}")
    print(f"latest_captured_at={fmt(snapshots.get('latest_captured_at'))}")
    print(f"first_selected_handicap={fmt(movement.get('first_selected_handicap'))}")
    print(f"latest_selected_handicap={fmt(movement.get('latest_selected_handicap'))}")
    print(f"line_delta={fmt(movement.get('line_delta'))}")
    print(f"first_selected_price={fmt(movement.get('first_selected_price'))}")
    print(f"latest_selected_price={fmt(movement.get('latest_selected_price'))}")
    print(f"price_delta={fmt(movement.get('price_delta'))}")
    print(f"policy_version={fmt(policy.get('policy_version'))}")
    print(f"policy_mode={fmt(policy.get('policy_mode'))}")
    print(f"policy_enforced={policy.get('policy_mode') == 'enforced'}")
    print(f"decision_state={fmt(policy.get('decision_state'))}")
    print(f"recommendation_grade={fmt(policy.get('recommendation_grade'))}")
    print(f"candidate_ah_pick={fmt(policy.get('candidate_ah_pick'))}")
    print(f"main_ah_pick={fmt(policy.get('main_ah_pick'))}")
    print(f"calibration_status={fmt(probability.get('calibration_status'))}")
    print(f"calibration.status={fmt(calibration.get('status'))}")
    print(f"calibration.method={fmt(calibration.get('method'))}")
    print(f"calibration.sample_scope={fmt(calibration.get('sample_scope'))}")
    print(f"calibration.independent_settled_recommend_samples={fmt(calibration.get('independent_settled_recommend_samples'))}")
    print(f"calibration.required_for_global_sigmoid={fmt(calibration.get('required_for_global_sigmoid'))}")
    print(f"calibration.required_for_line_family={fmt(calibration.get('required_for_line_family'))}")
    print(f"calibration.readiness={json.dumps(calibration.get('readiness') or {}, ensure_ascii=False, sort_keys=True)}")
    print(f"calibration.reason={fmt(calibration.get('reason'))}")
    print(f"calibration.calibration_artifact={fmt(calibration.get('calibration_artifact'))}")
    print(f"calibration.trained_artifact_loaded={fmt(calibration.get('trained_artifact_loaded'))}")
    print(f"edge_raw={fmt(probability.get('edge_raw'))}")
    print(f"edge_calibrated={fmt(probability.get('edge_calibrated'))}")
    print(f"market_prob_method={fmt(probability.get('market_prob_method'))}")
    print(f"market_prob_fair={fmt(probability.get('market_prob_fair'))}")
    print(f"overround={fmt(probability.get('overround'))}")
    print(f"hard_gates={json.dumps(policy.get('hard_gates') or {}, ensure_ascii=False, sort_keys=True)}")
    print(f"failed_gates={json.dumps(policy.get('failed_gates') or [], ensure_ascii=False)}")
    print(f"movement_flags={json.dumps(policy.get('movement_flags') or [], ensure_ascii=False)}")
    print(f"conflict_flags={json.dumps(policy.get('conflict_flags') or [], ensure_ascii=False)}")
    print(f"grade_caps_applied={json.dumps(policy.get('grade_caps_applied') or [], ensure_ascii=False)}")
    print(f"movement_summary_cn={fmt(policy.get('movement_summary_cn'))}")
    print(f"final_decision_state={fmt(policy.get('decision_state'))}")
    print(f"final_recommendation_grade={fmt(policy.get('recommendation_grade'))}")
    print(f"pass_reason={fmt(policy.get('pass_reason'))}")
    print(f"observe_reason={fmt(policy.get('observe_reason'))}")
    print(f"policy_summary_cn={fmt(policy.get('policy_summary_cn'))}")
    card_type = decision_card.get("card_type") or dashboard_card_type(policy)
    show_main = bool(policy.get("decision_state") == "RECOMMEND" and policy.get("main_ah_pick"))
    show_candidate = bool(policy.get("decision_state") in {"OBSERVE", "PASS"} and policy.get("candidate_ah_pick"))
    print(f"dashboard_display_mode=decision_card_first")
    print(f"dashboard_card_type={card_type}")
    print(f"dashboard_decision_card_headline={fmt(decision_card.get('headline_cn'))}")
    print(f"dashboard_decision_card_grade={fmt(decision_card.get('recommendation_grade'))}")
    print(f"dashboard_decision_card_main_pick={fmt(decision_card.get('main_pick_cn'))}")
    print(f"dashboard_left_status_label={dashboard_left_status_label(policy)}")
    print(f"dashboard_card_title={dashboard_card_title(policy)}")
    print(f"dashboard_pass_reason_source={dashboard_pass_reason_source(policy)}")
    print(f"dashboard_contains_forbidden_recommend_words={str(decision_card_contains_forbidden_words(decision_card)).lower()}")
    print(f"dashboard_would_show_main_pick={str(show_main).lower()}")
    print(f"dashboard_would_show_candidate_only={str(show_candidate).lower()}")
    print("PASS_ROOT_CAUSE_AUDIT")
    print(f"audit.fixture_id={fid}")
    print(f"audit.decision_state={fmt(policy.get('decision_state'))}")
    print(f"audit.pass_root_cause={pass_root_cause(policy)}")
    print(f"audit.has_ah={fmt((policy.get('hard_gates') or {}).get('has_ah'))}")
    print(f"audit.has_market_fair_prob={fmt((policy.get('hard_gates') or {}).get('has_market_fair_prob'))}")
    print(f"audit.has_score_matrix={fmt((policy.get('hard_gates') or {}).get('has_score_matrix'))}")
    print(f"audit.failed_gates={json.dumps(policy.get('failed_gates') or [], ensure_ascii=False)}")
    print(f"audit.dashboard_selected_call_generated_at={fmt(state.get('generated_at'))}")
    print(f"audit.dashboard_selected_call_stage_id={fmt(state.get('stage_id'))}")
    print("audit.decision_card_source=policy_result")
    print(f"audit.stale_lock_override={str(stale_lock_override).lower()}")
    print(f"ai_policy_consistency={consistency}")
    print(f"ai_conflict_flags={json.dumps(conflict_flags, ensure_ascii=False)}")
    print(f"visible_text_policy_conflicts={json.dumps(visible_conflicts, ensure_ascii=False)}")
    print(f"settlement_preview={settlement_preview(fid)}")
    print(f"legacy_pass_reason={pass_reason(bundle)}")
    print(f"missing_recommendation_reason={reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
