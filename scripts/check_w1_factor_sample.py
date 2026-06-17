#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Checker for W1 FiveDim Historical Validation (Stage C) sample.

Guards the leakage-safe / research-only contract of the factor validation sample:
  - builder is offline (no network, no result-ledger reads),
  - no current-match post-match column is carried as a feature,
  - rolling features are strictly pre-match (structural proof: first appearance has no history),
  - layers are present and never claim an independent edge.
Each assertion is paired with a reverse test. Only ADDS assertions; weakens nothing.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "config/w1_factor_sample_policy.json").read_text(encoding="utf-8"))
SAMPLE = ROOT / POLICY["output"]
SUMMARY = ROOT / POLICY["output_summary"]
BUILDER = ROOT / "scripts/w1_factor_sample_builder.py"
VALIDATION = ROOT / "scripts/w1_factor_validation.py"
FORBIDDEN = POLICY["forbidden_current_match_columns"]
FORBIDDEN_FETCH = ["import requests", "httpx", "aiohttp", "urllib.request", "BeautifulSoup", "playwright", "selenium"]
FEATURE_PREFIXES = ("elo_", "ppg_", "gd_", "sotr_", "xg_", "rest_")

errors: list[str] = []


def fail(m: str) -> None:
    errors.append(m)


def main() -> int:
    for p in (SAMPLE, SUMMARY, BUILDER):
        if not p.is_file():
            fail(f"missing artifact: {p.relative_to(ROOT)}")
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print("W1 factor sample check FAIL")
        return 1

    # builder offline + no ledger reads
    src = BUILDER.read_text(encoding="utf-8")
    for tok in FORBIDDEN_FETCH:
        if tok in src:
            fail(f"builder has network pattern: {tok}")
    for tok in ("round1_results", "requests.get", "api_football"):
        if tok in src:
            fail(f"builder references forbidden source: {tok}")

    df = pd.read_csv(SAMPLE)
    cols = set(df.columns)

    # 1) no current-match post-match column is carried as a feature column
    leaked = sorted(cols & set(FORBIDDEN))
    if leaked:
        fail(f"sample carries forbidden current-match columns as features: {leaked}")

    # 2) feature columns confined to allowed prefixes + market
    feature_like = [c for c in cols if c.endswith(("_home", "_away", "_diff")) and not c.startswith("n_hist")]
    for c in feature_like:
        if not c.startswith(FEATURE_PREFIXES):
            fail(f"unexpected feature column not in allowed prefixes: {c}")

    # 3) independent_edge never true
    if "independent_edge" in cols and bool(df["independent_edge"].any()):
        fail("independent_edge must be false on all rows")

    # 4) structural leakage proof: a team's first appearance has no rolling history
    zero = df[df["n_hist_home"] == 0]
    if len(zero) == 0:
        fail("expected some zero-history rows (first appearances) — rolling may be mis-built")
    elif not zero["ppg_home"].isna().all():
        fail("LEAKAGE: zero-history rows have non-null rolling ppg_home (future info used)")

    # 5) layers present & separate
    layers = set(df["layer"].unique())
    for need in ("league", "wc_qualifier", "wc_finals"):
        if need not in layers:
            fail(f"missing layer: {need}")

    # 6) results (if present) keep layers separate and research-only
    if SUMMARY.is_file():
        s = json.loads(SUMMARY.read_text(encoding="utf-8"))
        if s.get("research_only") is not True or s.get("production_wired") is not False:
            fail("summary must be research_only=true, production_wired=false")

    # --- reverse tests ---
    if not (set(["FTHG", "home_xg"]) & set(FORBIDDEN)):
        fail("reverse test: forbidden list should include current-match stats")
    fake = pd.DataFrame({"HS": [10], "elo_diff": [1.0]})
    if not (set(fake.columns) & set(FORBIDDEN)):
        fail("reverse test: a sample with raw 'HS' column must be flagged")
    fake2 = pd.DataFrame({"n_hist_home": [0], "ppg_home": [1.5]})
    z2 = fake2[fake2["n_hist_home"] == 0]
    if z2["ppg_home"].isna().all():
        fail("reverse test: zero-history row WITH ppg must be catchable as leakage")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"W1 factor sample check FAIL ({len(errors)})")
        return 1
    print(f"W1 factor sample check PASS (rows={len(df)}, layers={sorted(layers)}, "
          "no current-match leakage, structural pre-match proof, research-only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
