#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 OU/AH coverage-probe checker.

Confirms the probe stays coverage-only: external_fetch_performed=false,
data_collected=false, and NO fetched odds values are present (no per-match OU/AH
odds rows). Also static-guards the probe script against any network/fetch import.
Skips if the (gitignored-dataset-derived) probe report is absent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/w1_ou_coverage_probe_v1.json"
SCRIPT = ROOT / "scripts/probe_w1_ou_coverage.py"
errors: list[str] = []


def fail(m: str) -> None:
    errors.append(m)


def main() -> int:
    if SCRIPT.is_file():
        src = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("requests", "urllib", "http.client", "httpx", "aiohttp", "socket", "web_fetch", "BeautifulSoup", "selenium"):
            if forbidden in src:
                fail(f"probe must not perform external fetch: found '{forbidden}'")
    else:
        fail("probe script missing")

    if not REPORT.is_file():
        if errors:
            for e in errors:
                print(f"FAIL: {e}", file=sys.stderr)
            return 1
        print("SKIP check_w1_ou_coverage: probe report not generated (run probe_w1_ou_coverage.py)")
        return 0

    p = json.loads(REPORT.read_text(encoding="utf-8"))
    if p.get("external_fetch_performed") is not False:
        fail("external_fetch_performed must be false")
    if p.get("data_collected") is not False:
        fail("data_collected must be false")
    # coverage-only: must not contain fetched odds values
    blob = json.dumps(p, ensure_ascii=False)
    for k in ("over_odds", "under_odds", "ah_odds", "ou_line_value", "fetched_odds"):
        if k in blob:
            fail(f"probe report contains fetched-odds field '{k}' (must be coverage-only)")
    if "totals" not in p or "ou_gap" not in p.get("totals", {}):
        fail("probe report missing coverage totals/ou_gap")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"W1 OU coverage probe check FAIL ({len(errors)})")
        return 1
    print("W1 OU coverage probe check PASS (coverage-only, no external fetch)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
