#!/usr/bin/env python3
"""Validate W1 click-to-predict local server and dashboard wiring."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib import request
from urllib.error import URLError


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "scripts/w1_local_predict_server.py"
RUNNER = ROOT / "scripts/run_w1_dashboard.sh"
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
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
FORBIDDEN_CREDENTIAL_WORDS = [
    "API " + "key",
    "api " + "key",
    "to" + "ken",
    "se" + "cret",
]


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def assert_no_forbidden(path: Path) -> None:
    text = read(path)
    for term in FORBIDDEN:
        if term.isascii():
            if re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", text, re.I):
                fail(f"Forbidden term found in {path.relative_to(ROOT)}: {term}")
        elif term in text:
            fail(f"Forbidden term found in {path.relative_to(ROOT)}: {term}")
    if path == HTML:
        for term in FORBIDDEN_CREDENTIAL_WORDS:
            if re.search(re.escape(term), text, re.I):
                fail(f"Credential wording must not appear in dashboard: {term}")


def assert_server() -> None:
    if not SERVER.is_file():
        fail("server file is missing")
    text = read(SERVER)
    for token in ("127.0.0.1", "GET", "POST", "/health", "/predict", "/progress", "/dashboard-data"):
        if token not in text:
            fail(f"server missing token: {token}")
    if "state/w1_predict_progress.json" not in text:
        fail("server must write runtime progress file")
    if "reports/dashboard/assets/w1_dashboard_data.json" not in text:
        fail("server must update dashboard data")
    for token in (
        "resolve_predict_match",
        "find_match_by_fixture_id",
        "find_match_by_name",
        "未找到对应比赛 fixture_id",
        "payload.get(\"fixture_id\")",
        "current_match",
        "fetch_live_lineups_from_api",
        "fixtures/lineups",
        "write_lineups_to_card",
        "refresh_lineups",
        "live_refresh",
        "verified_fallback",
        "实时 API 未配置",
    ):
        if token not in text:
            fail(f"server missing fixture_id priority token: {token}")
    fallback_idx = text.find("verified_lineup_payload(fixture_id)")
    fallback_block = text[fallback_idx:fallback_idx + 700] if fallback_idx >= 0 else ""
    if "source=\"live_api\"" in fallback_block or "source='live_api'" in fallback_block:
        fail("verified fallback must not be marked as live_api success")
    fixture_branch = re.search(
        r"if fixture_id:.*?find_match_by_fixture_id\(fixture_id\).*?return progress_match",
        text,
        re.S,
    )
    if not fixture_branch:
        fail("server must exact-match by fixture_id before any name fallback")
    start = text.find("if fixture_id:")
    end = text.find("home =", start)
    fixture_only_block = text[start:end]
    if "find_match_by_name" in fixture_only_block:
        fail("fixture_id branch must not call name fallback")


def assert_runner() -> None:
    if not RUNNER.is_file():
        fail("runner file is missing")
    text = read(RUNNER)
    if "w1_local_predict_server.py" not in text:
        fail("runner must start local server")
    if "http://127.0.0.1:8765/reports/dashboard/W1_VISUAL_DASHBOARD.html" not in text:
        fail("runner must show dashboard URL")


def assert_dashboard() -> None:
    text = read(HTML)
    for token in (
        "POST /predict",
        "fetch('/predict'",
        "fetch('/progress'",
        "fetch('/dashboard-data'",
        "查询进度",
        "初始化比赛",
        "实时请求赔率 API",
        "实时请求首发 API",
        "实时请求裁判/fixture detail API",
        "实时请求伤停/停赛 API",
        "实时请求天气 API/Open-Meteo",
        "查询比赛环境/天气",
        "写入 match card runtime",
        "重算首发/战术/风控",
        "重建 dashboard 数据",
        "返回 progress",
        "本次实时刷新",
        "实时 API 成功",
        "使用缓存",
        "使用兜底数据",
        "数据暂缺，保留上一版",
        "fixture_id:fixtureId",
        "const selectedMatch=selectedRecord",
    ):
        if token not in text:
            fail(f"dashboard missing token: {token}")


def assert_progress_schema() -> None:
    if not PROGRESS.is_file():
        fail("progress file is missing")
    data = json.loads(read(PROGRESS))
    if data.get("schema_version") != "w1_predict_progress.v1":
        fail("progress schema mismatch")
    for key in ("status", "total_steps", "step_index", "step_label", "message_cn", "steps", "updated_at"):
        if key not in data:
            fail(f"progress missing key: {key}")
    steps = data.get("steps", [])
    if data.get("total_steps") != 10 or len(steps) != 10:
        fail("progress must contain 10 steps")
    if "查询比赛环境/天气" not in [step.get("label") for step in steps]:
        fail("progress must include weather/environment step")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(url: str, payload: dict[str, str] | None = None) -> dict[str, object]:
    if payload is None:
        with request.urlopen(url, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def assert_fixture_id_smoke() -> None:
    port = free_port()
    env = os.environ.copy()
    env["W1_DASHBOARD_PORT"] = str(port)
    env.pop("APIFOOTBALL_KEY", None)
    env.pop("W1_LOCAL_REAL_REFRESH", None)
    proc = subprocess.Popen(
        ["python3", str(SERVER)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(30):
            try:
                if http_json(f"{base}/health").get("ok"):
                    break
            except (URLError, TimeoutError, ConnectionError):
                time.sleep(0.1)
        else:
            fail("smoke server did not start")

        started = http_json(f"{base}/predict", {"fixture_id": "1489373"})
        if not started.get("ok"):
            fail("fixture_id smoke predict did not start")
        saw_qatar = False
        last_progress = {}
        for _ in range(300):
            progress = http_json(f"{base}/progress")
            last_progress = progress
            current = progress.get("current_match") or progress.get("match") or {}
            if current.get("fixture_id") == "1489373":
                saw_qatar = True
                match = current.get("match") or ""
                home_en = current.get("home_team") or ""
                away_en = current.get("away_team") or ""
                home = current.get("home_team_cn") or ""
                away = current.get("away_team_cn") or ""
                text = f"{match} {home_en} {away_en} {home} {away}"
                if "Qatar" not in text or "Switzerland" not in text:
                    fail("fixture_id=1489373 smoke resolved to wrong match")
                if "Brazil" in text or "Morocco" in text:
                    fail("fixture_id=1489373 smoke must not resolve to Brazil vs Morocco")
                if progress.get("status") == "done":
                    data = http_json(f"{base}/dashboard-data")
                    qatar = next(
                        (row for row in data.get("match_records", []) if str(row.get("fixture_id")) == "1489373"),
                        None,
                    )
                    if not qatar:
                        fail("fixture_id=1489373 missing from dashboard data after smoke")
                    expected = {
                        "lineup_status": "CONFIRMED",
                        "confirmed_lineup_available": True,
                        "home_formation": "4-3-3",
                        "away_formation": "3-4-2-1",
                        "home_starting_count": 11,
                        "away_starting_count": 11,
                    }
                    for key, value in expected.items():
                        if qatar.get(key) != value:
                            fail(f"fixture_id=1489373 {key} mismatch after smoke: {qatar.get(key)}")
                    if int(qatar.get("home_bench_count") or 0) < 1 or int(qatar.get("away_bench_count") or 0) < 1:
                        fail("fixture_id=1489373 bench counts must be present after smoke")
                    if qatar.get("lineup_effect", {}).get("status") != "ready":
                        fail("fixture_id=1489373 lineup_effect.status must be ready after smoke")
                    if qatar.get("tactical_effect", {}).get("status") != "ready":
                        fail("fixture_id=1489373 tactical_effect.status must be ready after smoke")
                    live_refresh = qatar.get("live_refresh", {})
                    lineups = live_refresh.get("modules", {}).get("lineups", {})
                    for key in ("source", "status", "fetched_at", "message_cn"):
                        if key not in lineups:
                            fail(f"fixture_id=1489373 live_refresh.modules.lineups missing {key}")
                    if lineups.get("source") == "live_api" and lineups.get("status") == "success":
                        fail("fixture_id=1489373 no-key smoke must not masquerade fallback as live_api success")
                    if lineups.get("source") != "verified_fallback":
                        fail(f"fixture_id=1489373 no-key smoke must use verified_fallback, got {lineups.get('source')}")
                    if "使用兜底数据" not in str(lineups.get("message_cn")):
                        fail("fixture_id=1489373 fallback module must explain 使用兜底数据")
                    return
            time.sleep(0.1)
        if saw_qatar:
            fail(f"fixture_id=1489373 smoke did not finish: {last_progress.get('step_label')} {last_progress.get('message_cn')}")
        fail("fixture_id=1489373 smoke did not reach progress/current_match")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)


def main() -> int:
    try:
        for path in (SERVER, RUNNER, HTML):
            if not path.is_file():
                fail(f"missing file: {path.relative_to(ROOT)}")
            assert_no_forbidden(path)
        assert_server()
        assert_runner()
        assert_dashboard()
        assert_fixture_id_smoke()
        assert_progress_schema()
    except (CheckError, json.JSONDecodeError) as exc:
        print(f"W1 click-to-predict check FAIL: {exc}", file=sys.stderr)
        return 1

    print("W1 click-to-predict check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
