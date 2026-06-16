#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate W1_OPPORTUNITY_SELECTOR_PHASE_A.

The stage is a read-only candidate unification and view-separation layer. It must
not become a selector, calibration layer, or production model change.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import w1_candidate_builder as CAND  # noqa: E402

DASH = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
OFFLINE_JSON = ROOT / "reports/w1_candidate_offline_eval_v1.json"
OFFLINE_MD = ROOT / "reports/w1_candidate_offline_eval_v1.md"
SCHEMA = ROOT / "config/w1_prospective_audit_schema.json"
ENGINE = ROOT / "scripts/w1_score_engine.py"
PROTECTED = [
    "scripts/w1_score_engine.py",
    "config/w1_decision_policy.json",
    "config/w1_odds_movement_thresholds.json",
]
PHASE_FILES = [
    ROOT / "scripts/w1_candidate_builder.py",
    ROOT / "scripts/w1_candidate_offline_eval.py",
    ROOT / "scripts/check_w1_opportunity_phase_a.py",
    OFFLINE_JSON,
    OFFLINE_MD,
    ROOT / "reports/W1_OPPORTUNITY_SELECTOR_PHASE_A_RESULT.md",
]
FORBIDDEN_FETCH = ["import requests", "httpx", "aiohttp", "urllib.request", "BeautifulSoup", "playwright", "selenium"]
FORBIDDEN_WORDS = [
    "TOP_PICK",
    "opportunity_score",
    "selector_score",
    "建议下注",
    "推荐投注",
    "资金建议",
    "稳赚",
    "必胜",
    "保证命中",
    "盈利承诺",
]

errors: list[str] = []


def fail(message: str) -> None:
    errors.append(message)


def git_diff(paths: list[str]) -> list[str]:
    proc = subprocess.run(["git", "diff", "--name-only", "--", *paths], cwd=ROOT, capture_output=True, text=True)
    return [x for x in proc.stdout.splitlines() if x.strip()] if proc.returncode == 0 else []


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def group_items(items: list[dict[str, Any]], market: str, line: float | None = None) -> list[dict[str, Any]]:
    rows = [item for item in items if item.get("market") == market]
    if line is not None:
        rows = [item for item in rows if abs(float(item.get("line", 999)) - line) < 1e-9]
    return rows


def assert_candidates(row: dict[str, Any]) -> None:
    fid = row.get("fixture_id")
    payload = row.get("candidates_snapshot")
    if not isinstance(payload, dict):
        fail(f"fixture {fid}: candidates_snapshot missing")
        return
    for err in CAND.validate_candidates(payload):
        fail(f"fixture {fid}: {err}")
    if payload.get("status") != "ready":
        fail(f"fixture {fid}: candidates_snapshot not ready")
    items = payload.get("items", [])
    markets = {item.get("market") for item in items}
    for market in ("1X2", "OU", "AH", "BTTS", "score_pool"):
        if market not in markets:
            fail(f"fixture {fid}: missing market candidates {market}")

    hda = group_items(items, "1X2")
    if abs(sum(float(x["raw_probability"]) for x in hda) - 1.0) > 0.01:
        fail(f"fixture {fid}: 1X2 probabilities do not sum ~1")
    btts = group_items(items, "BTTS")
    if abs(sum(float(x["raw_probability"]) for x in btts) - 1.0) > 0.01:
        fail(f"fixture {fid}: BTTS probabilities do not sum ~1")
    for line in sorted({float(x["line"]) for x in items if x.get("market") == "OU" and x.get("line") is not None}):
        ou = group_items(items, "OU", line)
        push = max(float(x.get("push_probability") or 0.0) for x in ou) if ou else 0.0
        if abs(sum(float(x["raw_probability"]) for x in ou) + push - 1.0) > 0.02:
            fail(f"fixture {fid}: OU line {line} not self-consistent")
    for line in sorted({float(x["line"]) for x in items if x.get("market") == "AH" and x.get("line") is not None}):
        home = [x for x in items if x.get("market") == "AH" and x.get("selection") == "home_cover" and abs(float(x["line"]) - line) < 1e-9]
        away = [x for x in items if x.get("market") == "AH" and x.get("selection") == "away_cover" and abs(float(x["line"]) + line) < 1e-9]
        if home and away:
            push = float(home[0].get("push_probability") or 0.0)
            if abs(float(home[0]["raw_probability"]) + float(away[0]["raw_probability"]) + push - 1.0) > 0.02:
                fail(f"fixture {fid}: AH line {line} not self-consistent")


