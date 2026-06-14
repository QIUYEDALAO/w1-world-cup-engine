#!/usr/bin/env python3
"""Validate real OU rho calibration artifacts and active provenance consistency."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data/historical/rho_calibration_real.csv"
REPORT = ROOT / "reports/W1_RHO_REAL_OU_CALIBRATION_REPORT.md"
FIGURE = ROOT / "reports/W1_RHO_REAL_OU_CALIBRATION_RELIABILITY.png"
JSON_REPORT = ROOT / "reports/w1_rho_real_ou_calibration.json"
CANDIDATE = ROOT / "reports/w1_rho_provenance_candidate.json"
SCORE_ENGINE = ROOT / "scripts/w1_score_engine.py"
BUILD_DASHBOARD = ROOT / "scripts/build_w1_dashboard_data.py"
PLAY_GUARD = ROOT / "config/w1_decision_policy.json"
PROVENANCE = ROOT / "config/w1_rho_provenance.json"
REQUIRED_COLUMNS = [
    "match_date",
    "home_team",
    "away_team",
    "closing_home_odds",
    "closing_draw_odds",
    "closing_away_odds",
    "closing_ou_main_line",
    "closing_over_odds",
    "closing_under_odds",
    "home_goals",
    "away_goals",
]


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_csv() -> int:
    if not CSV_PATH.is_file():
        fail("rho_calibration_real.csv missing")
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        missing = [col for col in REQUIRED_COLUMNS if col not in header]
        if missing:
            fail(f"rho_calibration_real.csv missing required columns: {missing}")
        rows = list(reader)
    if len(rows) < 500:
        fail(f"rho_calibration_real.csv sample too small: {len(rows)}")
    for idx, row in enumerate(rows, start=2):
        if row.get("competition", "").upper() == "SYNTH":
            fail(f"row {idx}: competition must not be SYNTH")
        if str(row.get("closing_ou_main_line", "")).strip() != "2.5":
            fail(f"row {idx}: closing_ou_main_line must be 2.5")
        for col in REQUIRED_COLUMNS:
            if str(row.get(col, "")).strip() == "":
                fail(f"row {idx}: missing required value {col}")
    return len(rows)


def assert_reports(sample_count: int) -> tuple[dict, dict]:
    for path in (REPORT, FIGURE, JSON_REPORT, CANDIDATE):
        if not path.is_file():
            fail(f"missing artifact: {path.relative_to(ROOT)}")
    report_text = REPORT.read_text(encoding="utf-8")
    if "PRODUCTION_READY" not in report_text:
        fail("report must contain PRODUCTION_READY")
    data = read_json(JSON_REPORT)
    if data.get("valid_sample") != sample_count:
        fail("json valid_sample must match CSV row count")
    if data.get("mode") != "ou":
        fail("json mode must be ou")
    if data.get("production_ready") is not True:
        fail("json production_ready must be true before DEFAULT_RHO can be updated")
    if data.get("default_rho_updated") is not False:
        fail("json report should remain an immutable calibration report, not an active update marker")
    candidate = read_json(CANDIDATE)
    if candidate.get("source_report") != "reports/W1_RHO_REAL_OU_CALIBRATION_REPORT.md":
        fail("candidate source_report mismatch")
    if candidate.get("valid_sample") != sample_count:
        fail("candidate valid_sample mismatch")
    if candidate.get("calibrated") is not False:
        fail("candidate must not be active calibrated provenance")
    return data, candidate


def assert_production_consistent(report_data: dict, candidate: dict) -> None:
    text = SCORE_ENGINE.read_text(encoding="utf-8")
    expected_rho = float(report_data.get("rho_hat"))
    if f"DEFAULT_RHO = {expected_rho}" not in text:
        fail(f"DEFAULT_RHO must equal calibrated rho_hat {expected_rho}")
    provenance = read_json(PROVENANCE)
    if provenance.get("calibrated") is not True:
        fail("config/w1_rho_provenance.json must be calibrated=true after approved update")
    if abs(float(provenance.get("default_rho")) - expected_rho) > 1e-9:
        fail("provenance default_rho must match rho_hat")
    if provenance.get("input_synthetic") is not False:
        fail("provenance input_synthetic must be false")
    if provenance.get("valid_sample") != report_data.get("valid_sample"):
        fail("provenance valid_sample must match report")
    if provenance.get("mode") != "ou":
        fail("provenance mode must be ou")
    if provenance.get("source_report") != candidate.get("source_report"):
        fail("provenance source_report must match candidate")
    if provenance.get("source_json") != candidate.get("source_json"):
        fail("provenance source_json must match candidate")
    if provenance.get("source_candidate") != "reports/w1_rho_provenance_candidate.json":
        fail("provenance source_candidate mismatch")
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--",
            str(BUILD_DASHBOARD.relative_to(ROOT)),
            str(PLAY_GUARD.relative_to(ROOT)),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        fail(f"git diff failed: {result.stderr or result.stdout}")
    changed = [line for line in result.stdout.splitlines() if line.strip()]
    if changed:
        fail(f"protected score matrix / PLAY_GUARD files changed: {changed}")


def main() -> int:
    try:
        sample_count = assert_csv()
        report_data, candidate = assert_reports(sample_count)
        assert_production_consistent(report_data, candidate)
    except (CheckError, json.JSONDecodeError) as exc:
        print(f"W1 real OU rho calibration check FAIL: {exc}", file=sys.stderr)
        return 1
    print("W1 real OU rho calibration check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
