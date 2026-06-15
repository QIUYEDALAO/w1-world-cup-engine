#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 anomaly-review checker.

Validates the diagnostic: every outlier classified, diagnostic-only flags set,
red lines intact (engine/rho/policy/thresholds untouched, no fetch, engine
read-only, future fix not implemented here). Skips if report absent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/w1_full_pipeline_anomaly_review_v1.json"
SRC = ROOT / "scripts/review_w1_full_pipeline_anomaly.py"
ENGINE = ROOT / "scripts/w1_score_engine.py"
errors: list[str] = []


def fail(m: str) -> None:
    errors.append(m)


def main() -> int:
    # static guard on the review script (always)
    if SRC.is_file():
        src = SRC.read_text(encoding="utf-8")
        for bad in ("import requests", "from urllib", "import urllib", "web_fetch", "httpx",
                    "aiohttp", "BeautifulSoup", "selenium", "http.client", "import socket"):
            if bad in src:
                fail(f"review script must not fetch externally: found '{bad}'")
        if "DEFAULT_RHO =" in src or "DEFAULT_RHO=" in src:
            fail("review must not assign DEFAULT_RHO (engine read-only)")
        if "import w1_score_engine" not in src:
            fail("review must read-only import w1_score_engine")
    else:
        fail("review script missing")
    # engine red line
    if ENGINE.is_file() and "DEFAULT_RHO = -0.057766" not in ENGINE.read_text(encoding="utf-8"):
        fail("DEFAULT_RHO changed from -0.057766")

    if not REPORT.is_file():
        if errors:
            for e in errors:
                print(f"FAIL: {e}", file=sys.stderr)
            return 1
        print("SKIP check_w1_anomaly_review: report not generated (run review_w1_full_pipeline_anomaly.py)")
        return 0

    p = json.loads(REPORT.read_text(encoding="utf-8"))
    if p.get("diagnostic_only") is not True:
        fail("diagnostic_only must be true")
    for k in ("engine_modified", "rho_modified", "refetch_performed"):
        if p.get(k) is not False:
            fail(f"{k} must be false")
    outliers = p.get("outliers", [])
    if p.get("n_outliers") != len(outliers):
        fail("n_outliers mismatch")
    if not outliers:
        fail("no outliers recorded (expected the FULL-replay outliers)")
    if any(not o.get("cause") for o in outliers):
        fail("every outlier must carry a cause")
    cd = p.get("cause_distribution", {})
    if sum(cd.values()) != len(outliers):
        fail("cause_distribution does not sum to n_outliers")
    # data_bug_found must be consistent with classified causes
    data_bug_causes = {"ORIENTATION_TEAM", "OU_LADDER_SELECTION", "MU_1X2_INCONSISTENCY"}
    expect_bug = any(c in data_bug_causes for c in cd)
    if bool(p.get("data_bug_found")) != expect_bug:
        fail(f"data_bug_found={p.get('data_bug_found')} inconsistent with causes {list(cd)}")
    fr = p.get("future_research_candidate", {})
    if fr.get("implemented_in_this_stage") is not False:
        fail("future research candidate must NOT be implemented in this diagnostic stage")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"W1 anomaly-review check FAIL ({len(errors)})")
        return 1
    print(f"W1 anomaly-review check PASS (outliers={len(outliers)}, causes={cd}, data_bug_found={p.get('data_bug_found')}; engine untouched)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
