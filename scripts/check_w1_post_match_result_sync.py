#!/usr/bin/env python3
"""Check W1 post-match batch result sync contract."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYNC = ROOT / "scripts/w1_result_sync.py"
RESULT_HELPER = ROOT / "scripts/w1_results_overlay.py"
BUILDER = ROOT / "scripts/build_w1_dashboard_data.py"
SERVER = ROOT / "scripts/w1_local_predict_server.py"
SCOUT_LEDGER = ROOT / "scripts/w1_scout_ledger.py"
SCOUT_REVIEW = ROOT / "scripts/w1_scout_review.py"
SCOPE = ROOT / "config/w1_competition_scope.json"
SCORE_ENGINE = ROOT / "scripts/w1_score_engine.py"
ODDS_THRESHOLDS = ROOT / "config/w1_odds_movement_thresholds.json"


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def read_json(path: Path) -> dict:
    if not path.is_file():
        fail(f"missing file: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def check_scope_and_sources() -> None:
    scope = read_json(SCOPE)
    if scope.get("results_overlay") != "data/results/world_cup_2026_results.json":
        fail("competition scope must point to world_cup_2026_results.json")
    if "data/results/round1_results.json" not in scope.get("legacy_results", []):
        fail("round1 legacy results compatibility missing")

    sync_source = SYNC.read_text(encoding="utf-8")
    required_sync = [
        'SCOPE_JSON = ROOT / "config/w1_competition_scope.json"',
        'api.get("/fixtures", id=fid)',
        "FINISHED_STATUS_SHORT = {\"FT\", \"AET\", \"PEN\"}",
        "dry_run",
        "api_called_count=0",
        "write_json(overlay_path, overlay)",
        "used_in_audit_review_calibration_only",
    ]
    for token in required_sync:
        if token not in sync_source:
            fail(f"result sync missing contract token: {token}")
    forbidden_sync = [
        "state/w1_scout_bundles.json",
        "state/w1_scout_calls.json",
        "state/scout_lock.jsonl",
        "w1_score_engine.py",
    ]
    for token in forbidden_sync:
        if token in sync_source:
            fail(f"result sync must not write/read pre-match runtime/engine target: {token}")

    builder = BUILDER.read_text(encoding="utf-8")
    if "configured_result_paths" not in builder or "world_cup_2026_results.json" not in json.dumps(scope):
        fail("builder must read configured result overlay")
    if 'RESULTS_JSON = ROOT / "data/results/round1_results.json"' in builder:
        fail("builder still hardcodes round1_results as only overlay")

    helper = RESULT_HELPER.read_text(encoding="utf-8")
    for token in (
        'SCOPE_JSON = ROOT / "config/w1_competition_scope.json"',
        "def configured_result_paths",
        "def load_results_map",
        'scope.get("legacy_results"',
        'scope.get("results_overlay")',
        "alias_fixture_ids",
    ):
        if token not in helper:
            fail(f"result helper missing token: {token}")

    server = SERVER.read_text(encoding="utf-8")
    if "results_overlay_path()" not in server or "iter_match_card_paths()" not in server:
        fail("local predict server must use competition scope for cards/results")

    for path in (SCOUT_LEDGER, SCOUT_REVIEW):
        source = path.read_text(encoding="utf-8")
        if 'RESULTS = ROOT / "data/results/round1_results.json"' in source:
            fail(f"{path.relative_to(ROOT)} still hardcodes round1_results.json")
        if "load_results_map" not in source:
            fail(f"{path.relative_to(ROOT)} must use shared load_results_map")
        if "data/results/round1_results.json" in source and "legacy" not in source:
            fail(f"{path.relative_to(ROOT)} must not directly read round1_results.json")


def check_dry_run_no_write() -> None:
    overlay = ROOT / "data/results/world_cup_2026_results.json"
    before = overlay.read_text(encoding="utf-8") if overlay.is_file() else None
    env = os.environ.copy()
    env["W1_DISABLE_API_ENV_BRIDGE"] = "1"
    proc = subprocess.run(
        [sys.executable, str(SYNC), "--dry-run"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        fail(f"w1_result_sync.py --dry-run failed: {proc.stderr or proc.stdout}")
    out = proc.stdout + proc.stderr
    if "api_called_count=0" not in out or "written_results=0" not in out:
        fail("result sync dry-run must report no API calls and no writes")
    after = overlay.read_text(encoding="utf-8") if overlay.is_file() else None
    if before != after:
        fail("result sync dry-run modified results overlay")


def check_guards_unchanged() -> None:
    score_source = SCORE_ENGINE.read_text(encoding="utf-8")
    if not re.search(r"DEFAULT_RHO\s*=\s*-0\.057766\b", score_source):
        fail("DEFAULT_RHO changed from -0.057766")
    thresholds = read_json(ODDS_THRESHOLDS)
    if thresholds.get("calibrated") != "none" or thresholds.get("tier") != "C":
        fail("odds movement thresholds changed from default Tier C / calibrated none")


def main() -> int:
    check_scope_and_sources()
    check_dry_run_no_write()
    check_guards_unchanged()
    print("PASS check_w1_post_match_result_sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
