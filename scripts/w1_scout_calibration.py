#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 Scout calibration readiness stub.

S24 deliberately does not train calibration. It exposes a stable diagnostic
interface so recommendation policy, backtest, and debug output can all explain
why raw passthrough is still used.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config/w1_calibration_policy.json"
LOCK = ROOT / "state/scout_lock.jsonl"
AUDIT = ROOT / "state/scout_audit.jsonl"
REVIEWS = ROOT / "state/scout_reviews.jsonl"
OUT = ROOT / "state/scout_calibration.json"

import sys

sys.path.insert(0, str(ROOT / "scripts"))
import w1_recommendation_policy as W1REC  # noqa: E402
import w1_scout_backtest as BT  # noqa: E402


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_policy() -> dict[str, Any]:
    return json.loads(POLICY.read_text(encoding="utf-8"))


def available_dims(call: dict[str, Any]) -> int:
    readiness = call.get("data_readiness")
    if readiness == "高":
        return 5
    if readiness == "中":
        return 3
    if readiness == "低":
        return 1
    return 0


def legacy_self_check_payload() -> dict[str, Any]:
    locks = read_jsonl(LOCK)
    audits = read_jsonl(AUDIT)
    reviews = read_jsonl(REVIEWS)
    by_bucket: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "aligned": 0, "known": 0})
    for row in audits:
        bucket = row.get("direction_bucket") or "未分档"
        by_bucket[bucket]["n"] += 1
        if row.get("broadly_aligned") is not None:
            by_bucket[bucket]["known"] += 1
            by_bucket[bucket]["aligned"] += int(bool(row.get("broadly_aligned")))

    direction_calibration = {}
    for bucket, stats in by_bucket.items():
        known = stats["known"]
        direction_calibration[bucket] = {
            "n": stats["n"],
            "aligned": stats["aligned"],
            "aligned_rate": round(stats["aligned"] / known, 3) if known else None,
        }

    readiness_values = [available_dims((lock.get("call") or {})) for lock in locks]
    reviewed_ids = {str(row.get("fixture_id")) for row in reviews}
    finished_ids = {str(row.get("fixture_id")) for row in audits}
    return {
        "schema_version": "W1_SCOUT_CALIBRATION_V1",
        "updated_at_utc": now(),
        "locked_count": len(locks),
        "audited_count": len(audits),
        "reviewed_count": len(reviews),
        "review_coverage_rate": round(len(reviewed_ids & finished_ids) / len(finished_ids), 3) if finished_ids else None,
        "avg_readiness_dims": round(sum(readiness_values) / len(readiness_values), 3) if readiness_values else None,
        "direction_calibration": direction_calibration,
        "note_cn": "这是 Scout 解读的自我体检与校准,不是战胜市场的证据。",
    }


def calibration_diagnosis(fixture_id: str | None = None) -> dict[str, Any]:
    summary = BT.build_summary(fixture_id=fixture_id) if fixture_id else BT.build_summary()
    metadata = W1REC.build_calibration_metadata(int(summary.get("settled_recommend_samples") or 0))
    samples = summary.get("samples") or []
    grade_counts: dict[str, int] = defaultdict(int)
    stage_counts: dict[str, int] = defaultdict(int)
    line_bucket_counts: dict[str, int] = defaultdict(int)
    side_role_counts: dict[str, int] = defaultdict(int)
    settled_observe = 0
    for row in samples:
        grade_counts[str(row.get("recommendation_grade") or "missing")] += 1
        stage_counts[str(row.get("stage_id") or "missing")] += 1
        line_bucket_counts[str(row.get("line_bucket") or "missing")] += 1
        side_role_counts[str(row.get("side_role") or "missing")] += 1
        if row.get("decision_state") == "OBSERVE" and row.get("has_result"):
            settled_observe += 1
    return {
        "schema_version": "W1_SCOUT_CALIBRATION_DIAGNOSIS_V1",
        "generated_at_utc": now(),
        "fixture_id": str(fixture_id or ""),
        "calibration_status": metadata["status"],
        "calibration_method": metadata["method"],
        "sample_scope": metadata["sample_scope"],
        "independent_settled_recommend_samples": metadata["independent_settled_recommend_samples"],
        "required_for_global_sigmoid": metadata["required_for_global_sigmoid"],
        "required_for_line_family": metadata["required_for_line_family"],
        "required_for_isotonic": (load_policy().get("thresholds") or {}).get("isotonic_min_samples", 100),
        "readiness": metadata["readiness"],
        "reason": metadata["reason"],
        "calibration_artifact": metadata["calibration_artifact"],
        "trained_artifact_loaded": metadata["trained_artifact_loaded"],
        "cover_prob_calibrated_equals_raw": True,
        "edge_calibrated_equals_raw": True,
        "diagnostics": {
            "independent_fixtures": summary.get("total_fixtures", 0),
            "settled_observe_diagnostic_samples": settled_observe,
            "pass_filter_samples": summary.get("pass_samples", 0),
            "grade_counts": dict(sorted(grade_counts.items())),
            "stage_counts": dict(sorted(stage_counts.items())),
            "line_bucket_counts": dict(sorted(line_bucket_counts.items())),
            "side_role_counts": dict(sorted(side_role_counts.items())),
        },
    }


