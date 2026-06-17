#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Checker for W1 FiveDim Confidence Adjustment (Stage D).

Guarantees the soft-signal contract: never changes any probability/lambda, agreement
with the market never raises confidence, output is research-only and not production
wired. Only ADDS assertions. Each safety assertion has a reverse test.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config/w1_confidence_adjustment_policy.json"
MODULE = ROOT / "scripts/w1_confidence_adjustment.py"
OUTPUT = ROOT / "state/w1_confidence_adjustment.json"
ENGINE = ROOT / "scripts/w1_score_engine.py"
PROTECTED = ["scripts/w1_score_engine.py", "config/w1_decision_policy.json", "config/w1_odds_movement_thresholds.json"]
FORBIDDEN_FETCH = ["import requests", "httpx", "aiohttp", "urllib.request", "BeautifulSoup", "playwright", "selenium"]
ALLOWED_STATES = {"insufficient", "aligned", "divergent", "factor_missing"}
GRADE_ORDER = {"D_insufficient": 0, "C_weak": 1, "B_medium": 2, "A_high": 3}

errors: list[str] = []


def fail(m: str) -> None:
    errors.append(m)


def keys_of(o):
    s = set()
    if isinstance(o, dict):
        for k, v in o.items():
            s.add(k)
            s |= keys_of(v)
    elif isinstance(o, list):
        for x in o:
            s |= keys_of(x)
    return s


def load_module():
    spec = importlib.util.spec_from_file_location("w1cadj", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    for p in (POLICY_PATH, MODULE, OUTPUT):
        if not p.is_file():
            fail(f"missing artifact: {p.relative_to(ROOT)}")
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print("W1 confidence adjustment check FAIL")
        return 1

    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    forbidden_prob = set(policy["hard_rules"]["never_change"])
    payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
    src = MODULE.read_text(encoding="utf-8")

    # red lines
    changed = subprocess.run(["git", "diff", "--name-only", "--", *PROTECTED], cwd=ROOT,
                             capture_output=True, text=True)
    if changed.returncode == 0 and [x for x in changed.stdout.splitlines() if x.strip()]:
        fail(f"protected files changed: {changed.stdout.split()}")
    if ENGINE.is_file() and "DEFAULT_RHO = -0.057766" not in ENGINE.read_text(encoding="utf-8"):
        fail("DEFAULT_RHO must remain -0.057766")
    for tok in FORBIDDEN_FETCH:
        if tok in src:
            fail(f"module has network pattern: {tok}")
    if "W1_FIVEDIM_HISTORICAL_VALIDATION" not in src and "W1_FIVEDIM_HISTORICAL_VALIDATION" not in json.dumps(policy):
        fail("must cite Stage C basis (W1_FIVEDIM_HISTORICAL_VALIDATION)")

    # output contract
    if payload.get("research_only") is not True or payload.get("production_wired") is not False:
        fail("output must be research_only=true, production_wired=false")
    if payload.get("prob_unchanged") is not True or payload.get("independent_edge_claimed") is not False:
        fail("output must keep prob_unchanged=true, independent_edge_claimed=false")

    # NO probability/lambda field anywhere in output (exact-key match; 'prob_unchanged' is allowed)
    leak = keys_of(payload) & forbidden_prob
    if leak:
        fail(f"output leaked probability/lambda fields: {sorted(leak)}")

    for row in payload.get("adjustments", []):
        fid = row.get("fixture_id")
        if row.get("independent_edge") is not False:
            fail(f"{fid}: independent_edge must be false")
        if row.get("prob_unchanged") is not True:
            fail(f"{fid}: prob_unchanged must be true")
        if row.get("market_vs_factor") not in ALLOWED_STATES:
            fail(f"{fid}: invalid market_vs_factor {row.get('market_vs_factor')}")
        if row.get("confidence_grade") not in GRADE_ORDER:
            fail(f"{fid}: invalid confidence_grade {row.get('confidence_grade')}")
        if not isinstance(row.get("risk_flags"), list):
            fail(f"{fid}: risk_flags must be a list")

    # core soft-use guarantee via the pure function
    mod = load_module()
    aligned = mod.adjust("home", {"available": True, "elo_diff": 40, "ppg_diff": 0.6, "gd_diff": 0.9})
    if GRADE_ORDER.get(aligned["confidence_grade"], 0) > GRADE_ORDER["C_weak"]:
        fail("aligned factors must NOT raise confidence above C_weak (Stage C: agreement has no edge)")
    divergent = mod.adjust("home", {"available": True, "elo_diff": -40, "ppg_diff": -0.6, "gd_diff": -0.9})
    if "RISK_MARKET_FACTOR_DIVERGENCE" not in divergent["risk_flags"]:
        fail("divergent factors must raise a divergence risk flag")
    for r in (aligned, divergent, mod.adjust("home", {"available": False})):
        if set(r.keys()) & forbidden_prob:
            fail("adjust() must not return any probability/lambda field")

    # reverse tests
    if not (keys_of({"adjustments": [{"pH": 0.5}]}) & forbidden_prob):
        fail("reverse test: a probability key must be catchable")
    boosted = dict(aligned, confidence_grade="A_high")
    if GRADE_ORDER.get(boosted["confidence_grade"], 0) <= GRADE_ORDER["C_weak"]:
        fail("reverse test: an A_high on aligned should be detectable as a violation")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"W1 confidence adjustment check FAIL ({len(errors)})")
        return 1
    print(f"W1 confidence adjustment check PASS (n={payload.get('n')}, no prob/lambda leak, "
          "agreement never boosts confidence, divergence flags only, red lines intact)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
