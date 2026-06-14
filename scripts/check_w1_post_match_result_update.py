#!/usr/bin/env python3
"""Validate W1 Australia vs Turkey post-match result update."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data/results/round1_results.json"
ALIASES = ROOT / "data/fixture_aliases.json"
DASHBOARD = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
BUILD = ROOT / "scripts/build_w1_dashboard_data.py"
SCORE_ENGINE = ROOT / "scripts/w1_score_engine.py"
DECISION_POLICY = ROOT / "config/w1_decision_policy.json"
FORBIDDEN = ["建议下注", "推荐投注", "稳赚", "必胜", "保证命中", "bet", "stake", "profit", "guaranteed"]


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_no_forbidden(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for term in FORBIDDEN:
        pattern = rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])" if term.isascii() else re.escape(term)
        if re.search(pattern, text, re.I):
            fail(f"{path.relative_to(ROOT)} contains forbidden term: {term}")


def assert_results_file() -> None:
    data = read_json(RESULTS)
    result = data.get("results", {}).get("1539001")
    if not result:
        fail("results missing fixture_id=1539001")
    expected = {
        "fixture_id": "1539001",
        "home_team": "Australia",
        "away_team": "Turkey",
        "actual_score": "2-0",
        "status": "complete",
        "source": "manual_result",
    }
    for key, value in expected.items():
        if result.get(key) != value:
            fail(f"result {key} mismatch: {result.get(key)}")
    if "66456942" not in result.get("alias_fixture_ids", []):
        fail("result must include alias_fixture_ids 66456942")
    if "澳大利亚 2-0 土耳其" not in " ".join(result.get("notes_cn", [])):
        fail("result notes must mention Australia 2-0 Turkey in Chinese")
    aliases = read_json(ALIASES)
    if aliases.get("1539001") != "66456942" or aliases.get("66456942") != "1539001":
        fail("fixture alias mapping must include 1539001 <-> 66456942")


def assert_no_single_match_weight_logic() -> None:
    build = BUILD.read_text(encoding="utf-8")
    bad_patterns = [
        r"if\s+fid\s*==",
        r"fixture_id\s*==",
        r"1539001.*weight",
        r"66456942.*weight",
        r"Australia.*weight",
        r"Turkey.*weight",
        r"1539001.*rho",
        r"66456942.*rho",
        r"Australia.*rho",
        r"Turkey.*rho",
    ]
    for pattern in bad_patterns:
        if re.search(pattern, build):
            fail(f"build script appears to contain single-match model logic: {pattern}")
    score_engine = SCORE_ENGINE.read_text(encoding="utf-8")
    for token in ("1539001", "66456942", "Australia", "Turkey"):
        if token in score_engine:
            fail(f"score engine must not contain post-match fixture/team hardcode: {token}")
    policy = DECISION_POLICY.read_text(encoding="utf-8")
    for token in ("1539001", "66456942", "Australia", "Turkey"):
        if token in policy:
            fail(f"PLAY_GUARD policy must not contain post-match fixture/team hardcode: {token}")


def assert_dashboard_calibration() -> None:
    result = subprocess.run([sys.executable, str(BUILD)], cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        fail(f"build_w1_dashboard_data.py failed: {result.stderr or result.stdout}")
    data = read_json(DASHBOARD)
    row = next((item for item in data.get("match_records", []) if item.get("fixture_id") == "1539001"), None)
    if not row:
        fail("dashboard missing fixture_id=1539001")
    if row.get("status") != "finished":
        fail(f"dashboard fixture_id=1539001 status must be finished, got {row.get('status')}")
    if row.get("actual_score") != {"home": 2, "away": 0}:
        fail(f"dashboard fixture_id=1539001 actual_score mismatch: {row.get('actual_score')}")
    if row.get("result_source") != "manual_result":
        fail(f"dashboard fixture_id=1539001 result_source mismatch: {row.get('result_source')}")
    calibration = row.get("post_match_calibration", {})
    if calibration.get("actual_score") != "2-0":
        fail("post_match_calibration.actual_score must be 2-0")
    if calibration.get("evaluation_method") != "rps_log_score":
        fail("post_match_calibration.evaluation_method must be rps_log_score")
    for key in ("actual_score_probability", "rps_1x2", "exact_score_log_loss", "deprecated_hit_type_warning"):
        if key not in calibration:
            fail(f"post_match_calibration missing {key}")
    if not isinstance(calibration.get("actual_score_probability"), (int, float)):
        fail("actual_score_probability must be numeric")
    if not isinstance(calibration.get("rps_1x2"), (int, float)):
        fail("rps_1x2 must be numeric")
    if not isinstance(calibration.get("exact_score_log_loss"), (int, float)):
        fail("exact_score_log_loss must be numeric")
    summary = row.get("score_matrix_summary", {})
    if summary.get("actual_score_probability") != calibration.get("actual_score_probability"):
        fail("score_matrix_summary actual_score_probability must mirror calibration")
    if row.get("score_distribution", {}).get("legacy_rule_weight") is not False:
        fail("score distribution must keep legacy_rule_weight=false")


def main() -> int:
    try:
        assert_results_file()
        assert_no_single_match_weight_logic()
        assert_dashboard_calibration()
        for path in (RESULTS, ALIASES, DASHBOARD, BUILD):
            assert_no_forbidden(path)
    except (CheckError, json.JSONDecodeError) as exc:
        print(f"W1 post-match result update check FAIL: {exc}", file=sys.stderr)
        return 1
    print("W1 post-match result update check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