def fit_global_sigmoid_stub(*_args: Any, **_kwargs: Any) -> None:
    raise NotImplementedError("S24 only provides calibration readiness stub; global sigmoid training is deferred.")


def fit_isotonic_stub(*_args: Any, **_kwargs: Any) -> None:
    raise NotImplementedError("S24 only provides calibration readiness stub; isotonic training is deferred.")


def fit_line_family_stub(*_args: Any, **_kwargs: Any) -> None:
    raise NotImplementedError("S24 only provides calibration readiness stub; line-family training is deferred.")


def print_diagnosis(payload: dict[str, Any]) -> None:
    readiness = payload.get("readiness") or {}
    print("W1 Scout calibration readiness diagnosis")
    print(f"calibration_status={payload.get('calibration_status')}")
    print(f"calibration_method={payload.get('calibration_method')}")
    print(f"sample_scope={payload.get('sample_scope')}")
    print(f"independent_settled_recommend_samples={payload.get('independent_settled_recommend_samples')}")
    print(f"global_sigmoid_status={readiness.get('global_sigmoid')} need={payload.get('required_for_global_sigmoid')}")
    print(f"line_family_status={readiness.get('line_family')} need={payload.get('required_for_line_family')}")
    print(f"isotonic_status={readiness.get('isotonic')} need={payload.get('required_for_isotonic')}")
    print(f"trained_artifact_loaded={payload.get('trained_artifact_loaded')}")
    print(f"calibration_artifact={payload.get('calibration_artifact') or ''}")
    print(f"reason={payload.get('reason')}")


def self_test() -> None:
    policy = load_policy()
    if policy.get("status") != "untrained":
        raise AssertionError("calibration policy must remain untrained")
    diagnosis = calibration_diagnosis()
    if diagnosis.get("calibration_status") != "untrained":
        raise AssertionError("diagnosis must report untrained")
    if diagnosis.get("calibration_method") != "raw_passthrough":
        raise AssertionError("diagnosis must use raw_passthrough")
    if diagnosis.get("trained_artifact_loaded") is not False:
        raise AssertionError("S24 must not load trained artifact")
    if not diagnosis.get("cover_prob_calibrated_equals_raw") or not diagnosis.get("edge_calibrated_equals_raw"):
        raise AssertionError("untrained calibration must be raw passthrough")
    if "ready" in set((diagnosis.get("readiness") or {}).values()):
        raise AssertionError("current S24 readiness must not claim trained readiness")
    for func in (fit_global_sigmoid_stub, fit_isotonic_stub, fit_line_family_stub):
        try:
            func([])
        except NotImplementedError:
            pass
        else:
            raise AssertionError("training stub must raise NotImplementedError")
    print("W1 Scout calibration readiness self-test PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose W1 Scout AH calibration readiness.")
    parser.add_argument("--diagnose", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fixture-id")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.diagnose or args.json or args.fixture_id:
        payload = calibration_diagnosis(args.fixture_id)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_diagnosis(payload)
        return 0
    payload = legacy_self_check_payload()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"scout calibration PASS: locked={payload['locked_count']} audited={payload['audited_count']} reviewed={payload['reviewed_count']} -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
