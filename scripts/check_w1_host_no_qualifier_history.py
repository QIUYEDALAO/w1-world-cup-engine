#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 S1B host-no-qualifier-history checker (WARN / model-gating, not BLOCKER).

2026 hosts (USA/Mexico/Canada) auto-qualified -> no qualifier history in the seed
set. This does NOT block ingestion, but it WARNs and should gate formal S2
acceptance for host teams (their strength must come from friendlies/Elo, not 0
qualifiers).
"""
from __future__ import annotations

import collections
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALIASES = ROOT / "config/w1_team_aliases.json"
CSV_PATH = ROOT / "data/processed/international/w1_international_dataset.csv"


def main() -> int:
    if not ALIASES.is_file():
        print("FAIL: aliases missing", file=sys.stderr)
        return 1
    teams = json.loads(ALIASES.read_text(encoding="utf-8")).get("teams", {})
    hosts = {tid for tid, e in teams.items() if e.get("host_auto_qualified_2026")}
    for need in ("usa", "mexico", "canada"):
        if need not in hosts:
            print(f"FAIL: host {need} not flagged host_auto_qualified_2026", file=sys.stderr)
            return 1

    if not CSV_PATH.is_file():
        print("SKIP host-no-qualifier check: dataset not generated; hosts flagged in aliases OK")
        return 0

    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    qual = collections.Counter()
    last = {}
    for r in rows:
        for side in ("home", "away"):
            tid = r[f"{side}_team_id"]
            if r["phase"] == "qualifier":
                qual[tid] += 1
            if r.get("match_date"):
                last[tid] = max(last.get(tid, ""), r["match_date"])
    print("W1 host-no-qualifier-history report (WARN; gates formal S2 for hosts):")
    for h in sorted(hosts):
        nm = teams[h]["canonical_name"]
        q = qual.get(h, 0)
        flag = "WARN no qualifier history" if q == 0 else "ok"
        print(f"  - {nm} ({h}): qualifier_matches={q} last_match={last.get(h, '–')} -> {flag}")
    print("host check PASS (report-only; not a blocker)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
