#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1_FORWARD_LEDGER_PROSPECTIVE_RUN_V1 checker.

Validates the prospective pre-match -> post-match loop. Skip-safe: if the
pre_match_view store is absent (fresh clone / not run yet), SKIP with the rebuild
command instead of failing.

Asserts:
  * pre_match_view is immutable / write-once per fixture; lock_as_of_utc present and
    <= kickoff_utc (genuine prospective, no hindsight); locked 1X2 sums ~1; no
    post-match (forbidden) field present in a view.
  * post_match_audit references an existing view; its locked_prediction EQUALS the
    view's (immutability — post-match never altered the pre-match prediction);
    lock_as_of <= kickoff; result.source is the local facts ledger.
  * stores are gitignored (data/forward_ledger/) and not tracked.
  * new scripts contain no external-fetch imports; no affirmative betting/money/
    hit-rate language in scripts/schema.
  * production red lines untouched: engine / DEFAULT_RHO / decision_policy / odds
    thresholds have no git diff.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import w1_candidate_builder as CAND  # noqa: E402
VIEW = ROOT / "data/forward_ledger/w1_pre_match_view.jsonl"
AUDIT = ROOT / "data/forward_ledger/w1_post_match_audit.jsonl"
SCHEMA = ROOT / "config/w1_prospective_audit_schema.json"
GITIGNORE = ROOT / ".gitignore"
ENGINE = ROOT / "scripts/w1_score_engine.py"
NEW_SCRIPTS = [
    ROOT / "scripts/w1_forward_lock_pre_match_view.py",
    ROOT / "scripts/w1_forward_post_match_audit.py",
    ROOT / "scripts/w1_forward_prospective_report.py",
]
PROTECTED = [
    "scripts/w1_score_engine.py",
    "config/w1_decision_policy.json",
    "config/w1_odds_movement_thresholds.json",
]
STORES_MUST_BE_UNTRACKED = [
    "data/forward_ledger/w1_pre_match_view.jsonl",
    "data/forward_ledger/w1_post_match_audit.jsonl",
    "data/forward_ledger/w1_prospective_calibration_v1.json",
]
FORBIDDEN_ASCII = ["bet", "stake", "profit", "guaranteed", "roi"]
FORBIDDEN_CN = ["建议下注", "推荐投注", "稳赚", "必胜", "保证命中", "资金分配"]
FORBIDDEN_FETCH = ["import requests", "from urllib", "import urllib", "httpx", "aiohttp",
                   "from selenium", "playwright", "BeautifulSoup", "web_fetch", "import socket", "from socket"]
REBUILD = ("python3 scripts/w1_forward_lock_pre_match_view.py && "
           "python3 scripts/w1_forward_post_match_audit.py && "
           "python3 scripts/w1_forward_prospective_report.py")

errors: list[str] = []


def fail(m: str) -> None:
    errors.append(m)


def dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def tracked(rel: str) -> bool:
    return subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=ROOT,
                          capture_output=True, text=True).returncode == 0


def git_diff(paths: list[str]) -> list[str]:
    r = subprocess.run(["git", "diff", "--name-only", "--", *paths], cwd=ROOT, capture_output=True, text=True)
    return [x for x in r.stdout.splitlines() if x.strip()] if r.returncode == 0 else []


def scan_forbidden(text: str, label: str) -> None:
    for t in FORBIDDEN_ASCII:
        if re.search(rf"(?<![A-Za-z]){re.escape(t)}(?![A-Za-z])", text, re.I):
            fail(f"{label}: affirmative forbidden term '{t}'")
    for t in FORBIDDEN_CN:
        if t in text:
            fail(f"{label}: forbidden term '{t}'")


