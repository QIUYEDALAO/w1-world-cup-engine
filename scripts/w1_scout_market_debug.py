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


ROOT = Path(__file__).resolve().parents[1]
SCOUT_DIR = ROOT / "data/scout"
BUNDLES = ROOT / "state/w1_scout_bundles.json"
BUNDLE_SCRIPT = ROOT / "scripts/w1_scout_bundle.py"
DASHBOARD_DATA = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
CALLS = ROOT / "state/w1_scout_calls.json"
SCHEDULER_STATUS = ROOT / "state/w1_scout_scheduler_status.json"
ODDS_RAW = ROOT / "data/odds_snapshots/raw"


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
    for call in payload.get("calls") or []:
        if str(call.get("fixture_id") or "") == fid and isinstance(call, dict):
            return call
    return {}


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
    result = bundle.get("policy_result")
    if isinstance(result, dict):
        return result
    try:
        return W1REC.build_policy_result(bundle)
    except Exception:
        return {}


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
    probability = policy.get("probability") if isinstance(policy.get("probability"), dict) else {}
    snapshots_count, snapshots_source = odds_snapshots_for_fixture(fid)
    consistency, conflict_flags, visible_conflicts = consistency_for_fixture(fid, bundle, policy)

    rec = match_record(fid)
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
    print(f"1x2={fmt(one_x_two.get('p_home'))}/{fmt(one_x_two.get('p_draw'))}/{fmt(one_x_two.get('p_away'))}")
    print(f"ah_line={fmt(ah.get('home_handicap'))} home_price={fmt(ah.get('home_price'))} away_price={fmt(ah.get('away_price'))}")
    print(f"ou_line={fmt(ou.get('line'))} over={fmt(ou.get('over_price'))} under={fmt(ou.get('under_price'))}")
    print(f"cover_probability_model={fmt(ah.get('cover_probability_model'))}")
    print(f"cover_probability_market={fmt(ah.get('cover_probability_market'))}")
    print(f"cover_edge={fmt(ah.get('cover_edge'))}")
    print(f"snapshots_count={snapshots_count}")
    print(f"snapshots_source={snapshots_source}")
    print(f"policy_version={fmt(policy.get('policy_version'))}")
    print(f"policy_mode={fmt(policy.get('policy_mode'))}")
    print(f"policy_enforced={policy.get('policy_mode') == 'enforced'}")
    print(f"decision_state={fmt(policy.get('decision_state'))}")
    print(f"recommendation_grade={fmt(policy.get('recommendation_grade'))}")
    print(f"candidate_ah_pick={fmt(policy.get('candidate_ah_pick'))}")
    print(f"main_ah_pick={fmt(policy.get('main_ah_pick'))}")
    print(f"calibration_status={fmt(probability.get('calibration_status'))}")
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
    print(f"pass_reason={fmt(policy.get('pass_reason'))}")
    print(f"observe_reason={fmt(policy.get('observe_reason'))}")
    print(f"policy_summary_cn={fmt(policy.get('policy_summary_cn'))}")
    print(f"ai_policy_consistency={consistency}")
    print(f"ai_conflict_flags={json.dumps(conflict_flags, ensure_ascii=False)}")
    print(f"visible_text_policy_conflicts={json.dumps(visible_conflicts, ensure_ascii=False)}")
    print(f"legacy_pass_reason={pass_reason(bundle)}")
    print(f"missing_recommendation_reason={reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
