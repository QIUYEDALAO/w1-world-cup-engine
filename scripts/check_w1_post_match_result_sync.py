#!/usr/bin/env python3
"""Check W1 post-match API result sync wiring."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "scripts/w1_local_predict_server.py"
DASHBOARD_DATA = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
RESULTS_JSON = ROOT / "data/results/round1_results.json"
GERMANY_CARD = ROOT / "data/processed/match_cards/group_stage_round1/fixture_1489374_germany_vs_cura-ao.json"
SCORE_ENGINE = ROOT / "scripts/w1_score_engine.py"
ODDS_THRESHOLDS = ROOT / "config/w1_odds_movement_thresholds.json"


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def read_json(path: Path) -> dict:
    if not path.is_file():
        fail(f"missing file: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def assert_score_record(row: dict, source_name: str) -> None:
    score = row.get("actual_score")
    if not isinstance(score, dict):
        fail(f"{source_name} actual_score is not an object")
    if score.get("home") != 7 or score.get("away") != 1:
        fail(f"{source_name} Germany vs Curacao score is not 7-1: {score}")
    if row.get("result_source") != "api_football_fixture_result":
        fail(f"{source_name} result_source is not api_football_fixture_result")


def check_server_wiring() -> None:
    source = SERVER.read_text(encoding="utf-8")
    required = [
        "api_football_get_fixture_by_id",
        "/fixtures?id={fixture_id}",
        "FINISHED_STATUS_SHORT",
        "is_finished_fixture_status",
        "parse_finished_score",
        "skipped_not_finished",
        "refresh_result_sync_module",
        '"result_sync"',
    ]
    for needle in required:
        if needle not in source:
            fail(f"server missing result sync wiring: {needle}")
    if "fixtures?id=66457070" in source or 'if fixture_id == "66457070"' in source:
        fail("server contains Germany local alias hardcode for API result sync")
    result_fn = source[source.find("def api_fixture_id_candidates_for_result") : source.find("def write_result_to_card")]
    if result_fn.find('match.get("fixture_id")') > result_fn.find('match.get("api_fixture_id")'):
        fail("result sync must prefer match fixture_id before api_fixture_id/request alias")


def check_dashboard_data() -> None:
    data = read_json(DASHBOARD_DATA)
    rows = data.get("match_records") or []
    germany = next((row for row in rows if str(row.get("fixture_id")) == "1489374"), None)
    if not germany:
        fail("dashboard_data missing fixture_id=1489374")
    if germany.get("status") != "finished":
        fail(f"dashboard_data Germany status is not finished: {germany.get('status')}")
    assert_score_record(germany, "dashboard_data")
    if germany.get("actual_score_display_cn") != "德国 7-1 库拉索":
        fail(f"dashboard_data display is wrong: {germany.get('actual_score_display_cn')}")


def check_card_and_results() -> None:
    card = read_json(GERMANY_CARD)
    if card.get("status") != "finished":
        fail(f"Germany card status is not finished: {card.get('status')}")
    assert_score_record(card, "Germany card")
    if not card.get("result_synced_at_utc"):
        fail("Germany card missing result_synced_at_utc")

    results = read_json(RESULTS_JSON).get("results", {})
    row = results.get("1489374")
    if not row:
        fail("results overlay missing 1489374")
    assert_score_record(row, "results overlay")
    aliases = [str(value) for value in row.get("alias_fixture_ids", [])]
    if "66457070" not in aliases:
        fail("results overlay missing alias 66457070 for Germany vs Curacao")


def check_guards_unchanged() -> None:
    score_source = SCORE_ENGINE.read_text(encoding="utf-8")
    if not re.search(r"DEFAULT_RHO\s*=\s*-0\.057766\b", score_source):
        fail("DEFAULT_RHO changed from -0.057766")
    thresholds = read_json(ODDS_THRESHOLDS)
    if thresholds.get("calibrated") != "none" or thresholds.get("tier") != "C":
        fail("odds movement thresholds changed from default Tier C / calibrated none")


def main() -> int:
    check_server_wiring()
    check_dashboard_data()
    check_card_and_results()
    check_guards_unchanged()
    print("PASS check_w1_post_match_result_sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
