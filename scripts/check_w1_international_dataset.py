#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 S1B data-integrity checker (consolidated).

Covers: schema/columns, 90-min score, finish_type (ET/Pens-derived) + dirty
`Finished` location, 1X2/OU/AH availability + pipeline_mode, xG/stats coverage,
domain split. Skips cleanly if the (gitignored) dataset has not been generated.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data/processed/international/w1_international_dataset.csv"
COV = ROOT / "data/processed/international/w1_international_coverage.json"
REQUIRED_COLS = [
    "source_sheet", "phase", "stage", "neutral_site", "home_team_id", "away_team_id",
    "home_goals_90", "away_goals_90", "finish_type", "dirty_finished_label",
    "home_penalties", "away_penalties", "odds_1x2_home", "odds_1x2_available",
    "ou_market_available", "ah_market_available", "xg_available", "stats_available",
    "pipeline_mode", "w1_full_pipeline_validated",
]
errors: list[str] = []


def fail(m: str) -> None:
    errors.append(m)


def main() -> int:
    if not CSV_PATH.is_file():
        print("SKIP check_w1_international_dataset: dataset not generated (run normalize_w1_international_dataset.py)")
        return 0
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    cov = json.loads(COV.read_text(encoding="utf-8")) if COV.is_file() else {}

    header = rows[0].keys() if rows else []
    for c in REQUIRED_COLS:
        if c not in header:
            fail(f"missing column: {c}")
    if cov and len(rows) != cov.get("total_rows"):
        fail(f"row count {len(rows)} != coverage total_rows {cov.get('total_rows')}")
    sheets = {r["source_sheet"] for r in rows}
    if len(sheets) != 4:
        fail(f"expected 4 source sheets, found {sorted(sheets)}")

    for r in rows:
        if r["pipeline_mode"] != "1X2_ONLY":
            fail(f"{r['home_name_raw']} vs {r['away_name_raw']}: pipeline_mode must be 1X2_ONLY"); break
    for r in rows:
        if r["w1_full_pipeline_validated"] != "False":
            fail("w1_full_pipeline_validated must be False everywhere"); break
    if any(r["ou_market_available"] != "False" or r["ah_market_available"] != "False" for r in rows):
        fail("OU/AH must be marked unavailable in this source")
    if any(r["finish_type"] not in ("regulation", "extra_time", "penalties") for r in rows):
        fail("invalid finish_type present")
    # result rows must have 90-min score
    for r in rows:
        if r["result_available"] == "True" and (r["home_goals_90"] == "" or r["away_goals_90"] == ""):
            fail(f"{r['home_name_raw']} vs {r['away_name_raw']}: result row missing 90-min score"); break
    # dirty finished labels located
    dirty = sum(1 for r in rows if r["dirty_finished_label"] == "True")
    if dirty == 0:
        fail("expected to locate dirty Finished labels (2022) but found none")

    # informational coverage (not a failure)
    print(f"coverage: rows={len(rows)} sheets={sorted(sheets)} "
          f"xG_qual={cov.get('xg_available_qualifiers')}/{cov.get('qualifier_rows')} "
          f"stats={cov.get('stats_available_total')} fouls={cov.get('fouls_available_total')} "
          f"dirty_finished={dirty} OU={cov.get('ou_market_available')} AH={cov.get('ah_market_available')}")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"W1 international dataset check FAIL ({len(errors)})")
        return 1
    print("W1 international dataset check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
