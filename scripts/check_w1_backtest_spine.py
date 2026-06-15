#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 S1B backtest-spine checker.

Validates the 1X2-only baseline report: forced 1X2_ONLY labels, leakage guard,
non-overlapping walk-forward split, metrics present, and that it never claims the
full W1 pipeline is validated. Skips if the (gitignored) baseline is absent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "reports/w1_backtest_1x2_only_baseline_v1.json"
errors: list[str] = []


def fail(m: str) -> None:
    errors.append(m)


def main() -> int:
    if not BASE.is_file():
        print("SKIP check_w1_backtest_spine: baseline not generated (run w1_backtest_engine.py)")
        return 0
    p = json.loads(BASE.read_text(encoding="utf-8"))
    if p.get("pipeline_mode") != "1X2_ONLY":
        fail("pipeline_mode must be 1X2_ONLY")
    if p.get("w1_full_pipeline_validated") is not False:
        fail("w1_full_pipeline_validated must be false")
    lg = p.get("leakage_guard", {})
    if not str(lg.get("status", "")).startswith("ok"):
        fail("leakage_guard.status must be ok")
    allowed = set(lg.get("allowed_features", []))
    if not allowed or not allowed.issubset({"odds_1x2_home", "odds_1x2_draw", "odds_1x2_away"}):
        fail(f"leakage_guard.allowed_features must be 1X2 odds only, got {sorted(allowed)}")
    o = p.get("overall", {})
    for k in ("n", "mean_rps", "mean_logloss", "direction_accuracy"):
        if o.get(k) is None:
            fail(f"overall missing metric {k}")
    wf = p.get("walk_forward", {})
    if "test" in wf:
        tr, va, te = wf["train"]["range"], wf["val"]["range"], wf["test"]["range"]
        if not (tr[1] <= va[1] and va[1] <= te[1] and tr[0] <= te[0]):
            fail(f"walk-forward ranges not chronological/non-overlapping: {tr} {va} {te}")
    if "比分矩阵" not in p.get("scope_note_cn", "") and "OU" not in p.get("scope_note_cn", ""):
        fail("scope_note must state OU/score-matrix not validated")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"W1 backtest spine check FAIL ({len(errors)})")
        return 1
    print(f"W1 backtest spine check PASS (n={o.get('n')}, mode=1X2_ONLY, full_pipeline_validated=false)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
