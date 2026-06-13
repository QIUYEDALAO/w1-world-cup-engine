#!/usr/bin/env python3
"""Validate W1_ENV_CONTEXT_V1 dashboard and schema wiring."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "config/w1_match_card_schema.json"
DATA_JSON = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
BUILD_SCRIPT = ROOT / "scripts/build_w1_dashboard_data.py"

REQUIRED_ENV_FIELDS = [
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
]
RISK_FLAGS = {
    "HIGH_TEMP",
    "HIGH_HUMIDITY",
    "HIGH_ALTITUDE",
    "HIGH_WIND",
    "RAIN_RISK",
    "WEATHER_IMPACT_REDUCED",
    "WEATHER_MISSING",
}
FORBIDDEN = [
    "bet",
    "stake",
    "profit",
    "guaranteed",
    "稳赚",
    "必胜",
    "Q" + "Q",
    "offi" + "cial",
    "pend" + "ing",
    "V" + "3",
    "V" + "4",
    "M" + "1",
]


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(read(path))


def assert_no_forbidden(text: str, label: str) -> None:
    for term in FORBIDDEN:
        if term.isascii():
            if re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", text, re.I):
                fail(f"Forbidden term found in {label}: {term}")
        elif term in text:
            fail(f"Forbidden term found in {label}: {term}")


def assert_schema() -> None:
    schema = load_json(SCHEMA)
    if "environment_context" not in schema.get("required", []):
        fail("schema required must include environment_context")
    env = schema.get("properties", {}).get("environment_context", {})
    if not env:
        fail("schema properties.environment_context missing")
    for field in REQUIRED_ENV_FIELDS:
        if field not in env.get("required", []):
            fail(f"schema environment_context required missing {field}")
        if field not in env.get("properties", {}):
            fail(f"schema environment_context properties missing {field}")
    enum_flags = set(env["properties"]["environment_risk_flags"]["items"].get("enum", []))
    if not RISK_FLAGS.issubset(enum_flags):
        fail("schema environment risk flags incomplete")


def assert_environment_rules(env: dict, fixture_id: str) -> None:
    flags = set(env.get("environment_risk_flags", []))
    temp = env.get("temperature_c")
    humidity = env.get("humidity_pct")
    wind = env.get("wind_speed_kmh")
    rain = env.get("precipitation_mm")
    altitude = env.get("altitude_m")
    roof = env.get("roof_status")
    if temp is not None and temp >= 30 and "HIGH_TEMP" not in flags:
        fail(f"{fixture_id}: HIGH_TEMP flag missing")
    if humidity is not None and humidity >= 70 and "HIGH_HUMIDITY" not in flags:
        fail(f"{fixture_id}: HIGH_HUMIDITY flag missing")
    if altitude is not None and altitude >= 1200 and "HIGH_ALTITUDE" not in flags:
        fail(f"{fixture_id}: HIGH_ALTITUDE flag missing")
    if wind is not None and wind >= 25 and "HIGH_WIND" not in flags:
        fail(f"{fixture_id}: HIGH_WIND flag missing")
    if rain is not None and rain > 0 and "RAIN_RISK" not in flags:
        fail(f"{fixture_id}: RAIN_RISK flag missing")
    if roof == "closed" and "WEATHER_IMPACT_REDUCED" not in flags:
        fail(f"{fixture_id}: WEATHER_IMPACT_REDUCED flag missing")
    if env.get("weather_status") == "missing":
        if env.get("environment_summary_cn") != "天气数据暂缺":
            fail(f"{fixture_id}: missing weather summary must be 天气数据暂缺")
        if "WEATHER_MISSING" not in flags:
            fail(f"{fixture_id}: WEATHER_MISSING flag missing")


def assert_dashboard_data() -> None:
    data = load_json(DATA_JSON)
    records = data.get("match_records", [])
    if len(records) < 24:
        fail(f"Expected at least 24 records, found {len(records)}")
    for row in records:
        env = row.get("environment_context")
        if not env:
            fail(f"{row.get('fixture_id')}: environment_context missing")
        for field in REQUIRED_ENV_FIELDS:
            if field not in env:
                fail(f"{row.get('fixture_id')}: environment_context missing {field}")
        if not env.get("venue_name") or not env.get("city") or not env.get("country"):
            fail(f"{row.get('fixture_id')}: venue/city/country must not be blank")
        if env.get("weather_status") not in {"ready", "missing", "partial", "error"}:
            fail(f"{row.get('fixture_id')}: invalid weather_status")
        if env.get("roof_status") not in {"open", "closed", "unknown"}:
            fail(f"{row.get('fixture_id')}: invalid roof_status")
        if env.get("environment_risk_level") not in {"LOW", "MEDIUM", "HIGH"}:
            fail(f"{row.get('fixture_id')}: invalid environment_risk_level")
        assert_environment_rules(env, str(row.get("fixture_id")))

    qatar = next((row for row in records if row.get("fixture_id") == "1489373"), None)
    if not qatar:
        fail("fixture_id=1489373 missing")
    env = qatar["environment_context"]
    if env.get("venue_name") != "Levi's Stadium":
        fail("fixture_id=1489373 venue_name mismatch")
    if env.get("city") != "San Francisco Bay Area":
        fail("fixture_id=1489373 city mismatch")
    if env.get("weather_status") not in {"ready", "missing"}:
        fail("fixture_id=1489373 weather_status must be ready or missing")
    if env.get("weather_status") == "ready" and env.get("temperature_c") is None:
        fail("fixture_id=1489373 ready weather must include temperature_c")
    if env.get("altitude_m") != 2:
        fail("fixture_id=1489373 altitude_m must come from static venue context")


def assert_html() -> None:
    text = read(HTML)
    assert_no_forbidden(text, HTML.relative_to(ROOT).as_posix())
    for token in (
        "比赛环境",
        "球场：",
        "城市：",
        "天气：",
        "温度：",
        "湿度：",
        "风速：",
        "海拔：",
        "环境风险：",
        "解读：",
        "天气数据暂缺",
        "environment_context",
    ):
        if token not in text:
            fail(f"HTML missing environment token: {token}")


def assert_build_script() -> None:
    text = read(BUILD_SCRIPT)
    for token in ("environment_context_for_card", "VENUE_ENV_STATIC", "HIGH_TEMP", "HIGH_ALTITUDE", "WEATHER_IMPACT_REDUCED"):
        if token not in text:
            fail(f"build script missing environment token: {token}")
    if "W1_PLAY_GUARD" in text and "environment_context_for_card" not in text:
        fail("environment context must not change play guard logic")


def main() -> int:
    try:
        for path in (SCHEMA, DATA_JSON, HTML, BUILD_SCRIPT):
            if not path.is_file():
                fail(f"missing file: {path.relative_to(ROOT)}")
        assert_no_forbidden(read(DATA_JSON), DATA_JSON.relative_to(ROOT).as_posix())
        assert_schema()
        assert_dashboard_data()
        assert_html()
        assert_build_script()
    except (CheckError, json.JSONDecodeError) as exc:
        print(f"W1 environment context check FAIL: {exc}", file=sys.stderr)
        return 1

    print("W1 environment context check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
