#!/usr/bin/env python3
"""Validate W1 score matrix integration in the production dashboard chain."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DASHBOARD_JSON = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
BUILD_SCRIPT = SCRIPTS / "build_w1_dashboard_data.py"
CARDS_DIR = ROOT / "data/processed/match_cards/group_stage_round1"
FORBIDDEN = ["建议下注", "推荐投注", "稳赚", "必胜", "保证命中", "bet", "stake", "profit", "guaranteed"]


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def in01(value: object) -> bool:
    return isinstance(value, (int, float)) and 0 <= float(value) <= 1


def assert_no_forbidden(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for term in FORBIDDEN:
        if re.search(re.escape(term), text, re.I):
            fail(f"{path.relative_to(ROOT)} contains forbidden term: {term}")


def assert_build_script_clean() -> None:
    text = BUILD_SCRIPT.read_text(encoding="utf-8")
    bad_patterns = [
        r"fid\s*==",
        r"fixture_id\s*==",
        r"==\s*['\"]1489",
        r"def\s+line_value\s*\(",
        r"def\s+ou_value\s*\(",
        r"score_distribution_for_record",
        r"Over \(\[0-9\.\]\+\)",
    ]
    for pattern in bad_patterns:
        if re.search(pattern, text):
            fail(f"build_w1_dashboard_data.py still contains legacy score branch: {pattern}")
    if "w1_score_engine" not in text or "build_score_distribution" not in text:
        fail("build_w1_dashboard_data.py must call w1_score_engine.build_score_distribution")


def assert_batch_tool_runs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.md"
        out = Path(tmp) / "matrix.json"
        cmd = [
            sys.executable,
            str(SCRIPTS / "w1_score_matrix_batch.py"),
            "--cards-dir",
            str(CARDS_DIR),
            "--old-dashboard-data",
            str(DASHBOARD_JSON),
            "--report",
            str(report),
            "--json-out",
            str(out),
        ]
        result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            fail(f"w1_score_matrix_batch.py smoke failed: {result.stderr or result.stdout}")
        if not report.is_file() or not out.is_file():
            fail("w1_score_matrix_batch.py did not create report/json outputs")


def assert_dashboard_data() -> None:
    data = json.loads(DASHBOARD_JSON.read_text(encoding="utf-8"))
    records = data.get("match_records", [])
    if len(records) < 24:
        fail("dashboard_data.json must contain at least 24 match_records")
    ready_seen = False
    for row in records:
        fid = row.get("fixture_id")
        summary = row.get("score_matrix_summary")
        dist = row.get("score_distribution")
        if not summary:
            fail(f"{fid}: score_matrix_summary missing")
        if not dist:
            fail(f"{fid}: score_distribution missing")
        if dist.get("derived_from_score_matrix") is not True:
            fail(f"{fid}: score_distribution.derived_from_score_matrix must be true")
        if dist.get("legacy_rule_weight") is not False:
            fail(f"{fid}: score_distribution.legacy_rule_weight must be false")
        if dist.get("status") == "ready":
            ready_seen = True
            if summary.get("status") != "ready":
                fail(f"{fid}: score_matrix_summary.status must be ready")
            for key in ("home_win_prob", "draw_prob", "away_win_prob", "open_game_mass", "collapse_mass"):
                if not in01(summary.get(key)):
                    fail(f"{fid}: score_matrix_summary.{key} must be probability")
            hda = [summary.get("home_win_prob"), summary.get("draw_prob"), summary.get("away_win_prob")]
            if abs(sum(float(x) for x in hda) - 1.0) > 0.05:
                fail(f"{fid}: 1X2 matrix probabilities should be close to 1")
            top_scores = summary.get("top_scores") or []
            if not top_scores:
                fail(f"{fid}: score_matrix_summary.top_scores must not be empty")
            for item in top_scores:
                if not in01(item.get("probability")):
                    fail(f"{fid}: top_scores probability out of range")
            for item in dist.get("score_pool", []):
                if not in01(item.get("weight")) or not in01(item.get("probability")):
                    fail(f"{fid}: score_pool weight/probability must be numeric probability")
            trigger_note = " ".join(
                str(dist.get("game_open_trigger", {}).get(key, ""))
                for key in ("note_cn", "collapse_note_cn")
            )
            if "比分矩阵区域概率" not in trigger_note or "矩阵尾部质量" not in trigger_note:
                fail(f"{fid}: open/collapse notes must point to matrix mass")
        calibration = row.get("post_match_calibration", {})
        if calibration.get("actual_score"):
            if calibration.get("evaluation_method") != "rps_log_score":
                fail(f"{fid}: post_match_calibration.evaluation_method must be rps_log_score")
            for key in ("actual_score_probability", "rps_1x2", "exact_score_log_loss"):
                if key not in calibration:
                    fail(f"{fid}: post_match_calibration missing {key}")
            if "deprecated_hit_type_warning" not in calibration:
                fail(f"{fid}: post_match_calibration missing deprecated_hit_type_warning")
    if not ready_seen:
        fail("No ready score matrix records found")


def main() -> int:
    try:
        sys.path.insert(0, str(SCRIPTS))
        import w1_score_engine  # noqa: F401

        assert_build_script_clean()
        assert_batch_tool_runs()
        assert_dashboard_data()
        for path in (BUILD_SCRIPT, SCRIPTS / "w1_score_engine.py", SCRIPTS / "w1_score_matrix_batch.py", DASHBOARD_JSON):
            assert_no_forbidden(path)
    except (CheckError, Exception) as exc:  # noqa: BLE001
        print(f"W1 score matrix integration check FAIL: {exc}", file=sys.stderr)
        return 1
    print("W1 score matrix integration check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
