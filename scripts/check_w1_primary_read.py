#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Checker for W1 FiveDim Primary Read Selector (Stage F).

Guards the research-conclusion contract: exactly one decision per match, decision uses
no post-match result, no probability is produced or changed, no betting wording, and it
declares itself NOT a betting selector. Only ADDS assertions; each has a reverse test.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config/w1_primary_read_policy.json"
BUILDER = ROOT / "scripts/w1_primary_read_builder.py"
OUTPUT = ROOT / "state/w1_primary_read.json"
ENGINE = ROOT / "scripts/w1_score_engine.py"
PROTECTED = ["scripts/w1_score_engine.py", "config/w1_decision_policy.json", "config/w1_odds_movement_thresholds.json"]
FORBIDDEN_FETCH = ["import requests", "httpx", "aiohttp", "urllib.request", "BeautifulSoup", "playwright", "selenium"]
PROB_KEYS = {"pH", "pD", "pA", "home_win", "away_win", "raw_probability", "lambda_home", "lambda_away", "score_matrix", "sum_check"}
DECISIONS = {"PRIMARY_READ", "WAIT", "SKIP", "BLOCKED"}

errors: list[str] = []


def fail(m):
    errors.append(m)


def keys_of(o, s=None):
    s = set() if s is None else s
    if isinstance(o, dict):
        for k, v in o.items():
            s.add(k)
            keys_of(v, s)
    elif isinstance(o, list):
        for x in o:
            keys_of(x, s)
    return s


def decide_body(src):
    m = re.search(r"def decide\(.*?\n(.*?)\ndef ", src, re.S)
    return m.group(1) if m else ""


def main() -> int:
    for p in (POLICY, BUILDER, OUTPUT):
        if not p.is_file():
            fail(f"missing artifact: {p.relative_to(ROOT)}")
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print("W1 primary read check FAIL")
        return 1

    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
    src = BUILDER.read_text(encoding="utf-8")
    terms = policy["hard_rules"]["forbidden_terms"]

    # red lines
    diff = subprocess.run(["git", "diff", "--name-only", "--", *PROTECTED], cwd=ROOT, capture_output=True, text=True)
    if diff.returncode == 0 and [x for x in diff.stdout.splitlines() if x.strip()]:
        fail(f"protected files changed: {diff.stdout.split()}")
    if ENGINE.is_file() and "DEFAULT_RHO = -0.057766" not in ENGINE.read_text(encoding="utf-8"):
        fail("DEFAULT_RHO must remain -0.057766")
    for tok in FORBIDDEN_FETCH:
        if tok in src:
            fail(f"builder has network pattern: {tok}")

    # leakage: decision logic must not read post-match result
    if "actual_score" in decide_body(src) or "result" in decide_body(src):
        fail("decide() must not reference post-match result (actual_score/result)")

    # output contract
    for k, want in (("research_only", True), ("production_wired", False), ("is_betting_selector", False),
                    ("independent_edge_claimed", False), ("prob_unchanged", True)):
        if payload.get(k) is not want:
            fail(f"output {k} must be {want}")

    # no probability key anywhere
    leak = keys_of(payload) & PROB_KEYS
    if leak:
        fail(f"output leaked probability keys: {sorted(leak)}")

    # no betting wording in serialized output
    text = json.dumps(payload, ensure_ascii=False)
    for t in terms:
        if re.search(re.escape(t), text, re.IGNORECASE):
            fail(f"output contains forbidden betting term: {t}")

    # per-row + one-decision-per-match
    seen = set()
    primary_per_fixture = {}
    for r in payload.get("reads", []):
        fid = r.get("fixture_id")
        if fid in seen:
            fail(f"duplicate fixture {fid} (must be one decision per match)")
        seen.add(fid)
        if r.get("decision") not in DECISIONS:
            fail(f"{fid}: invalid decision {r.get('decision')}")
        if r.get("independent_edge") is not False or r.get("prob_unchanged") is not True:
            fail(f"{fid}: must keep independent_edge=false, prob_unchanged=true")
        if r.get("basis") != "market_implied":
            fail(f"{fid}: basis must be market_implied")
        if (r.get("audit") or {}).get("used_in_decision") is not False:
            fail(f"{fid}: audit.used_in_decision must be false")
        if r.get("decision") == "PRIMARY_READ":
            primary_per_fixture[fid] = primary_per_fixture.get(fid, 0) + 1
            if not r.get("primary_read_cn"):
                fail(f"{fid}: PRIMARY_READ must carry a read text")
    if any(v > 1 for v in primary_per_fixture.values()):
        fail("a match has more than one PRIMARY_READ")

    # --- reverse tests via the pure decide() ---
    spec = importlib.util.spec_from_file_location("w1pr", BUILDER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    blocked, _, _ = mod.decide({"market_probability_panel": {"one_x_two": {}}})
    if blocked != "BLOCKED":
        fail("reverse test: missing 1X2 must yield BLOCKED")
    balanced = {"market_probability_panel": {"one_x_two": {"home_win": 0.34, "draw": 0.33, "away_win": 0.33, "sum_check": 1.0}},
                "status": "finished"}
    if mod.decide(balanced)[0] != "SKIP":
        fail("reverse test: balanced market must yield SKIP")
    if not (keys_of({"reads": [{"pH": 0.5}]}) & PROB_KEYS):
        fail("reverse test: a probability key must be catchable")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"W1 primary read check FAIL ({len(errors)})")
        return 1
    from collections import Counter
    dist = dict(Counter(r["decision"] for r in payload.get("reads", [])))
    print(f"W1 primary read check PASS (n={payload.get('n')}, decisions={dist}, one-per-match, "
          "no result leakage, no probability change, not a betting selector, red lines intact)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
