#!/usr/bin/env python3
"""Validate W1_DATA_BINDING_V1 dashboard data."""

from __future__ import annotations

import json
import re
import sys
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_JSON = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
BUILD_SCRIPT = ROOT / "scripts/build_w1_dashboard_data.py"
QATAR_CARD = ROOT / "data/processed/match_cards/group_stage_round1/fixture_1489373_qatar_vs_switzerland.json"
ALLOWED_RESULT_SOURCES = {"post_match_auto_calibration_sample", "manual_verified_overlay", "api_football_fixture_result"}

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


def assert_lineup_effect_builder() -> None:
    source = read(BUILD_SCRIPT)
    for token in ("lineup_effect_for_card", "tactical_effect_for_card", "reference_should_recalculate", "key_absences", "rotation_flags", "lineup_summary_cn"):
        if token not in source:
            fail(f"build_w1_dashboard_data.py missing lineup_effect token: {token}")
    if not QATAR_CARD.is_file():
        fail("Qatar vs Switzerland card missing for lineup_effect validation")
    spec = importlib.util.spec_from_file_location("w1_dashboard_builder", BUILD_SCRIPT)
    if not spec or not spec.loader:
        fail("Unable to import dashboard builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    card = json.loads(read(QATAR_CARD))
    effect = module.lineup_effect_for_card(card)
    required = (
        "status",
        "formation_home",
        "formation_away",
        "formation_changed",
        "home_starter_confidence",
        "away_starter_confidence",
        "key_absences",
        "rotation_flags",
        "attacking_power_effect",
        "defensive_stability_effect",
        "midfield_control_effect",
        "pace_transition_effect",
        "set_piece_effect",
        "pressing_effect",
        "reference_should_recalculate",
        "lineup_summary_cn",
    )
    missing = [key for key in required if key not in effect]
    if missing:
        fail(f"lineup_effect missing keys: {missing}")
    if card.get("lineups", {}).get("confirmed_lineup_available"):
        if effect["status"] != "ready":
            fail("Qatar vs Switzerland lineup_effect.status must be ready after confirmed lineup")
        tactical = module.tactical_effect_for_card(card, effect)
        if tactical.get("status") != "ready":
            fail("Qatar vs Switzerland tactical_effect.status must be ready after confirmed lineup")
        tactical_text = " ".join(tactical.get("home_style_tags", []) + tactical.get("away_style_tags", []))
        for token in ("边路速度", "转换进攻", "前场冲击", "三中卫", "翼卫推进", "中路保护"):
            if token not in tactical_text:
                fail(f"Qatar vs Switzerland tactical_effect missing tag: {token}")
    else:
        if effect["status"] != "missing":
            fail("Qatar vs Switzerland lineup_effect.status must be missing before confirmed lineup")
        if effect["reference_should_recalculate"] is not False:
            fail("Missing lineup must not force reference recalculation")
        for key in (
            "attacking_power_effect",
            "defensive_stability_effect",
            "midfield_control_effect",
            "pace_transition_effect",
            "set_piece_effect",
            "pressing_effect",
        ):
            if effect.get(key) != "unknown":
                fail(f"Missing lineup must keep {key}=unknown")
        if "首发未确认" not in effect.get("lineup_summary_cn", ""):
            fail("Missing lineup summary must explain 首发未确认")


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
        assert_lineup_effect_builder()

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
        if first["result_source"] not in ALLOWED_RESULT_SOURCES:
            fail(f"First match result_source invalid: {first['result_source']}")

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
            "lineup_effect",
            "tactical_effect",
            "live_refresh",
            "score_distribution",
            "score_matrix_summary",
            "post_match_calibration",
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
            movement = row.get("odds_movement", {})
            if movement.get("schema_version") != "W1_ODDS_MOVEMENT_MONITOR_V1":
                fail(f"{row.get('fixture_id')}: odds_movement must use W1_ODDS_MOVEMENT_MONITOR_V1")
            for key in (
                "status",
                "status_reason_code",
                "liquidity",
                "snapshots",
                "cumulative_move",
                "recent_move",
                "coherence",
                "digestion",
                "play_guard_input",
                "display",
                "single_book_outliers",
                "disclaimer_cn",
            ):
                if key not in movement:
                    fail(f"{row.get('fixture_id')}: odds_movement missing {key}")
            cumulative = movement.get("cumulative_move", {})
            if "x2_tv_distance" not in cumulative or "mu_delta" not in cumulative:
                fail(f"{row.get('fixture_id')}: odds_movement must expose TV distance and mu drift")
            play_guard_input = movement.get("play_guard_input", {})
            if play_guard_input.get("recommended_gate") not in {"SKIP", "OBSERVE_ONLY", "ALLOW_FORMAL"}:
                fail(f"{row.get('fixture_id')}: odds_movement recommended_gate invalid")
            if movement.get("status") == "THIN_MARKET_SKIP" and play_guard_input.get("recommended_gate") != "SKIP":
                fail(f"{row.get('fixture_id')}: THIN_MARKET_SKIP must map to SKIP")
            if not movement.get("display", {}).get("normal_sentence_cn"):
                fail(f"{row.get('fixture_id')}: odds_movement normal display missing")
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
            lineup_effect = row.get("lineup_effect")
            if lineup_effect:
                for key in ("status", "key_absences", "rotation_flags", "reference_should_recalculate", "lineup_summary_cn"):
                    if key not in lineup_effect:
                        fail(f"{row.get('fixture_id')}: lineup_effect missing {key}")
            tactical_effect = row.get("tactical_effect")
            if tactical_effect:
                for key in ("status", "home_formation", "away_formation", "home_style_tags", "away_style_tags", "reference_should_recalculate", "tactical_summary_cn"):
                    if key not in tactical_effect:
                        fail(f"{row.get('fixture_id')}: tactical_effect missing {key}")
            live_refresh = row.get("live_refresh", {})
            if not live_refresh:
                fail(f"{row.get('fixture_id')}: live_refresh missing")
            modules = live_refresh.get("modules", {})
            for module_name in ("odds", "lineups", "referee", "weather", "injuries"):
                module = modules.get(module_name, {})
                if not module:
                    fail(f"{row.get('fixture_id')}: live_refresh.modules.{module_name} missing")
                for key in ("requested", "source", "status", "fetched_at", "message_cn"):
                    if key not in module:
                        fail(f"{row.get('fixture_id')}: live_refresh.modules.{module_name} missing {key}")
            score_distribution = row.get("score_distribution", {})
            if not score_distribution:
                fail(f"{row.get('fixture_id')}: score_distribution missing")
            score_matrix_summary = row.get("score_matrix_summary", {})
            if not score_matrix_summary:
                fail(f"{row.get('fixture_id')}: score_matrix_summary missing")
            for key in ("status", "main_score", "fallback_score", "score_pool", "game_open_trigger", "market_vs_score_risk", "score_summary_cn", "post_match_calibration"):
                if key not in score_distribution:
                    fail(f"{row.get('fixture_id')}: score_distribution missing {key}")
            if score_distribution.get("derived_from_score_matrix") is not True:
                fail(f"{row.get('fixture_id')}: score_distribution must be derived from score matrix")
            if score_distribution.get("legacy_rule_weight") is not False:
                fail(f"{row.get('fixture_id')}: legacy_rule_weight must be false")
            if score_distribution.get("status") == "skipped":
                if row.get("odds_status") != "WAIT":
                    fail(f"{row.get('fixture_id')}: skipped score_distribution is only allowed when odds_status=WAIT")
                if not score_distribution.get("skip_reason"):
                    fail(f"{row.get('fixture_id')}: skipped score_distribution must explain skip_reason")
                continue
            if len(score_distribution.get("score_pool", [])) < 6:
                fail(f"{row.get('fixture_id')}: score_distribution.score_pool must contain at least 6 paths")
            for item in score_distribution.get("score_pool", []):
                if not isinstance(item.get("weight"), (int, float)):
                    fail(f"{row.get('fixture_id')}: score_pool weight must be numeric probability")
            pool_text = " ".join(item.get("path", "") for item in score_distribution.get("score_pool", []))
            if "防线崩盘" not in pool_text:
                fail(f"{row.get('fixture_id')}: score pool must include 防线崩盘")
            market_summary = score_distribution.get("market_vs_score_risk", {}).get("summary_cn", "")
            for token in ("深让不等于大胜", "平手盘也可能打开", "大小球不直接决定比分"):
                if token not in market_summary:
                    fail(f"{row.get('fixture_id')}: market_vs_score_risk.summary_cn missing {token}")

        qatar = next((row for row in records if row.get("fixture_id") == "1489373"), None)
        if not qatar:
            fail("fixture_id=1489373 Qatar vs Switzerland is missing")
        if qatar.get("status") != "finished" or qatar.get("actual_score") != {"home": 1, "away": 1}:
            fail("fixture_id=1489373 must be finished with actual_score 1-1")
        if qatar.get("result_source") not in ALLOWED_RESULT_SOURCES:
            fail(f"fixture_id=1489373 result_source invalid: {qatar.get('result_source')}")
        qatar_cal = qatar.get("post_match_calibration", {})
        if qatar_cal.get("actual_score") != "1-1":
            fail("fixture_id=1489373 post_match_calibration.actual_score must be 1-1")
        if qatar_cal.get("evaluation_method") != "rps_log_score":
            fail("fixture_id=1489373 evaluation_method must be rps_log_score")
        for key in ("actual_score_probability", "rps_1x2", "exact_score_log_loss", "deprecated_hit_type_warning"):
            if key not in qatar_cal:
                fail(f"fixture_id=1489373 calibration missing {key}")
        if "深让不等于大胜" not in qatar_cal.get("lesson_cn", ""):
            fail("fixture_id=1489373 calibration must include 深让不等于大胜")
        usa = next((row for row in records if row.get("fixture_id") == "1489370"), None)
        if not usa:
            fail("fixture_id=1489370 USA vs Paraguay is missing")
        if usa.get("status") != "finished" or usa.get("actual_score") != {"home": 4, "away": 1}:
            fail("fixture_id=1489370 must be finished with actual_score 4-1")
        if usa.get("result_source") not in ALLOWED_RESULT_SOURCES:
            fail(f"fixture_id=1489370 result_source invalid: {usa.get('result_source')}")
        usa_cal = usa.get("post_match_calibration", {})
        if usa_cal.get("actual_score") != "4-1":
            fail("fixture_id=1489370 post_match_calibration.actual_score must be 4-1")
        if usa_cal.get("evaluation_method") != "rps_log_score":
            fail("fixture_id=1489370 evaluation_method must be rps_log_score")
        for key in ("actual_score_probability", "rps_1x2", "exact_score_log_loss", "deprecated_hit_type_warning"):
            if key not in usa_cal:
                fail(f"fixture_id=1489370 calibration missing {key}")
        if "平手盘也可能打开" not in usa_cal.get("lesson_cn", ""):
            fail("fixture_id=1489370 calibration must include 平手盘也可能打开")
        qatar_lineups = qatar.get("live_refresh", {}).get("modules", {}).get("lineups", {})
        for key in ("source", "status", "fetched_at", "message_cn"):
            if key not in qatar_lineups:
                fail(f"fixture_id=1489373 live_refresh.modules.lineups missing {key}")
        if qatar_lineups.get("source") == "live_api" and qatar_lineups.get("status") == "success" and "实时 API 成功" not in qatar_lineups.get("message_cn", ""):
            fail("fixture_id=1489373 live_api success must be explicit")
        if qatar_lineups.get("source") in {"verified_fallback", "cache"} and "实时 API 成功" in qatar_lineups.get("message_cn", ""):
            fail("fixture_id=1489373 fallback/cache must not be described as live API success")
        qatar_quality = qatar.get("data_quality", {})
        if qatar_quality.get("overall") != "partial":
            fail("fixture_id=1489373 data_quality.overall must be partial")
        if qatar_quality.get("odds", {}).get("bookmakers_count") != 13:
            fail("fixture_id=1489373 odds bookmakers_count must be 13")
        if not all(qatar_quality.get("odds", {}).get(key) is True for key in ("has_1x2", "has_ah", "has_ou")):
            fail("fixture_id=1489373 odds must have 1X2/AH/OU")
        if qatar.get("lineup_status") != "CONFIRMED" and "lineups.confirmed_lineup" not in qatar_quality.get("play_guard", {}).get("fail_rules", []):
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
        if qatar.get("lineup_status") == "CONFIRMED":
            expected = {
                "confirmed_lineup_available": True,
                "home_formation": "4-3-3",
                "away_formation": "3-4-2-1",
                "home_starting_count": 11,
                "away_starting_count": 11,
            }
            for key, value in expected.items():
                if qatar.get(key) != value:
                    fail(f"fixture_id=1489373 {key} mismatch: {qatar.get(key)}")
            if int(qatar.get("home_bench_count") or 0) < 1 or int(qatar.get("away_bench_count") or 0) < 1:
                fail("fixture_id=1489373 bench counts must be present when lineups are confirmed")
            if qatar.get("lineup_effect", {}).get("status") != "ready":
                fail("fixture_id=1489373 lineup_effect.status must be ready when lineups are confirmed")
            tactical = qatar.get("tactical_effect", {})
            if tactical.get("status") != "ready":
                fail("fixture_id=1489373 tactical_effect.status must be ready when lineups are confirmed")
            tactical_text = " ".join(tactical.get("home_style_tags", []) + tactical.get("away_style_tags", []))
            for token in ("边路速度", "转换进攻", "前场冲击", "三中卫", "翼卫推进", "中路保护"):
                if token not in tactical_text:
                    fail(f"fixture_id=1489373 tactical_effect missing tag: {token}")

        if data.get("status_cards", {}).get("play_guard_version") != "W1_PLAY_GUARD_V1":
            fail("PLAY_GUARD_V1 must remain in status_cards")
        if first.get("play_guard_version") != "W1_PLAY_GUARD_V1":
            fail("PLAY_GUARD_V1 must remain in first match record")
        if first.get("play_guard_pass") is not False:
            fail("First match must not bypass W1 play guard")
        if "赛前未放行" not in first.get("w1_state", ""):
            fail("First match must say W1 was not released pre-match")
        if first.get("post_match_calibration", {}).get("evaluation_method") != "rps_log_score":
            fail("First match must expose rps_log_score calibration")
        if "ledger" not in first.get("current_action_cn", ""):
            fail("First match current_action_cn must mention ledger review")

    except (CheckError, json.JSONDecodeError) as exc:
        print(f"W1 dashboard data binding check FAIL: {exc}", file=sys.stderr)
        return 1

    print("W1 dashboard data binding check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
