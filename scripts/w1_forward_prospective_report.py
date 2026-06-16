#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1_FORWARD_LEDGER_PROSPECTIVE_RUN_V1 — aggregate prospective calibration.

Aggregates the post-match audits into a point-in-time prospective-calibration
report (gitignored live JSON). This is a TRUE prospective sample: only fixtures
whose 1X2 prediction was locked before kickoff and that have a local result are
included. Early in WC2026 the sample may legitimately be 0 (machinery ready,
sample accumulates as matches complete). No betting / money / hit-rate output.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / "data/forward_ledger/w1_pre_match_view.jsonl"
AUDIT = ROOT / "data/forward_ledger/w1_post_match_audit.jsonl"
OUT = ROOT / "data/forward_ledger/w1_prospective_calibration_v1.json"


def load(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]


def main() -> int:
    views = load(VIEW)
    audits = load(AUDIT)

    def m(key: str):
        vals = [a["prospective_calibration"][key] for a in audits if "prospective_calibration" in a]
        return round(mean(vals), 6) if vals else None

    by_outcome: dict[str, int] = {"H": 0, "D": 0, "A": 0}
    for a in audits:
        oc = a.get("result", {}).get("outcome")
        if oc in by_outcome:
            by_outcome[oc] += 1

    report = {
        "schema_version": "W1_PROSPECTIVE_AUDIT_V1",
        "record_type": "prospective_calibration_report",
        "note_cn": "真正 prospective 样本：仅纳入赛前锁定 1X2 且有本地赛果的场次。WC2026 早期样本可能为 0（机制就绪，样本随完赛累积），这是 prospective 纪律的正确表现，不是缺陷。",
        "lock_scope": "market_implied_1x2 (V1)",
        "n_pre_match_views_locked": len(views),
        "n_post_match_audited": len(audits),
        "prospective_sample": {
            "n": len(audits),
            "mean_rps_1x2": m("rps_1x2"),
            "mean_logloss_1x2": m("logloss_1x2"),
            "mean_brier_1x2": m("brier_1x2"),
            "mean_prob_of_actual_outcome": m("prob_of_actual_outcome"),
            "outcome_distribution": by_outcome,
        },
        "boundary_cn": "概率建模与赛前/赛后研究；不是投注平台，不输出资金建议，不承诺命中率，不把模型-市场分歧表述为投注机会。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ps = report["prospective_sample"]
    print(f"W1 prospective report: views_locked={len(views)} audited={len(audits)} "
          f"mean_rps_1x2={ps['mean_rps_1x2']} -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
