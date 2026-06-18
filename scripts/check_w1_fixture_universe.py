#!/usr/bin/env python3
"""Check W1 fixture universe spans configured World Cup group-stage rounds."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCOPE = ROOT / "config/w1_competition_scope.json"
BUILDER = ROOT / "scripts/build_w1_dashboard_data.py"
BUNDLE = ROOT / "scripts/w1_scout_bundle.py"
DASHBOARD_DATA = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
SCORE_ENGINE = ROOT / "scripts/w1_score_engine.py"


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def read_json(path: Path) -> dict:
    if not path.is_file():
        fail(f"missing file: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def check_scope() -> dict:
    scope = read_json(SCOPE)
    if scope.get("tournament") != "world_cup_2026":
        fail("scope tournament must be world_cup_2026")
    if scope.get("stage") != "group_stage":
        fail("scope stage must be group_stage")
    if scope.get("rounds") != [1, 2, 3]:
        fail(f"scope rounds must be [1,2,3]: {scope.get('rounds')}")
    expected = {
        "data/processed/match_cards/group_stage_round1",
        "data/processed/match_cards/group_stage_round2",
        "data/processed/match_cards/group_stage_round3",
    }
    if set(scope.get("card_dirs", [])) != expected:
        fail("scope card_dirs must include group stage rounds 1/2/3")
    if scope.get("results_overlay") != "data/results/world_cup_2026_results.json":
        fail("scope must use world_cup_2026_results.json overlay")
    if "data/results/round1_results.json" not in scope.get("legacy_results", []):
        fail("scope must retain round1_results.json as legacy compatibility")
    return scope


def check_builder_source() -> None:
    source = BUILDER.read_text(encoding="utf-8")
    forbidden = [
        'CARDS_DIR = ROOT / "data/processed/match_cards/group_stage_round1"',
        'RESULTS_JSON = ROOT / "data/results/round1_results.json"',
        'SNAPSHOT_DIR = ROOT / "data/snapshots/group_stage_round1"',
        "LEDGER_CANDIDATES = [",
    ]
    for token in forbidden:
        if token in source:
            fail(f"builder still has single-round hardcode: {token}")
    required = [
        "config/w1_competition_scope.json",
        "configured_card_dirs",
        "configured_result_paths",
        "configured_snapshot_dirs",
        "results_overlay",
    ]
    for token in required:
        if token not in source:
            fail(f"builder missing competition scope token: {token}")
    bundle = BUNDLE.read_text(encoding="utf-8")
    if re.search(r"^CARDS\s*=\s*ROOT\s*/\s*['\"]data/processed/match_cards/group_stage_round1['\"]", bundle, re.M):
        fail("w1_scout_bundle.py still reads only group_stage_round1")
    for token in ("config/w1_competition_scope.json", "card_dirs", "_card_dirs", "_card_paths"):
        if token not in bundle:
            fail(f"w1_scout_bundle.py missing competition scope token: {token}")


def check_cards_and_dashboard(scope: dict) -> None:
    total = 0
    for directory in scope.get("card_dirs", []):
        path = ROOT / directory
        if not path.is_dir():
            fail(f"missing card dir: {directory}")
        count = len(list(path.glob("*.json")))
        if count < 24:
            fail(f"{directory} has fewer than 24 cards: {count}")
        total += count
    data = read_json(DASHBOARD_DATA)
    records = data.get("match_records", [])
    if len(records) < total:
        fail(f"dashboard records fewer than configured cards: records={len(records)} cards={total}")
    rounds = {str(row.get("group") or "") for row in records}
    if "Group Stage - 2" not in rounds:
        fail("dashboard data missing Group Stage - 2 fixtures")
    if "Group Stage - 3" not in rounds:
        fail("dashboard data missing Group Stage - 3 fixtures")
    binding = data.get("dashboard_binding", {})
    if binding.get("competition_scope") != "config/w1_competition_scope.json":
        fail("dashboard binding missing competition scope")
    if binding.get("results_overlay") != "data/results/world_cup_2026_results.json":
        fail("dashboard binding missing world_cup_2026 results overlay")


def check_redlines() -> None:
    source = SCORE_ENGINE.read_text(encoding="utf-8")
    if not re.search(r"DEFAULT_RHO\s*=\s*-0\.057766\b", source):
        fail("DEFAULT_RHO changed")


def main() -> int:
    scope = check_scope()
    check_builder_source()
    check_cards_and_dashboard(scope)
    check_redlines()
    print("PASS check_w1_fixture_universe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
