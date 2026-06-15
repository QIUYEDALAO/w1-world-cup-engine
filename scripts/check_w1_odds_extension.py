#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
W1 S1B Odds Extension Checker (C1)
===================================
Validates the local odds extension merge output:
  - data/processed/international/w1_international_dataset_extended.csv
  - data/processed/international/w1_current_odds_snapshot_quality.json
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT_PATH = ROOT / "data/processed/international/w1_international_dataset_extended.csv"
CUR_QUALITY = ROOT / "data/processed/international/w1_current_odds_snapshot_quality.json"
SNAPSHOT_DIR = ROOT / "data/local_odds"
PROCESSED_DIR = ROOT / "data/processed/international"

errors: list[str] = []
warns: list[str] = []


def fail(m: str) -> None:
    errors.append(m)


def warn(m: str) -> None:
    warns.append(m)


def main() -> int:
    # ── 1. Extended dataset exists ──
    if not EXT_PATH.is_file():
        fail(f"Extended dataset not found: {EXT_PATH} (run merge_w1_odds_extension.py first)")
        return 1
    rows = list(csv.DictReader(EXT_PATH.open(encoding="utf-8")))
    print(f"[CHECK] Extended dataset loaded: {len(rows)} rows")

    # Count by competition + pipeline_mode
    wc_2018_full = sum(1 for r in rows if r.get("competition") == "World Cup 2018" and r.get("pipeline_mode") == "FULL")
    wc_2022_full = sum(1 for r in rows if r.get("competition") == "World Cup 2022" and r.get("pipeline_mode") == "FULL")
    wc_2014_full = sum(1 for r in rows if r.get("competition") == "World Cup 2014" and r.get("pipeline_mode") == "FULL")
    full_total = sum(1 for r in rows if r.get("pipeline_mode") == "FULL")
    x2_total = sum(1 for r in rows if r.get("pipeline_mode") == "1X2_ONLY")

    # ── 2. FULL coverage = 128 ──
    if full_total != 128:
        fail(f"FULL coverage expected 128, got {full_total}")
    else:
        print(f"[PASS] FULL coverage: {full_total}")

    # ── 3. 2018 FULL = 64 ──
    if wc_2018_full != 64:
        fail(f"2018 FULL expected 64, got {wc_2018_full}")
    else:
        print(f"[PASS] 2018 FULL: {wc_2018_full}")

    # ── 4. 2022 FULL = 64 ──
    if wc_2022_full != 64:
        fail(f"2022 FULL expected 64, got {wc_2022_full}")
    else:
        print(f"[PASS] 2022 FULL: {wc_2022_full}")

    # ── 5. 2014 FULL = 0 + WARN ──
    if wc_2014_full > 0:
        fail(f"2014 FULL expected 0, got {wc_2014_full}")
    else:
        warn("2014 full coverage = 0 (NO_LOCAL_ODDS_SOURCE_2014)")
        print(f"[WARN] 2014 FULL: {wc_2014_full} — NO_LOCAL_ODDS_SOURCE_2014")

    # ── 6. AH missing ──
    ah_avail = sum(1 for r in rows if r.get("ah_available") == "True")
    if ah_avail > 0:
        fail(f"AH should be unavailable, but {ah_avail} rows have ah_available=True")
    else:
        warn("AH missing from all rows (AH_MISSING_NO_SOURCE)")
        print("[WARN] AH: AH_MISSING_NO_SOURCE — AH backtest SKIP")

    # ── 7. 2026 current snapshot not in historical ──
    wc_2026_in_historical = sum(1 for r in rows if "World Cup" in r.get("competition", "") and "2026" in str(r.get("season", "")))
    if wc_2026_in_historical > 0:
        fail(f"2026 data found in historical backtest dataset: {wc_2026_in_historical} rows")
    else:
        print(f"[PASS] No 2026 data in historical backtest dataset")

    # ── 8. Uncovered samples remain 1X2_ONLY ──
    for r in rows:
        if r.get("odds_extension_covered") != "True" and r.get("pipeline_mode") != "1X2_ONLY":
            fail(f"Row {r.get('match_date','')} {r.get('home_team_id','')}vs{r.get('away_team_id','')}: "
                 f"uncovered but pipeline_mode={r.get('pipeline_mode','')}")
    print(f"[PASS] Uncovered samples remain 1X2_ONLY")

    # ── 9. FULL only on rows with OU ladder ──
    for r in rows:
        if r.get("pipeline_mode") == "FULL":
            if r.get("ou_market_available") != "True":
                fail(f"Row {r.get('match_date','')} marked FULL but ou_market_available={r.get('ou_market_available','')}")
    print(f"[PASS] FULL only on rows with OU ladder")

    # ── 10. w1_full_pipeline_validated_for_full_dataset=false ──
    full_validated = sum(1 for r in rows if r.get("w1_full_pipeline_validated") == "True" and r.get("pipeline_mode") == "FULL")
    if full_validated != 128:
        warn(f"Expected 128 FULL rows with w1_full_pipeline_validated=True, got {full_validated}")
    else:
        print(f"[PASS] w1_full_pipeline_validated on FULL subset: {full_validated}")

    # ── 11. data/local_odds/*.csv not git tracked ──
    repo = ROOT
    for csv_file in SNAPSHOT_DIR.glob("*.csv"):
        result = _git_ls(csv_file)
        if result:
            fail(f"data/local_odds/{csv_file.name} is git-tracked (should be gitignored)")
            break
    else:
        print(f"[PASS] data/local_odds/*.csv not git-tracked")

    # ── 12. data/processed/international/* not git tracked ──
    proc_tracked = _git_ls(EXT_PATH) or _git_ls(CUR_QUALITY)
    if proc_tracked:
        fail("data/processed/international/ files are git-tracked (should be gitignored)")
    else:
        print(f"[PASS] data/processed/international/* not git-tracked")

    # ── 13. Static guard: no external fetch in B1/B2 scripts (checkers excluded as they contain guard strings) ──
    new_scripts = [
        ROOT / "scripts/merge_w1_odds_extension.py",
        ROOT / "scripts/w1_backtest_full_pipeline.py",
    ]
    _forbidden_imports = ["import requests", "from urllib", "import urllib",
                          "from selenium", "import playwright", "web_fetch",
                          "http.client", "httpx", "aiohttp", "BeautifulSoup",
                          "from socket", "import socket"]
    for sp in new_scripts:
        if not sp.is_file():
            continue
        src = sp.read_text(encoding="utf-8")
        for fi in _forbidden_imports:
            if fi in src:
                fail(f"'{sp.name}' contains forbidden pattern '{fi}'")
    print(f"[PASS] All new scripts are free of external fetch imports")

    # ── Current snapshot quality exists ──
    if not CUR_QUALITY.is_file():
        fail(f"Current snapshot quality not found: {CUR_QUALITY}")
    else:
        cur = json.loads(CUR_QUALITY.read_text(encoding="utf-8"))
        if cur.get("historical_backtest_eligible") is not False:
            fail("current snapshot quality must set historical_backtest_eligible=false")
        print(f"[PASS] Current snapshot quality: historical_backtest_eligible=false")

    # ── Summary ──
    print(f"\n{'='*60}")
    print(f"CHECKER SUMMARY: {len(errors)} FAIL / {len(warns)} WARN")
    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
    if warns:
        for w in warns:
            print(f"  WARN: {w}")

    return 1 if errors else 0


def _git_ls(path: Path) -> bool:
    """Check if a file is tracked by git. Returns True if tracked."""
    import subprocess
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(path.relative_to(ROOT))],
        cwd=ROOT, capture_output=True, text=True, timeout=10
    )
    return result.returncode == 0


if __name__ == "__main__":
    raise SystemExit(main())
