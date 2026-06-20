#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inspect every dashboard data source for one fixture.

This is a debug/audit tool. It does not mutate runtime state and does not dump
raw API payloads. It exists to catch cases where market_debug, static HTML, and
the live /dashboard-data endpoint disagree about the same Scout decision card.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib import request

ROOT = Path(__file__).resolve().parents[1]
CALLS = ROOT / "state/w1_scout_calls.json"
BUNDLES = ROOT / "state/w1_scout_bundles.json"
DASHBOARD_DATA = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
SCOUT_LOCK = ROOT / "state/scout_lock.jsonl"
DEFAULT_DASHBOARD_URL = "http://127.0.0.1:8765/dashboard-data"
STAGE_PRIORITY = {
    "final_30m": 7,
    "official_1h": 6,
    "watch_2h": 5,
    "watch_6h": 4,
    "watch_12h": 3,
    "early_24h": 2,
    "early_48h": 1,
}

sys.path.insert(0, str(ROOT / "scripts"))
import w1_recommendation_policy as W1REC  # noqa: E402
import w1_decision_card as W1CARD  # noqa: E402
import w1_scout_embed as SCOUT_EMBED  # noqa: E402


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def script_json(path: Path, script_id: str) -> dict[str, Any]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    match = re.search(
        rf'<script id="{re.escape(script_id)}" type="application/json">(.*?)</script>',
        text,
        re.S,
    )
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}


def fetch_dashboard_payload(url: str) -> dict[str, Any]:
    try:
        with request.urlopen(url, timeout=5) as handle:  # noqa: S310 - localhost/debug use
            return json.loads(handle.read().decode("utf-8"))
    except Exception as exc:  # debug tool: report, do not crash all sources
        return {"__fetch_error": str(exc)}


def stage_rank(call: dict[str, Any]) -> int:
    return STAGE_PRIORITY.get(str(call.get("stage_id") or ""), 0)


def generated_at(call: dict[str, Any]) -> str:
    return str(call.get("generated_at") or "")


def has_policy(call: dict[str, Any]) -> int:
    return 1 if isinstance(call.get("policy_result"), dict) else 0


def has_card(call: dict[str, Any]) -> int:
    return 1 if isinstance(call.get("decision_card"), dict) else 0