def main() -> int:
    if not SCHEMA.is_file():
        fail("config/w1_prospective_audit_schema.json missing")
    if not VIEW.is_file():
        print("SKIP check_w1_forward_prospective_run: pre_match_view not generated yet")
        print(f"  rebuild: {REBUILD}")
        return 1 if errors else 0

    schema = json.loads(SCHEMA.read_text(encoding="utf-8")) if SCHEMA.is_file() else {}
    forbidden_fields = set(schema.get("forbidden_fields_in_pre_match_view", []))

    # ── pre_match_view ──
    views: dict[str, dict[str, Any]] = {}
    for i, line in enumerate(VIEW.open(encoding="utf-8"), 1):
        if not line.strip():
            continue
        v = json.loads(line)
        fid = str(v.get("fixture_id"))
        if fid in views:
            fail(f"pre_match_view line {i}: duplicate fixture_id {fid} (must be write-once/immutable)")
        if forbidden_fields.intersection(v.keys()):
            fail(f"pre_match_view {fid}: LEAKAGE — post-match field(s) {sorted(forbidden_fields.intersection(v.keys()))}")
        lock, ko = dt(v.get("lock_as_of_utc")), dt(v.get("kickoff_utc"))
        if not v.get("lock_as_of_utc"):
            fail(f"pre_match_view {fid}: missing lock_as_of_utc")
        if ko is not None and (lock is None or lock > ko):
            fail(f"pre_match_view {fid}: lock_as_of_utc must be <= kickoff (no hindsight): {v.get('lock_as_of_utc')} > {v.get('kickoff_utc')}")
        pred = v.get("locked_prediction", {})
        s = sum(pred.get(k, 0) for k in ("p_home", "p_draw", "p_away"))
        if not (0.98 <= s <= 1.02):
            fail(f"pre_match_view {fid}: locked 1X2 must sum ~1, got {s}")
        cand = v.get("candidates_snapshot")
        if cand:
            for err in CAND.validate_candidates(cand):
                fail(f"pre_match_view {fid}: candidates_snapshot invalid: {err}")
        views[fid] = v

    # ── post_match_audit ──
    if AUDIT.is_file():
        for i, line in enumerate(AUDIT.open(encoding="utf-8"), 1):
            if not line.strip():
                continue
            a = json.loads(line)
            fid = str(a.get("fixture_id"))
            if fid not in views:
                fail(f"post_match_audit line {i}: references unknown pre_match_view {fid}")
                continue
            if a.get("locked_prediction") != views[fid].get("locked_prediction"):
                fail(f"post_match_audit {fid}: locked_prediction differs from view (immutability violated)")
            lock, ko = dt(a.get("lock_as_of_utc")), dt(a.get("kickoff_utc"))
            if ko is not None and (lock is None or lock > ko):
                fail(f"post_match_audit {fid}: lock_as_of must be <= kickoff (no hindsight)")
            if "prospective_calibration" not in a or "result" not in a:
                fail(f"post_match_audit {fid}: missing result/prospective_calibration")
            if a.get("result", {}).get("source") != "local_round1_results":
                fail(f"post_match_audit {fid}: result.source must be local_round1_results (no external fetch)")

    # ── gitignore + tracking ──
    gi = GITIGNORE.read_text(encoding="utf-8") if GITIGNORE.is_file() else ""
    if "data/forward_ledger/" not in gi:
        fail(".gitignore must ignore data/forward_ledger/ (prospective stores)")
    for rel in STORES_MUST_BE_UNTRACKED:
        if tracked(rel):
            fail(f"prospective store must not be tracked (gitignored): {rel}")

    # ── new scripts: no external fetch; no affirmative betting language ──
    for sp in NEW_SCRIPTS:
        if sp.is_file():
            src = sp.read_text(encoding="utf-8")
            for fi in FORBIDDEN_FETCH:
                if fi in src:
                    fail(f"{sp.name}: contains external-fetch pattern '{fi}'")
            scan_forbidden(src, sp.name)
    if SCHEMA.is_file():
        scan_forbidden(SCHEMA.read_text(encoding="utf-8"), "schema")

    # ── red lines ──
    changed = git_diff(PROTECTED)
    if changed:
        fail(f"production red-line files changed (must not): {changed}")
    if ENGINE.is_file() and "DEFAULT_RHO = -0.057766" not in ENGINE.read_text(encoding="utf-8"):
        fail("DEFAULT_RHO changed from -0.057766")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"W1 forward prospective run check FAIL ({len(errors)})")
        return 1
    print(f"W1 forward prospective run check PASS "
          f"(views={len(views)} immutable/pre-kickoff; audits reference & match views; stores gitignored; production untouched)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
