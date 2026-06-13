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
            "data_quality",
            "environment_context",
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
            quality = row.get("data_quality", {})
            if not quality:
                fail(f"{row.get('fixture_id')}: data_quality missing")
            for key in ("overall", "reason_cn", "odds", "lineup", "referee", "injuries", "local_context", "play_guard"):
                if key not in quality:
                    fail(f"{row.get('fixture_id')}: data_quality missing {key}")
            if "fail_rules" not in quality.get("play_guard", {}):
                fail(f"{row.get('fixture_id')}: data_quality.play_guard.fail_rules missing")
            env = row.get("environment_context", {})
            if not env:
                fail(f"{row.get('fixture_id')}: environment_context missing")
            for key in (
                "venue_name",
                "city",
                "country",
                "kickoff_local_time",
                "weather_status",
                "temperature_c",
                "humidity_pct",
                "wind_speed_kmh",
                "precipitation_mm",
                "altitude_m",
                "roof_status",
                "environment_risk_level",
                "environment_risk_flags",
                "environment_summary_cn",
            ):
                if key not in env:
                    fail(f"{row.get('fixture_id')}: environment_context missing {key}")
            if not env.get("venue_name") or not env.get("city") or not env.get("country"):
                fail(f"{row.get('fixture_id')}: environment_context venue/city/country must not be empty")
            if env.get("weather_status") == "missing" and env.get("environment_summary_cn") != "天气数据暂缺":
                fail(f"{row.get('fixture_id')}: missing weather must say 天气数据暂缺")

        qatar = next((row for row in records if row.get("fixture_id") == "1489373"), None)
        if not qatar:
            fail("fixture_id=1489373 Qatar vs Switzerland is missing")
        qatar_quality = qatar.get("data_quality", {})
        if qatar_quality.get("overall") != "partial":
            fail("fixture_id=1489373 data_quality.overall must be partial")
        if qatar_quality.get("odds", {}).get("bookmakers_count") != 13:
            fail("fixture_id=1489373 odds bookmakers_count must be 13")
        if not all(qatar_quality.get("odds", {}).get(key) is True for key in ("has_1x2", "has_ah", "has_ou")):
            fail("fixture_id=1489373 odds must have 1X2/AH/OU")
        if "lineups.confirmed_lineup" not in qatar_quality.get("play_guard", {}).get("fail_rules", []):
            fail("fixture_id=1489373 play_guard fail_rules must include lineups.confirmed_lineup")
        qatar_env = qatar.get("environment_context", {})
        if qatar_env.get("venue_name") != "Levi's Stadium":
            fail("fixture_id=1489373 venue_name must be Levi's Stadium")
        if qatar_env.get("city") != "San Francisco Bay Area":
            fail("fixture_id=1489373 city must be San Francisco Bay Area")
        if qatar_env.get("weather_status") not in {"ready", "missing"}:
            fail("fixture_id=1489373 weather_status must be ready or missing")
        if qatar_env.get("weather_status") == "ready":
            for key in ("temperature_c", "humidity_pct", "wind_speed_kmh"):
                if qatar_env.get(key) is None:
                    fail(f"fixture_id=1489373 ready weather missing {key}")
        if qatar_env.get("weather_status") == "missing" and qatar_env.get("environment_summary_cn") != "天气数据暂缺":
            fail("fixture_id=1489373 environment_summary_cn must be 天气数据暂缺 when weather is missing")

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
