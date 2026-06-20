#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 Scout AH settlement backtest framework.

Reads local Scout calls/bundles and local result overlays. It never writes
reports by default and never trains calibration or changes policy thresholds.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/w1_backtest_policy.json"
CALLS = ROOT / "state/w1_scout_calls.json"
BUNDLES = ROOT / "state/w1_scout_bundles.json"

sys.path.insert(0, str(ROOT / "scripts"))
import w1_ah_settlement as AH  # noqa: E402
import w1_recommendation_policy as W1REC  # noqa: E402


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def root_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def load_config() -> dict[str, Any]:
    return load_json(CONFIG)


def load_results(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in config.get("result_sources") or []:
        path = root_path(item)
        if not path.is_file():
            continue
        payload = load_json(path)
        for fid, row in (payload.get("results") or {}).items():
            row = dict(row)
            row.setdefault("result_source_path", str(path.relative_to(ROOT)))
            out[str(fid)] = row
            for alias in row.get("alias_fixture_ids", []) or []:
                out[str(alias)] = row
    return out


def load_bundles() -> dict[str, dict[str, Any]]:
    payload = load_json(BUNDLES)
    return {str(row.get("fixture_id")): row for row in payload.get("bundles") or [] if row.get("fixture_id") is not None}


def load_calls() -> list[dict[str, Any]]:
    payload = load_json(CALLS)
    return [row for row in payload.get("calls") or [] if isinstance(row, dict)]


def stage_rank(stage_id: str | None, config: dict[str, Any]) -> int:
    order = ((config.get("default_sample_policy") or {}).get("prefer_stage_order") or [])
    try:
        return len(order) - order.index(str(stage_id or ""))
    except ValueError:
        return 0


def call_generated_at(call: dict[str, Any]) -> str:
    return str(call.get("generated_at") or "")


def normalize_call(call: dict[str, Any], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    out = json.loads(json.dumps(call, ensure_ascii=False))
    if not isinstance(out.get("policy_result"), dict) and isinstance(bundle, dict):
        out["policy_result"] = W1REC.build_policy_result(bundle)
    if isinstance(out.get("policy_result"), dict):
        W1REC.enforce_call_with_policy(out, out["policy_result"])
    return out


def select_calls(calls: list[dict[str, Any]], config: dict[str, Any], all_stages: bool = False) -> list[dict[str, Any]]:
    sample_policy = config.get("default_sample_policy") or {}
    one_sample_per_fixture = bool(sample_policy.get("one_sample_per_fixture", True))
    if all_stages or not one_sample_per_fixture:
        return calls
    by_fixture: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for call in calls:
        by_fixture[str(call.get("fixture_id"))].append(call)
    selected: list[dict[str, Any]] = []
    for rows in by_fixture.values():
        rows = sorted(rows, key=lambda call: (stage_rank(call.get("stage_id"), config), call_generated_at(call)), reverse=True)
        selected.append(rows[0])
    return selected


def selected_score(result: dict[str, Any], side: str) -> tuple[int, int] | None:
    score = result.get("actual_score") if isinstance(result.get("actual_score"), dict) else {}
    if score.get("home") is None or score.get("away") is None:
        return None
    home = int(score["home"])
    away = int(score["away"])
    if side == "home":
        return home, away
    if side == "away":
        return away, home
    return None


def sample_from_call(call: dict[str, Any], results: dict[str, dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    fid = str(call.get("fixture_id") or "")
    policy = call.get("policy_result") if isinstance(call.get("policy_result"), dict) else {}
    decision = str(policy.get("decision_state") or "PASS")
    grade = str(policy.get("recommendation_grade") or "PASS")
    side = str(policy.get("main_ah_side") or policy.get("candidate_ah_side") or "")
    handicap = (policy.get("market") or {}).get("selected_handicap")
    result = results.get(fid)
    sample = {
        "fixture_id": fid,
        "stage_id": call.get("stage_id") or policy.get("stage_id") or "",
        "decision_state": decision,
        "recommendation_grade": grade,
        "candidate_ah_pick": policy.get("candidate_ah_pick") or "",
        "main_ah_pick": policy.get("main_ah_pick") or "",
        "main_ah_side": policy.get("main_ah_side") or "",
        "selected_side": side,
        "selected_handicap": handicap,
        "line_bucket": AH.line_bucket(float(handicap), config.get("line_buckets")) if handicap is not None else "missing",
        "side_role": AH.side_role(float(handicap)) if handicap is not None else "missing",
        "calibration_status": (policy.get("probability") or {}).get("calibration_status") or "unknown",
        "movement_flags": policy.get("movement_flags") or [],
        "has_result": bool(result),
        "settlement_result": "SKIP",
        "settlement_value": None,
        "diagnostic_only": decision == "OBSERVE",
        "filter_only": decision == "PASS",
    }
    if decision != "RECOMMEND":
        return sample
    if not result:
        sample["missing_result_reason"] = "missing final result"
        return sample
    score_pair = selected_score(result, side)
    if score_pair is None or handicap is None:
        sample["missing_result_reason"] = "missing score/handicap/side"
        return sample
    settlement = AH.settle_ah_pick(score_pair[0], score_pair[1], float(handicap))
    sample.update(settlement)
    sample["final_score"] = result.get("actual_score")
    return sample


def empty_metric() -> dict[str, Any]:
    return {
        "settled": 0,
        "full_win_count": 0,
        "half_win_count": 0,
        "push_count": 0,
        "half_loss_count": 0,
        "full_loss_count": 0,
        "net_settlement_points": 0.0,
        "average_settlement_points": None,
        "win_like_rate": None,
        "loss_like_rate": None,
        "push_rate": None,
    }


def add_metric(metric: dict[str, Any], sample: dict[str, Any]) -> None:
    result = sample.get("settlement_result")
    value = sample.get("settlement_value")
    if result not in {"full_win", "half_win", "push", "half_loss", "full_loss"} or value is None:
        return
    metric["settled"] += 1
    metric[f"{result}_count"] += 1
    metric["net_settlement_points"] = round(float(metric["net_settlement_points"]) + float(value), 3)


def finish_metric(metric: dict[str, Any]) -> dict[str, Any]:
    settled = int(metric["settled"])
    if settled:
        metric["average_settlement_points"] = round(float(metric["net_settlement_points"]) / settled, 4)
        metric["win_like_rate"] = round((metric["full_win_count"] + metric["half_win_count"]) / settled, 4)
        metric["loss_like_rate"] = round((metric["full_loss_count"] + metric["half_loss_count"]) / settled, 4)
        metric["push_rate"] = round(metric["push_count"] / settled, 4)
    return metric


def summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    recommend = [s for s in samples if s.get("decision_state") == "RECOMMEND"]
    observe = [s for s in samples if s.get("decision_state") == "OBSERVE"]
    passed = [s for s in samples if s.get("decision_state") == "PASS"]
    settled_recommend = [s for s in recommend if s.get("settlement_value") is not None]
    missing_result = [s for s in recommend if s.get("settlement_value") is None]
    primary = empty_metric()
    for sample in settled_recommend:
        add_metric(primary, sample)
    group_fields = ("decision_state", "recommendation_grade", "line_bucket", "side_role", "selected_side", "stage_id", "calibration_status")
    groups: dict[str, dict[str, dict[str, Any]]] = {}
    for field in group_fields:
        groups[field] = {}
        for sample in samples:
            key = str(sample.get(field) or "missing")
            groups[field].setdefault(key, empty_metric())
            add_metric(groups[field][key], sample)
        groups[field] = {key: finish_metric(metric) for key, metric in sorted(groups[field].items())}
    movement_groups: dict[str, dict[str, Any]] = {}
    for sample in samples:
        flags = sample.get("movement_flags") or ["none"]
        for flag in flags:
            movement_groups.setdefault(str(flag), empty_metric())
            add_metric(movement_groups[str(flag)], sample)
    calibration = W1REC.build_calibration_metadata(len(settled_recommend))
    return {
        "schema_version": "W1_SCOUT_AH_BACKTEST_SUMMARY_V1",
        "total_fixtures": len({s.get("fixture_id") for s in samples}),
        "recommend_samples": len(recommend),
        "observe_samples": len(observe),
        "pass_samples": len(passed),
        "settled_recommend_samples": len(settled_recommend),
        "missing_result_samples": len(missing_result),
        "primary_performance": finish_metric(primary),
        "calibration_readiness": calibration,
        "calibration_status": calibration.get("status"),
        "calibration_method": calibration.get("method"),
        "independent_settled_recommend_samples": calibration.get("independent_settled_recommend_samples"),
        "calibration_sample_scope": calibration.get("sample_scope"),
        "groups": groups,
        "movement_flags": {key: finish_metric(metric) for key, metric in sorted(movement_groups.items())},
        "samples": samples,
    }


def build_summary(all_stages: bool = False, fixture_id: str | None = None) -> dict[str, Any]:
    config = load_config()
    bundles = load_bundles()
    calls = [normalize_call(call, bundles.get(str(call.get("fixture_id")))) for call in load_calls()]
    if fixture_id:
        calls = [call for call in calls if str(call.get("fixture_id")) == str(fixture_id)]
    calls = select_calls(calls, config, all_stages=all_stages)
    results = load_results(config)
    samples = [sample_from_call(call, results, config) for call in calls]
    return summarize(samples)


def print_summary(summary: dict[str, Any]) -> None:
    if not summary.get("samples"):
        print("SKIP: missing runtime input (state/w1_scout_calls.json has no calls)")
        return
    perf = summary["primary_performance"]
    print("W1 Scout AH backtest summary")
    print(f"total_fixtures={summary['total_fixtures']}")
    print(f"recommend_samples={summary['recommend_samples']}")
    print(f"observe_samples={summary['observe_samples']}")
    print(f"pass_samples={summary['pass_samples']}")
    print(f"settled_recommend_samples={summary['settled_recommend_samples']}")
    print(f"missing_result_samples={summary['missing_result_samples']}")
    calibration = summary.get("calibration_readiness") or {}
    readiness = calibration.get("readiness") or {}
    print(f"calibration_status={calibration.get('status')}")
    print(f"calibration_method={calibration.get('method')}")
    print(f"calibration_sample_scope={calibration.get('sample_scope')}")
    print(f"independent_settled_recommend_samples={calibration.get('independent_settled_recommend_samples')}")
    print(f"global_sigmoid_status={readiness.get('global_sigmoid')}")
    print(f"line_family_status={readiness.get('line_family')}")
    print(f"isotonic_status={readiness.get('isotonic')}")
    print(f"net_settlement_points={perf['net_settlement_points']}")
    print(f"average_settlement_points={perf['average_settlement_points']}")
    print(f"win_like_rate={perf['win_like_rate']}")
    print(f"loss_like_rate={perf['loss_like_rate']}")
    print(f"push_rate={perf['push_rate']}")


def fixture_report(summary: dict[str, Any], fixture_id: str) -> None:
    rows = [row for row in summary.get("samples") or [] if str(row.get("fixture_id")) == str(fixture_id)]
    if not rows:
        print(f"SKIP: missing Scout sample for fixture_id={fixture_id}")
        return
    row = rows[0]
    if row.get("settlement_value") is None:
        print(f"settlement_preview=SKIP: {row.get('missing_result_reason') or 'not a RECOMMEND sample or missing final result'}")
    else:
        print(f"settlement_preview={row.get('settlement_result')} value={row.get('settlement_value')}")
    print(json.dumps(row, ensure_ascii=False, indent=2))


def synthetic_calls() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    cfg = W1REC.load_policy_config()
    base = W1REC.build_policy_result(W1REC._sample_bundle(0.06), cfg)
    observe = W1REC.build_policy_result(W1REC._sample_bundle(0.02), cfg)
    passed = W1REC.build_policy_result(W1REC._sample_bundle(0.01), cfg)
    calls = []
    for fid, stage, policy in (
        ("A", "early_24h", base),
        ("A", "final_30m", base),
        ("B", "official_1h", observe),
        ("C", "watch_2h", passed),
    ):
        call = {"fixture_id": fid, "stage_id": stage, "generated_at": f"2026-06-20T0{len(calls)}:00:00Z", "policy_result": policy, "read": {}}
        calls.append(W1REC.enforce_call_with_policy(call, policy))
    results = {
        "A": {"actual_score": {"home": 1, "away": 0}},
        "B": {"actual_score": {"home": 0, "away": 0}},
        "C": {"actual_score": {"home": 0, "away": 1}},
    }
    return calls, results


def self_test() -> None:
    AH.self_test()
    config = load_config()
    calls, results = synthetic_calls()
    selected = select_calls(calls, config, all_stages=False)
    if len(selected) != 3:
        raise AssertionError("default sample policy must select one call per fixture")
    if next(row for row in selected if row["fixture_id"] == "A")["stage_id"] != "final_30m":
        raise AssertionError("default sample policy must prefer final stage")
    samples = [sample_from_call(call, results, config) for call in selected]
    summary = summarize(samples)
    if summary["recommend_samples"] != 1 or summary["observe_samples"] != 1 or summary["pass_samples"] != 1:
        raise AssertionError("RECOMMEND/OBSERVE/PASS sample routing failed")
    if summary["settled_recommend_samples"] != 1:
        raise AssertionError("RECOMMEND sample must enter primary settlement")
    if summary["primary_performance"]["settled"] != 1:
        raise AssertionError("OBSERVE/PASS must not enter primary settlement")
    calibration = summary.get("calibration_readiness") or {}
    if calibration.get("status") != "untrained" or calibration.get("method") != "raw_passthrough":
        raise AssertionError("S24 calibration must remain untrained raw_passthrough")
    if calibration.get("independent_settled_recommend_samples") != 1:
        raise AssertionError("calibration settled sample count must follow settled RECOMMEND samples")
    if set((calibration.get("readiness") or {}).values()) != {"insufficient_sample"}:
        raise AssertionError("synthetic calibration readiness must be insufficient_sample")
    if AH.line_bucket(0.74) != "0.75" or AH.side_role(-0.5) != "favorite" or AH.side_role(0.5) != "underdog" or AH.side_role(0) != "pickem":
        raise AssertionError("line bucket / side role failed")
    print("W1 Scout AH backtest self-test PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest W1 Scout AH recommendation settlement.")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fixture-id")
    parser.add_argument("--all-stages", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    summary = build_summary(all_stages=args.all_stages, fixture_id=args.fixture_id)
    if args.json:
        text = json.dumps(summary, ensure_ascii=False, indent=2)
    elif args.fixture_id:
        fixture_report(summary, args.fixture_id)
        return 0
    else:
        from io import StringIO
        buf = StringIO()
        old = sys.stdout
        try:
            sys.stdout = buf
            print_summary(summary)
        finally:
            sys.stdout = old
        text = buf.getvalue().rstrip() + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
