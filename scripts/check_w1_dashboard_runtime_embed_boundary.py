#!/usr/bin/env python3
"""Validate W1_DASHBOARD_RUNTIME_EMBED_BOUNDARY_FIX_V1.

The tracked HTML keeps a file-open embedded baseline. It must not absorb local
runtime state from state/ overlays, weather cache, or live_refresh. Runtime data
may still appear in the gitignored external JSON and server path.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
EXTERNAL_JSON = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
BUILD = ROOT / "scripts/build_w1_dashboard_data.py"
WEATHER_CACHE = ROOT / "state/w1_weather_cache.json"
LIVE_REFRESH_STATE = ROOT / "state/w1_live_refresh_state.json"
LINEUP_OVERLAY = ROOT / "state/w1_lineup_runtime_overlay.json"


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def run(cmd: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=True, check=False)


def git_status_html() -> str:
    result = run(["git", "status", "--short", "--", str(HTML.relative_to(ROOT))])
    if result.returncode != 0:
        fail(result.stderr or result.stdout or "git status failed")
    return result.stdout.strip()


def load_embedded() -> dict[str, Any]:
    text = HTML.read_text(encoding="utf-8")
    match = re.search(r'<script id="w1-data" type="application/json">(.*?)</script>', text, re.S)
    if not match:
        fail("tracked HTML must retain embedded JSON for file-open use")
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        fail(f"embedded JSON is not parseable: {exc}")


def any_runtime_weather_in_external() -> bool:
    if not WEATHER_CACHE.is_file() or not EXTERNAL_JSON.is_file():
        return False
    data = json.loads(EXTERNAL_JSON.read_text(encoding="utf-8"))
    for row in data.get("match_records", []):
        env = row.get("environment_context", {})
        if env.get("weather_snapshot_time") or env.get("temperature_c") is not None:
            return True
    return False


def assert_embedded_boundary(data: dict[str, Any]) -> None:
    records = data.get("match_records", [])
    if len(records) < 24:
        fail(f"embedded JSON must retain file-open records >=24, got {len(records)}")

    for row in records:
        fid = row.get("fixture_id")
        env = row.get("environment_context", {})
        if env.get("weather_snapshot_time") is not None:
            fail(f"{fid}: embedded environment_context.weather_snapshot_time must be null")
        if env.get("weather_reason_cn") not in (None, "", "天气数据暂缺"):
            fail(f"{fid}: embedded environment_context.weather_reason_cn carries runtime text")
        for key in ("weather_code", "temperature_c", "humidity_pct", "wind_speed_kmh", "precipitation_mm", "precipitation_probability_pct"):
            if env.get(key) is not None:
                fail(f"{fid}: embedded environment_context.{key} must be null")

        lineups = row.get("lineups", {})
        source = row.get("lineup_source") or lineups.get("source")
        if source != "manual_verified":
            if row.get("lineup_confirmed_utc") is not None:
                fail(f"{fid}: embedded non-manual lineup_confirmed_utc must be null")
            if lineups.get("confirmed_utc") is not None:
                fail(f"{fid}: embedded non-manual lineups.confirmed_utc must be null")
            if source in {"live_api", "verified_fallback", "cache"}:
                fail(f"{fid}: embedded lineup source carries runtime overlay/source state: {source}")

        refresh = row.get("live_refresh", {})
        modules = refresh.get("modules", {})
        if refresh.get("requested_at") is not None:
            fail(f"{fid}: embedded live_refresh.requested_at must be null")
        for name, module in modules.items():
            if module.get("fetched_at") is not None or module.get("updated_at") is not None:
                fail(f"{fid}: embedded live_refresh.modules.{name} timestamp must be null")
            message = str(module.get("message_cn") or "")
            if any(token in message for token in ("实时 API 成功", "赔率返回", "records=", "天气已接入", "查询失败", "使用缓存/兜底数据")):
                fail(f"{fid}: embedded live_refresh.modules.{name}.message_cn carries runtime message: {message}")
            source = str(module.get("source") or "")
            if source == "实时 API 成功":
                fail(f"{fid}: embedded live_refresh.modules.{name}.source carries runtime source: {source}")
            status = str(module.get("status") or "")
            if status in {"成功", "失败", "暂无"}:
                fail(f"{fid}: embedded live_refresh.modules.{name}.status carries runtime status: {status}")


def main() -> int:
    try:
        if git_status_html():
            fail("HTML must be clean before boundary check; restore tracked HTML first")

        env = os.environ.copy()
        env["W1_DISABLE_API_ENV_BRIDGE"] = "1"
        result = run(["python3", str(BUILD)], env=env)
        if result.returncode != 0:
            fail(f"build_w1_dashboard_data.py failed: {result.stderr or result.stdout}")

        dirty = git_status_html()
        if dirty:
            fail(f"tracked HTML became dirty after build: {dirty}")

        embedded = load_embedded()
        assert_embedded_boundary(embedded)

        external = json.loads(EXTERNAL_JSON.read_text(encoding="utf-8"))
        if len(external.get("match_records", [])) < 24:
            fail("external runtime JSON must retain records >=24")
        if WEATHER_CACHE.is_file() and not any_runtime_weather_in_external():
            fail("external runtime JSON should retain weather runtime state when local weather cache exists")
        if LIVE_REFRESH_STATE.is_file() and not any(
            row.get("live_refresh", {}).get("modules") for row in external.get("match_records", [])
        ):
            fail("external runtime JSON should retain live_refresh module structure")
        if LINEUP_OVERLAY.is_file() and not isinstance(external.get("match_records", []), list):
            fail("external runtime JSON malformed while lineup runtime overlay exists")
    except CheckError as exc:
        print(f"W1 dashboard runtime embed boundary check FAIL: {exc}", file=sys.stderr)
        return 1

    print("W1 dashboard runtime embed boundary check PASS (tracked HTML stable; runtime state stays external/state/server)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