def best_call(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    return sorted(rows, key=lambda c: (has_policy(c), has_card(c), stage_rank(c), generated_at(c)))[-1]


def calls_for(payload: dict[str, Any], fid: str) -> list[dict[str, Any]]:
    rows = payload.get("calls") if isinstance(payload.get("calls"), list) else []
    return [row for row in rows if isinstance(row, dict) and str(row.get("fixture_id") or "") == fid]


def display_call(call: dict[str, Any]) -> dict[str, Any]:
    if not call:
        return {}
    try:
        SCOUT_EMBED.BUNDLE_BY_FIXTURE = SCOUT_EMBED.load_bundle_map()
        return SCOUT_EMBED.display_call(call)
    except Exception:
        return call


def bundle_for(fid: str) -> dict[str, Any]:
    payload = load_json(BUNDLES)
    for row in payload.get("bundles") or []:
        if isinstance(row, dict) and str(row.get("fixture_id") or "") == fid:
            return row
    return {}


def call_from_bundle(fid: str) -> dict[str, Any]:
    bundle = bundle_for(fid)
    if not bundle:
        return {}
    policy = W1REC.build_policy_result(bundle)
    return {
        "fixture_id": fid,
        "generated_at": "",
        "stage_id": "",
        "policy_result": policy,
        "decision_card": W1CARD.build_decision_card({"fixture_id": fid, "policy_result": policy, "read": {}}),
    }


def record_for(fid: str) -> dict[str, Any]:
    payload = load_json(DASHBOARD_DATA)
    for row in payload.get("match_records") or []:
        if isinstance(row, dict) and str(row.get("fixture_id") or "") == fid:
            return row
    return {}


def lock_for(fid: str) -> dict[str, Any]:
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


def left_label(policy: dict[str, Any]) -> str:
    decision = str(policy.get("decision_state") or "")
    if decision == "RECOMMEND":
        return "已有AI推荐"
    if decision == "OBSERVE":
        return "AI观察"
    if decision == "PASS":
        return "AI PASS"
    return "待生成"


def card_type(policy: dict[str, Any]) -> str:
    decision = str(policy.get("decision_state") or "PASS")
    if decision == "RECOMMEND":
        return "RECOMMEND_CARD"
    if decision == "OBSERVE":
        return "OBSERVE_CARD"
    return "PASS_CARD"


def source_summary(source_name: str, source_path: str, fid: str, call: dict[str, Any], *, selected: bool, found: bool) -> None:
    policy = call.get("policy_result") if isinstance(call.get("policy_result"), dict) else {}
    decision_card = call.get("decision_card") if isinstance(call.get("decision_card"), dict) else {}
    if policy and not decision_card:
        try:
            decision_card = W1CARD.build_decision_card(call)
        except Exception:
            decision_card = {}
    gates = policy.get("hard_gates") if isinstance(policy.get("hard_gates"), dict) else {}
    print(f"source_name={source_name}")
    print(f"source_path_or_url={source_path}")
    print(f"fixture_id={fid}")
    print(f"found={str(found).lower()}")
    print(f"selected={str(selected).lower()}")
    print(f"generated_at={call.get('generated_at') or 'missing'}")
    print(f"stage_id={call.get('stage_id') or 'missing'}")
    print(f"policy_result.decision_state={policy.get('decision_state') or 'missing'}")
    print(f"policy_result.recommendation_grade={policy.get('recommendation_grade') or 'missing'}")
    print(f"decision_card.card_type={decision_card.get('card_type') or card_type(policy)}")
    print(f"decision_card.headline={decision_card.get('headline_cn') or 'missing'}")
    print(f"decision_card.main_pick={decision_card.get('main_pick_cn') or policy.get('main_ah_pick') or 'missing'}")
    print(f"failed_gates={json.dumps(policy.get('failed_gates') or [], ensure_ascii=False)}")
    print(f"pass_reason={policy.get('pass_reason') or 'missing'}")
    print(f"has_ah={gates.get('has_ah', 'missing')}")
    print(f"has_market_fair_prob={gates.get('has_market_fair_prob', 'missing')}")
    print(f"has_score_matrix={gates.get('has_score_matrix', 'missing')}")
    print(f"dashboard_visible_title={decision_card.get('headline_cn') or 'missing'}")
    print(f"dashboard_visible_grade={decision_card.get('recommendation_grade') or policy.get('recommendation_grade') or 'missing'}")
    print(f"dashboard_left_status_label={left_label(policy)}")
    print("")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect dashboard sources for one fixture.")
    parser.add_argument("--fixture-id", required=True)
    parser.add_argument("--dashboard-url", default=DEFAULT_DASHBOARD_URL)
    args = parser.parse_args()
    fid = str(args.fixture_id)

    print(f"fixture_id={fid}")
    print("dynamic_dashboard_cache_policy=/dashboard-data reloads Scout display helper per request; static HTML is offline fallback")
    print("")

    state_rows = calls_for(load_json(CALLS), fid)
    state_best_raw = best_call(state_rows)
    source_summary("state_raw_calls", str(CALLS.relative_to(ROOT)), fid, state_best_raw, selected=bool(state_best_raw), found=bool(state_rows))

    state_best_display = display_call(state_best_raw)
    source_summary("state_display_calls", f"{CALLS.relative_to(ROOT)} via w1_scout_embed.display_call", fid, state_best_display, selected=bool(state_best_display), found=bool(state_best_raw))

    bundle_call = call_from_bundle(fid)
    source_summary("state_bundle_policy", str(BUNDLES.relative_to(ROOT)), fid, bundle_call, selected=False, found=bool(bundle_call))

    rec = record_for(fid)
    rec_call = {
        "fixture_id": fid,
        "policy_result": {},
        "decision_card": {},
        "score_distribution": rec.get("score_distribution"),
        "score_matrix_summary": rec.get("score_matrix_summary"),
    } if rec else {}
    source_summary("dashboard_assets_record", str(DASHBOARD_DATA.relative_to(ROOT)), fid, rec_call, selected=False, found=bool(rec))
    if rec:
        sd = rec.get("score_distribution") if isinstance(rec.get("score_distribution"), dict) else {}
        sm = rec.get("score_matrix_summary") if isinstance(rec.get("score_matrix_summary"), dict) else {}
        print(f"assets.score_distribution.status={sd.get('status') or 'missing'}")
        print(f"assets.score_matrix_summary.status={sm.get('status') or 'missing'}")
        print(f"assets.local_market_overlay_source={sm.get('local_market_overlay_source') or sd.get('market_input_overlay_source') or 'missing'}")
        print("")

    html_payload = script_json(HTML, "w1-scout-calls")
    html_rows = calls_for(html_payload, fid)
    html_best = best_call(html_rows)
    source_summary("static_html_embed", str(HTML.relative_to(ROOT)), fid, html_best, selected=bool(html_best), found=bool(html_rows))

    live_payload = fetch_dashboard_payload(args.dashboard_url)
    live_calls = live_payload.get("scout_calls") if isinstance(live_payload.get("scout_calls"), dict) else {}
    live_rows = calls_for(live_calls, fid)
    live_best = best_call(live_rows)
    source_summary("live_dashboard_data", args.dashboard_url, fid, live_best, selected=bool(live_best), found=bool(live_rows))
    if live_payload.get("__fetch_error"):
        print(f"live_dashboard_error={live_payload.get('__fetch_error')}")
        print("")

    lock = lock_for(fid)
    lock_call = lock.get("call") if isinstance(lock.get("call"), dict) else {}
    source_summary("scout_lock_reference_only", str(SCOUT_LOCK.relative_to(ROOT)), fid, lock_call, selected=False, found=bool(lock_call))
    print("scout_lock_display_override=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
