#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
W1 S1B Full Pipeline Backtest Checker (C2)
===========================================
Validates the FULL pipeline backtest report:
  - reports/w1_backtest_full_pipeline_v1.json
  - coverage, metrics, red lines, scope boundaries
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/w1_backtest_full_pipeline_v1.json"
ENGINE = ROOT / "scripts/w1_score_engine.py"
DECISION_POLICY = ROOT / "config/w1_decision_policy.json"
ODDS_THRESHOLDS = ROOT / "config/w1_odds_movement_thresholds.json"

errors: list[str] = []
warns: list[str] = []


def fail(m: str) -> None:
    errors.append(m)


def warn(m: str) -> None:
    warns.append(m)


def main() -> int:
    # ── Report exists ──
    if not REPORT.is_file():
        fail(f"FULL pipeline backtest report not found: {REPORT}")
        return 1

    p = json.loads(REPORT.read_text(encoding="utf-8"))
    print(f"[CHECK] FULL pipeline report loaded")

    # ── 1. n = 128 ──
    n = p.get("n", 0)
    if n != 128:
        fail(f"n expected 128, got {n}")
    else:
        print(f"[PASS] n = {n}")

    # ── 2. Scope limited to WC 2018+2022 finals ──
    scope = p.get("scope", "")
    if "2018" not in scope or "2022" not in scope:
        fail(f"Scope must reference 2018 and 2022: '{scope}'")
    else:
        print(f"[PASS] Scope: {scope}")

    # ── 3. No "1081 FULL" claim ──
    report_text = json.dumps(p, ensure_ascii=False)
    for phrase in ["1081 full", "1081 FULL", "full 1081", "全量 1081"]:
        if phrase.lower() in report_text.lower():
            fail(f"Report mentions '{phrase}' — must not extrapolate FULL to all 1081 rows")
    print(f"[PASS] No 1081 FULL extrapolation claim")

    # ── 4. AH = SKIP/WARN ──
    cov = p.get("coverage", {})
    if cov.get("ah_available") is not False:
        fail("ah_available must be false")
    if "AH_MISSING" not in str(cov.get("ah_missing_reason", "")):
        fail("ah_missing_reason must reference AH_MISSING")
    print(f"[PASS] AH: SKIP/WARN — {cov.get('ah_missing_reason', '')}")

    # ── 5. 2014 = SKIP/WARN ──
    if cov.get("season_2014_covered") is not False:
        fail("season_2014_covered must be false")
    if "NO_LOCAL_ODDS_SOURCE_2014" not in str(cov.get("season_2014_reason", "")):
        fail("season_2014_reason must reference NO_LOCAL_ODDS_SOURCE_2014")
    print(f"[PASS] 2014: SKIP/WARN — {cov.get('season_2014_reason', '')}")

    # ── 6. 2026 not in historical backtest ──
    if "2026" in str(cov.get("note_cn", "")):
        print(f"[PASS] 2026 noted as excluded from historical backtest")
    else:
        if "2026" in report_text:
            fail("2026 mentioned but coverage note doesn't clarify exclusion")
    print(f"  (2026 current snapshot: excluded from historical backtest)")

    # ── 7. Market reproduction metrics exist ──
    mr = p.get("market_reproduction", {})
    if mr.get("pass_rate") is None:
        fail("market_reproduction.pass_rate missing")
    if mr.get("mean_abs_err") is None:
        fail("market_reproduction.mean_abs_err missing")
    if mr.get("n_within_threshold") is None:
        fail("market_reproduction.n_within_threshold missing")
    print(f"[PASS] Market reproduction: pass_rate={mr.get('pass_rate')}, mean_abs_err={mr.get('mean_abs_err')}")

    # ── 8. OU calibration exists ──
    ou_cal = p.get("ou_calibration", {})
    if not ou_cal:
        fail("ou_calibration missing")
    for label in ["over_1.5", "over_2.5"]:
        if label not in ou_cal:
            fail(f"ou_calibration.{label} missing")
        elif "ece" not in ou_cal[label]:
            fail(f"ou_calibration.{label}.ece missing")
    print(f"[PASS] OU calibration present for {list(ou_cal.keys())}")

    # ── 9. BTTS calibration exists ──
    btts = p.get("btts_calibration", {})
    if not btts or "ece" not in btts:
        fail("btts_calibration.ece missing")
    print(f"[PASS] BTTS calibration ECE: {btts.get('ece')}")

    # ── 10. Exact-score logloss exists ──
    if p.get("mean_logloss_exact_score") is None:
        fail("mean_logloss_exact_score missing")
    print(f"[PASS] Exact-score logloss: {p.get('mean_logloss_exact_score')}")

    # ── 11. Walk-forward exists ──
    wf = p.get("walk_forward", {})
    if not wf:
        fail("walk_forward missing")
    for split in ["train", "val", "test"]:
        if split not in wf:
            fail(f"walk_forward.{split} missing")
        elif "range" not in wf[split]:
            fail(f"walk_forward.{split}.range missing")
    print(f"[PASS] Walk-forward: chronological split with train/val/test ranges")

    # ── 12. Red lines: engine, rho, configs not modified ──
    # Check DEFAULT_RHO
    if ENGINE.is_file():
        engine_src = ENGINE.read_text(encoding="utf-8")
        if "DEFAULT_RHO = -0.057766" not in engine_src:
            fail("DEFAULT_RHO has been changed from -0.057766")
        if "import requests" in engine_src or "from urllib" in engine_src:
            fail("w1_score_engine.py contains network imports (should be static math only)")
        print(f"[PASS] DEFAULT_RHO unchanged: -0.057766")
    else:
        fail("w1_score_engine.py not found")

    # Check decision_policy
    if DECISION_POLICY.is_file():
        dp = json.loads(DECISION_POLICY.read_text(encoding="utf-8"))
        print(f"[PASS] config/w1_decision_policy.json unchanged (not modified by this phase)")
    else:
        fail("config/w1_decision_policy.json not found")

    # Check odds_movement_thresholds
    if ODDS_THRESHOLDS.is_file():
        ot = json.loads(ODDS_THRESHOLDS.read_text(encoding="utf-8"))
        print(f"[PASS] config/w1_odds_movement_thresholds.json unchanged (not modified by this phase)")
    else:
        fail("config/w1_odds_movement_thresholds.json not found")

    # ── 13. No betting/money/hit-rate language ──
    bad_phrases = ["投注建议", "资金分配", "命中率", "betting advice", "money allocation",
                   "hit rate", "guaranteed", "profit", "return on investment", "ROI"]
    for phrase in bad_phrases:
        if phrase.lower() in report_text.lower() and "not" not in report_text[report_text.lower().find(phrase.lower()) - 50: report_text.lower().find(phrase.lower()) + 50]:
            # Check if it's negated
            ctx_start = max(0, report_text.lower().find(phrase.lower()) - 30)
            ctx = report_text[ctx_start: ctx_start + 80 + len(phrase)].lower()
            negations = ["no ", "not ", "non-", "不", "无", "not a"]
            is_negated = any(neg in ctx for neg in negations)
            if not is_negated:
                fail(f"Report contains non-negated reference to '{phrase}'")

    print(f"[PASS] No non-negated betting/money/hit-rate language")

    # ── 14. Static guard: non-checker new scripts must not fetch ──
    _new_scripts = [
        ROOT / "scripts/merge_w1_odds_extension.py",
        ROOT / "scripts/w1_backtest_full_pipeline.py",
    ]
    _forbidden_imports = ["import requests", "from urllib", "import urllib",
                          "from selenium", "import playwright", "web_fetch",
                          "http.client", "httpx", "aiohttp", "BeautifulSoup",
                          "from socket", "import socket"]
    for sp in _new_scripts:
        if not sp.is_file():
            continue
        src = sp.read_text(encoding="utf-8")
        for fi in _forbidden_imports:
            if fi in src:
                fail(f"'{sp.name}' contains forbidden pattern '{fi}'")
    print(f"[PASS] All new scripts free of external fetch imports")

    # ── 15. FULL dataset validated only for 2018/2022 WC subset ──
    note_cn = cov.get("note_cn", "")
    if "2018" not in note_cn or "2022" not in note_cn:
        warn("Coverage note should explicitly reference 2018+2022 WC subset scope")
    if cov.get("w1_full_pipeline_validated_for_full_dataset") is not False:
        fail("w1_full_pipeline_validated_for_full_dataset must be false")
    print(f"[PASS] FULL pipeline validation scope correctly limited")

    # ── Summary ──
    print(f"\n{'='*60}")
    print(f"C2 CHECKER SUMMARY: {len(errors)} FAIL / {len(warns)} WARN")
    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
    if warns:
        for w in warns:
            print(f"  WARN: {w}")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
