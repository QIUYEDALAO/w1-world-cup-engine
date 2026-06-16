#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1_DRAW_CALIBRATION_RESEARCH_V1 checker.

Validates that the draw-calibration work is RESEARCH ONLY and touches nothing in
production. Skip-safe: if the research report is absent (e.g. fresh clone), SKIP
with the rebuild command instead of failing.

Asserts:
  * report flags research_only / prototype / production_wired=false
  * baseline + candidates (B0/C1/C2/C3) present; walk-forward present; 128 scope clear;
    no extrapolation to 1081 / qualifiers
  * recommendation.production_change_recommended == false
  * production red lines untouched: w1_score_engine.py / DEFAULT_RHO / decision_policy /
    odds thresholds have no git diff (research must not modify them)
  * research is NOT wired into production: build/predict do not reference the research
    module; the research script does not import build/predict nor write dashboard/cards/state
  * no affirmative betting / money / hit-rate language
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_JSON = ROOT / "reports/w1_draw_calibration_research_v1.json"
REPORT_MD = ROOT / "reports/W1_DRAW_CALIBRATION_RESEARCH_V1.md"
SPEC = ROOT / "docs/W1_DRAW_CALIBRATION_RESEARCH_V1.md"
SCRIPT = ROOT / "scripts/w1_draw_calibration_research.py"
ENGINE = ROOT / "scripts/w1_score_engine.py"
DECISION_POLICY = ROOT / "config/w1_decision_policy.json"
ODDS_THRESHOLDS = ROOT / "config/w1_odds_movement_thresholds.json"
BUILD = ROOT / "scripts/build_w1_dashboard_data.py"
PREDICT = ROOT / "scripts/w1_local_predict_server.py"

PROTECTED = [
    "scripts/w1_score_engine.py",
    "config/w1_decision_policy.json",
    "config/w1_odds_movement_thresholds.json",
]
# Affirmative-only forbidden terms (avoid bare 投注/资金/命中率 which appear negated in the report).
FORBIDDEN_ASCII = ["bet", "stake", "profit", "guaranteed", "roi"]
FORBIDDEN_CN = ["建议下注", "推荐投注", "稳赚", "必胜", "保证命中", "资金分配", "命中率承诺达成"]
PRODUCTION_WIRING_IN_SCRIPT = ["build_w1_dashboard_data", "w1_local_predict_server",
                              "match_cards", "reports/dashboard", "live_refresh", "DASHBOARD"]
REBUILD = "python3 scripts/w1_draw_calibration_research.py  # regenerate research report"

errors: list[str] = []


def fail(m: str) -> None:
    errors.append(m)


def git_diff_names(paths: list[str]) -> list[str]:
    r = subprocess.run(["git", "diff", "--name-only", "--", *paths], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        return []
    return [x for x in r.stdout.splitlines() if x.strip()]


def scan_forbidden(text: str, label: str) -> None:
    for term in FORBIDDEN_ASCII:
        if re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", text, re.I):
            fail(f"{label} contains affirmative forbidden term: {term}")
    for term in FORBIDDEN_CN:
        if term in text:
            fail(f"{label} contains forbidden term: {term}")


def main() -> int:
    # skip-safe
    if not REPORT_JSON.is_file():
        print("W1 draw calibration research check SKIP (report absent)")
        print(f"  rebuild: {REBUILD}")
        return 0

    if not SPEC.is_file():
        fail("research spec docs/W1_DRAW_CALIBRATION_RESEARCH_V1.md missing")
    if not SCRIPT.is_file():
        fail("research script scripts/w1_draw_calibration_research.py missing")

    r = json.loads(REPORT_JSON.read_text(encoding="utf-8"))

    # 1. research flags
    if r.get("research_only") is not True:
        fail("report.research_only must be true")
    if r.get("prototype") is not True:
        fail("report.prototype must be true")
    if r.get("production_wired") is not False:
        fail("report.production_wired must be false")

    # 2. baseline + candidates + walk-forward + scope
    cands = r.get("candidates", {})
    for key in ("B0_baseline_fixed_rho", "C1_diagnostic_draw_fit_rho",
                "C2_draw_calibration_layer", "C3_parametric_walkforward_rho"):
        if key not in cands:
            fail(f"report missing candidate: {key}")
    if "overall" not in cands.get("B0_baseline_fixed_rho", {}):
        fail("baseline overall metrics missing")
    wf = cands.get("C3_parametric_walkforward_rho", {}).get("walk_forward", {})
    for split in ("train", "val", "test", "baseline_test"):
        if split not in wf:
            fail(f"C3 walk_forward.{split} missing (walk-forward required)")
    if cands.get("C1_diagnostic_draw_fit_rho", {}).get("oracle_like") is not True:
        fail("C1 must be flagged oracle_like=true (diagnostic upper bound, not a production candidate)")

    scope = str(r.get("scope", ""))
    for token in ("128", "2018", "2022"):
        if token not in scope:
            fail(f"scope must reference {token}: '{scope}'")
    if "NOT 1081" not in scope or "NOT qualifiers" not in scope:
        fail(f"scope must explicitly exclude 1081 and qualifiers: '{scope}'")

    # 3. recommendation cannot push to production
    rec = r.get("recommendation", {})
    if rec.get("production_change_recommended") is not False:
        fail("recommendation.production_change_recommended must be false")
    nxt = rec.get("next_stage_recommended")
    if nxt not in (None, "W1_DRAW_CALIBRATION_PROTOTYPE_V2"):
        fail(f"next_stage_recommended may only be null or W1_DRAW_CALIBRATION_PROTOTYPE_V2, got {nxt}")

    # 4. comparison present (baseline vs candidates)
    if "comparison_vs_baseline" not in r:
        fail("report missing comparison_vs_baseline (baseline vs candidates)")

    # 5. red lines: protected production files unchanged (research must not touch them)
    changed = git_diff_names(PROTECTED)
    if changed:
        fail(f"production red-line files changed by research (must not): {changed}")
    if ENGINE.is_file() and "DEFAULT_RHO = -0.057766" not in ENGINE.read_text(encoding="utf-8"):
        fail("DEFAULT_RHO changed from -0.057766")

    # 6. not wired into production
    if SCRIPT.is_file():
        src = SCRIPT.read_text(encoding="utf-8")
        for token in PRODUCTION_WIRING_IN_SCRIPT:
            if token in src:
                fail(f"research script must not reference production wiring: {token}")
    for prod, name in ((BUILD, "build"), (PREDICT, "predict")):
        if prod.is_file() and "w1_draw_calibration_research" in prod.read_text(encoding="utf-8"):
            fail(f"{name} must not import/reference the research module (not wired to production)")

    # 7. no affirmative betting/money/hit-rate language
    for path, label in ((SCRIPT, "research script"), (REPORT_JSON, "report json"),
                        (REPORT_MD, "report md"), (SPEC, "spec")):
        if path.is_file():
            scan_forbidden(path.read_text(encoding="utf-8"), label)

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"W1 draw calibration research check FAIL ({len(errors)})")
        return 1
    print("W1 draw calibration research check PASS "
          "(research-only; production untouched; baseline vs candidates + walk-forward; no production wiring)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
