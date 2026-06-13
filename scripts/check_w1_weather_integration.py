#!/usr/bin/env python3
"""Validate W1_WEATHER_INTEGRATION_V1."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENUES = ROOT / "data/static/world_cup_2026_venues.json"
WEATHER_CLIENT = ROOT / "scripts/w1_weather_client.py"
SERVER = ROOT / "scripts/w1_local_predict_server.py"
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
DATA_JSON = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
PROGRESS = ROOT / "state/w1_predict_progress.json"

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
CREDENTIAL_WORDS = ["API " + "key", "api " + "key", "to" + "ken", "se" + "cret"]


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(read(path))


def assert_no_forbidden(text: str, label: str, *, frontend: bool = False) -> None:
    for term in FORBIDDEN:
        if term.isascii():
            if re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", text, re.I):
                fail(f"Forbidden term found in {label}: {term}")
        elif term in text:
            fail(f"Forbidden term found in {label}: {term}")
    if frontend:
        for term in CREDENTIAL_WORDS:
            if re.search(re.escape(term), text, re.I):
                fail(f"Credential wording found in frontend: {term}")


def assert_venues() -> None:
    data = load_json(VENUES)
    venues = data.get("venues", [])
    if len(venues) < 16:
        fail(f"Expected at least 16 venues, found {len(venues)}")
    names = {row.get("venue_name") for row in venues}
    if "Levi's Stadium" not in names:
        fail("Levi's Stadium missing from venue mapping")
    for row in venues:
        for key in ("venue_name", "city", "country", "lat", "lon", "altitude_m", "roof_status", "timezone"):
            if key not in row:
                fail(f"venue missing {key}: {row.get('venue_name')}")
        if row["roof_status"] not in {"open", "closed", "unknown"}:
            fail(f"invalid roof_status: {row['venue_name']}")


def assert_weather_client() -> None:
    if not WEATHER_CLIENT.is_file():
        fail("w1_weather_client.py missing")
    text = read(WEATHER_CLIENT)
    for token in ("Open-Meteo", "api.open-meteo.com", "weather_status", "temperature_c", "humidity_pct", "wind_speed_kmh"):
        if token not in text:
            fail(f"weather client missing token: {token}")


def assert_server_progress() -> None:
    text = read(SERVER)
    for token in ("查询比赛环境/天气", "total_steps", "w1_weather_client.py", "w1_weather_cache.json"):
        if token not in text:
            fail(f"server missing weather progress token: {token}")
    if PROGRESS.is_file():
        data = load_json(PROGRESS)
        if data.get("total_steps") is not None and data.get("total_steps") != 9:
            fail("runtime progress total_steps must be 9")
        labels = [step.get("label") for step in data.get("steps", [])]
        if labels and "查询比赛环境/天气" not in labels:
            fail("runtime progress must include 查询比赛环境/天气")


def assert_dashboard_data() -> None:
    data = load_json(DATA_JSON)
    records = data.get("match_records", [])
    if len(records) < 24:
        fail(f"Expected at least 24 records, found {len(records)}")
    for row in records:
        env = row.get("environment_context")
        if not env:
            fail(f"{row.get('fixture_id')}: environment_context missing")
        for key in ("venue_name", "weather_status", "temperature_c", "humidity_pct", "wind_speed_kmh", "altitude_m", "roof_status"):
            if key not in env:
                fail(f"{row.get('fixture_id')}: environment_context missing {key}")
    qatar = next((row for row in records if row.get("fixture_id") == "1489373"), None)
    if not qatar:
        fail("fixture_id=1489373 missing")
    env = qatar["environment_context"]
    if env.get("venue_name") != "Levi's Stadium":
        fail("fixture_id=1489373 venue mismatch")
    if env.get("altitude_m") != 2:
        fail("fixture_id=1489373 altitude_m must be 2")
    if env.get("roof_status") != "open":
        fail("fixture_id=1489373 roof_status must be open")
    if env.get("temperature_c") is None:
        if env.get("weather_status") != "missing" or not env.get("weather_reason_cn"):
            fail("fixture_id=1489373 missing temperature requires weather_status=missing with reason")
    else:
        if env.get("temperature_c") != 21.4:
            fail("fixture_id=1489373 temperature_c must match verified Open-Meteo sample")
        if env.get("humidity_pct") != 64:
            fail("fixture_id=1489373 humidity_pct must match verified Open-Meteo sample")
        if env.get("wind_speed_kmh") is None:
            fail("fixture_id=1489373 wind_speed_kmh must be present when weather is ready")


def assert_html() -> None:
    text = read(HTML)
    assert_no_forbidden(text, HTML.relative_to(ROOT).as_posix(), frontend=True)
    for token in ("比赛环境", "温度", "湿度", "风速", "海拔", "查询比赛环境/天气", "降雨概率/降雨量"):
        if token not in text:
            fail(f"HTML missing token: {token}")


def main() -> int:
    try:
        for path in (VENUES, WEATHER_CLIENT, SERVER, HTML, DATA_JSON):
            if not path.is_file():
                fail(f"missing file: {path.relative_to(ROOT)}")
        assert_no_forbidden(read(DATA_JSON), DATA_JSON.relative_to(ROOT).as_posix())
        assert_venues()
        assert_weather_client()
        assert_server_progress()
        assert_dashboard_data()
        assert_html()
    except (CheckError, json.JSONDecodeError) as exc:
        print(f"W1 weather integration check FAIL: {exc}", file=sys.stderr)
        return 1
    print("W1 weather integration check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
