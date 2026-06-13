#!/usr/bin/env python3
"""Fetch match-hour weather from Open-Meteo for W1.

No API key is required. Runtime failures are converted to a structured
weather_status=missing payload so the dashboard can keep the previous view.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"


def parse_utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)


def missing_payload(reason: str) -> dict[str, Any]:
    return {
        "weather_status": "missing",
        "weather_code": None,
        "temperature_c": None,
        "humidity_pct": None,
        "wind_speed_kmh": None,
        "precipitation_mm": None,
        "precipitation_probability_pct": None,
        "weather_snapshot_time": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "weather_reason_cn": reason,
    }


def nearest_hour_index(times: list[str], kickoff: datetime) -> int | None:
    if not times:
        return None
    best_index = None
    best_delta = None
    for index, raw in enumerate(times):
        try:
            candidate = parse_utc(raw if raw.endswith("Z") else f"{raw}+00:00")
        except ValueError:
            continue
        delta = abs((candidate - kickoff).total_seconds())
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_index = index
    return best_index


def choose_endpoint(kickoff: datetime) -> str:
    now = datetime.now(timezone.utc)
    return OPEN_METEO_ARCHIVE if kickoff.date() < now.date() else OPEN_METEO_FORECAST


def fetch_weather(lat: float, lon: float, kickoff_utc: str, timeout: int = 12) -> dict[str, Any]:
    kickoff = parse_utc(kickoff_utc)
    date = kickoff.date().isoformat()
    endpoint = choose_endpoint(kickoff)
    hourly = [
        "temperature_2m",
        "relative_humidity_2m",
        "precipitation",
        "weather_code",
        "wind_speed_10m",
    ]
    if endpoint == OPEN_METEO_FORECAST:
        hourly.append("precipitation_probability")
    params = {
        "latitude": f"{lat:.5f}",
        "longitude": f"{lon:.5f}",
        "hourly": ",".join(hourly),
        "start_date": date,
        "end_date": date,
        "timezone": "UTC",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }
    url = endpoint + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - callers need structured missing payload
        return missing_payload(f"天气查询失败：{exc}")

    hourly_data = payload.get("hourly", {})
    times = hourly_data.get("time", [])
    index = nearest_hour_index(times, kickoff)
    if index is None:
        return missing_payload("天气小时数据暂缺")

    def item(name: str) -> Any:
        values = hourly_data.get(name) or []
        return values[index] if index < len(values) else None

    return {
        "weather_status": "ready",
        "weather_code": item("weather_code"),
        "temperature_c": item("temperature_2m"),
        "humidity_pct": item("relative_humidity_2m"),
        "wind_speed_kmh": item("wind_speed_10m"),
        "precipitation_mm": item("precipitation"),
        "precipitation_probability_pct": item("precipitation_probability"),
        "weather_snapshot_time": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "weather_source": "Open-Meteo",
        "weather_hour_utc": times[index],
        "weather_reason_cn": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Open-Meteo match weather for W1.")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--kickoff-utc", required=True)
    args = parser.parse_args()
    result = fetch_weather(args.lat, args.lon, args.kickoff_utc)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
