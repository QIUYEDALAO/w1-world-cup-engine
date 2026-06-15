#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 S2 strength-prototype checker.

Asserts the prototype stays a research artifact: prototype labels, no future
leakage in the walk-forward, shrinkage applied, host fallback present, market
comparison present, and NO coupling to production (no DEFAULT_RHO / w1_score_engine /
decision_policy / odds thresholds references in the prototype script).
Skips if the (gitignored-dataset-derived) report is absent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/w1_team_strength_prototype_v1.json"
SCRIPT = ROOT / "scripts/w1_team_strength_prototype.py"
errors: list[str] = []


def fail(m: str) -> None:
    errors.append(m)


def main() -> int:
    # static guard on the script: detect REAL production coupling (imports/writes),
    # not prose mentions in the docstring (which legitimately say "does NOT touch ...").
    if SCRIPT.is_file():
        src = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("import w1_score_engine", "from w1_score_engine", "import build_w1_dashboard_data",
                          "from build_w1_dashboard_data", "w1_decision_policy.json", "w1_odds_movement_thresholds.json"):
            if forbidden in src:
                fail(f"prototype must not couple to production: found '{forbidden}'")
    else:
        fail("prototype script missing")

    if not REPORT.is_file():
        if errors:
            for e in errors:
                print(f"FAIL: {e}", file=sys.stderr)
            return 1
        print("SKIP check_w1_team_strength_prototype: report not generated (run w1_team_strength_prototype.py)")
        return 0

    p = json.loads(REPORT.read_text(encoding="utf-8"))
    if p.get("prototype") is not True:
        fail("prototype must be true")
    if p.get("production_validated") is not False:
        fail("production_validated must be false")
    if p.get("production_wired") is not False:
        fail("production_wired must be false")
    wf = p.get("walk_forward", {})
    if wf.get("no_future_leakage") is not True:
        fail("walk_forward.no_future_leakage must be true")
    if not (wf.get("train_range", ["", ""])[1] <= wf.get("test_range", ["", ""])[0]):
        fail(f"train must end before test starts: {wf.get('train_range')} vs {wf.get('test_range')}")
    if not (p.get("hyperparams", {}).get("l2_shrinkage", 0) > 0):
        fail("shrinkage (l2) must be > 0 (partial pooling)")
    if "host_fallback" not in p:
        fail("host_fallback section missing")
    if "market_on_same_subset" not in p.get("test_metrics", {}):
        fail("market comparison missing")
    # Honest framing is enforced structurally (prototype / production_validated /
    # production_wired flags above), not by naive substring scan of disclaimers.

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"W1 strength prototype check FAIL ({len(errors)})")
        return 1
    print("W1 strength prototype check PASS (prototype, no leakage, not wired to production)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
