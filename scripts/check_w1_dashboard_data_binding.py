#!/usr/bin/env python3
"""Validate W1_DATA_BINDING_V1 dashboard data."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_JSON = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
BUILD_SCRIPT = ROOT / "scripts/build_w1_dashboard_data.py"

FORBIDDEN_TERMS = [
    "待 W1 参考信号",
    "当前页面只展示原站式交互结构",
    "Q" + "Q",
    "offi" + "cial",
    "pend" + "ing",
    "V" + "3",
    "V" + "4",
    "M" + "1",
    "bet",
    "stake",
    "profit",
    "guaranteed",
    "稳赚",
    "必胜",
]


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def assert_no_forbidden_text(text: str, label: str) -> None:
    for term in FORBIDDEN_TERMS:
        if term.isascii():
            if re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", text, re.I):
                fail(f"Forbidden term found in {label}: {term}")
        elif term in text:
            fail(f"Forbidden term found in {label}: {term}")


def main() -> int:
    try:
        if not DATA_JSON.is_file():
            fail("dashboard_data.json is missing")
        if not BUILD_SCRIPT.is_file():
            fail("build_w1_dashboard_data.py is missing")

        text = read(DATA_JSON)
        assert_no_forbidden_text(text, DATA_JSON.relative_to(ROOT).as_posix())
        data = json.loads(text)

        if data.get("schema_version") != "W1_VISUAL_DASHBOARD_DATA_BOUND_V1":
            fail("schema_version must be W1_VISUAL_DASHBOARD_DATA_BOUND_V1")
        if data.get("dashboard_binding", {}).get("version") != "W1_DATA_BINDING_V1":
            fail("dashboard_binding.version must be W1_DATA_BINDING_V1")

        records = data.get("match_records", [])
        if len(records) < 24:
            fail(f"Expected at least 24 match records, found {len(records)}")

        first = next((row for row in records if row.get("fixture_id") == "1489369"), None)
        if not first:
            fail("First match Mexico vs South Africa is missing")
        if first.get("match") != "墨西哥 vs 南非":
            fail("First match must be 墨西哥 vs 南非")
        if not first.get("boss_summary_cn"):
            fail("First match boss_summary_cn must not be empty")

        for key in ("status", "actual_score", "result_source"):
            if key not in first:
                fail(f"First match missing finished field: {key}")
        if first["status"] != "finished":
            fail("First match status must be finished via overlay when ledger has no result")
        if first["actual_score"] != {"home": 2, "away": 0}:
            fail("First match actual_score must be 2-0")
        if first["result_source"] != "manual_verified_overlay":
            fail("First match result_source must be manual_verified_overlay")

        required_fields = [
            "match",
            "fixture_id",
            "group",
            "kickoff",
            "status",
            "actual_score",
            "decision",
            "w1_state",
            "prediction_stage",
            "reference_direction",
            "reference_score",
            "risk_level_cn",
            "next_update_reason_cn",
            "is_final_decision",
            "play_guard_pass",
            "lineup_status",
            "referee_status",
            "odds_status",
            "odds_movement",
            "market_signal",
            "supporting_factors",
            "counter_factors",
            "risk_flags",
            "data_gaps",
            "current_action_cn",
            "boss_summary_cn",
            "next_refresh",
        ]
        for row in records:
            missing = [key for key in required_fields if key not in row]
            if missing:
                fail(f"{row.get('fixture_id')}: missing fields {missing}")
            if row["prediction_stage"] == "EARLY_REFERENCE":
                if row.get("ledger_required") is True:
                    fail(f"{row.get('fixture_id')}: EARLY_REFERENCE must not set ledger_required=true")
                if row.get("decision") == "W1_PLAY":
                    fail(f"{row.get('fixture_id')}: EARLY_REFERENCE must not produce W1_PLAY")
                if row.get("is_final_decision") is not False:
                    fail(f"{row.get('fixture_id')}: EARLY_REFERENCE must not be final")
            if row.get("decision") == "W1_PLAY" and row["prediction_stage"] not in ("FORMAL_DECISION", "FINAL_CHECK"):
                fail(f"{row.get('fixture_id')}: W1_PLAY only allowed in formal/final stages")
            if row.get("reference_score") and row.get("is_final_decision") is False:
                if "不是最终结论" not in row.get("non_final_disclaimer_cn", ""):
                    fail(f"{row.get('fixture_id')}: reference_score must carry non-final disclaimer")

        if data.get("status_cards", {}).get("play_guard_version") != "W1_PLAY_GUARD_V1":
            fail("PLAY_GUARD_V1 must remain in status_cards")
        if first.get("play_guard_version") != "W1_PLAY_GUARD_V1":
            fail("PLAY_GUARD_V1 must remain in first match record")
        if first.get("play_guard_pass") is not False:
            fail("First match must not bypass W1 play guard")
        if "赛前未放行" not in first.get("w1_state", ""):
            fail("First match must say W1 was not released pre-match")
        if first.get("hit_status_cn") != "比分命中":
            fail("First match hit_status_cn must be 比分命中")
        if "ledger" not in first.get("current_action_cn", ""):
            fail("First match current_action_cn must mention ledger review")

    except (CheckError, json.JSONDecodeError) as exc:
        print(f"W1 dashboard data binding check FAIL: {exc}", file=sys.stderr)
        return 1

    print("W1 dashboard data binding check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