def scan_text_boundaries() -> None:
    for path in PHASE_FILES:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if path.name != "check_w1_opportunity_phase_a.py":
            for token in FORBIDDEN_FETCH:
                if token in text:
                    fail(f"{path.relative_to(ROOT)} contains external-fetch pattern {token}")
        if path.name != "check_w1_opportunity_phase_a.py":
            for token in FORBIDDEN_WORDS:
                if token in text:
                    fail(f"{path.relative_to(ROOT)} contains forbidden Phase A wording {token}")
            if re.search(r"calibrated['\"]?\s*:\s*True", text):
                fail(f"{path.relative_to(ROOT)} appears to set calibrated=true")


def main() -> int:
    for path in (DASH, HTML, OFFLINE_JSON, OFFLINE_MD, SCHEMA):
        if not path.is_file():
            fail(f"missing required artifact: {path.relative_to(ROOT)}")

    changed = git_diff(PROTECTED)
    if changed:
        fail(f"production red-line files changed: {changed}")
    if ENGINE.is_file() and "DEFAULT_RHO = -0.057766" not in ENGINE.read_text(encoding="utf-8"):
        fail("DEFAULT_RHO must remain -0.057766")

    if DASH.is_file():
        data = load(DASH)
        records = data.get("match_records", [])
        if len(records) < 24:
            fail("dashboard records must include at least 24 matches")
        for row in records:
            assert_candidates(row)

    if OFFLINE_JSON.is_file():
        report = load(OFFLINE_JSON)
        if report.get("stage") != "W1_OPPORTUNITY_SELECTOR_PHASE_A":
            fail("offline eval stage mismatch")
        if report.get("research_only") is not True or report.get("production_wired") is not False:
            fail("offline eval must be research_only=true and production_wired=false")
        if report.get("calibrated") is not False or report.get("basis") != CAND.BASIS:
            fail("offline eval must remain uncalibrated and matrix-based")
        if report.get("n_matches") != 128:
            fail(f"offline eval FULL subset expected n=128, got {report.get('n_matches')}")

    if HTML.is_file():
        html = HTML.read_text(encoding="utf-8")
        for token in ("function pCandidateConsensus", "function pCandidateExpert", "候选共识", "非独立优势", "非推介", CAND.BASIS):
            if token not in html:
                fail(f"HTML missing candidate view token: {token}")
        for token in ("TOP_PICK", "opportunity_score", "selector_score"):
            if token in html:
                fail(f"HTML contains forbidden single-selection token {token}")

    # Reverse check: flipping either flag must fail validation.
    bad = {
        "basis": CAND.BASIS,
        "independent_edge": False,
        "calibrated": False,
        "items": [
            {
                "market": "1X2",
                "selection": "home_win",
                "line": None,
                "raw_probability": 0.5,
                "expected_result_score": 0.5,
                "basis": CAND.BASIS,
                "independent_edge": True,
                "calibrated": False,
            }
        ],
    }
    if not CAND.validate_candidates(bad):
        fail("reverse validation must reject independent_edge=true")

    scan_text_boundaries()

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        print(f"W1 opportunity phase A check FAIL ({len(errors)})")
        return 1
    print("W1 opportunity phase A check PASS (read-only candidates, view separation, red lines intact)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
