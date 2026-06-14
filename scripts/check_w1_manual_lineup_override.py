#!/usr/bin/env python3
"""Validate W1 manual lineup override hotfix."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib import error, request


ROOT = Path(__file__).resolve().parents[1]
OVERRIDES = [
    ROOT / "data/manual_lineups/1539001.json",
    ROOT / "data/manual_lineups/66456942.json",
]
ALIASES = ROOT / "data/fixture_aliases.json"
SERVER = ROOT / "scripts/w1_local_predict_server.py"
BUILD = ROOT / "scripts/build_w1_dashboard_data.py"
DASHBOARD = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
TEST_PORT = "8877"
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"
FORBIDDEN = ["建议下注", "推荐投注", "稳赚", "必胜", "保证命中", "bet", "stake", "profit", "guaranteed"]


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_no_forbidden(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for term in FORBIDDEN:
        pattern = rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])" if term.isascii() else re.escape(term)
        if re.search(pattern, text, re.I):
            fail(f"{path.relative_to(ROOT)} contains forbidden term: {term}")


def assert_override_file() -> None:
    expected_by_file = {
        "1539001.json": "1539001",
        "66456942.json": "66456942",
    }
    for path in OVERRIDES:
        if not path.is_file():
            fail(f"manual lineup override file missing: {path.relative_to(ROOT)}")
        data = read_json(path)
        expected = {
            "fixture_id": expected_by_file[path.name],
            "source": "Sky Sports",
            "source_type": "manual_verified",
            "status": "confirmed",
            "home_team": "Australia",
            "away_team": "Turkey",
            "home_formation": "3-4-2-1",
            "away_formation": "4-2-3-1",
        }
        for key, value in expected.items():
            if data.get(key) != value:
                fail(f"{path.name} override {key} mismatch: {data.get(key)}")
        if len(data.get("home_starting_xi", [])) != 11 or len(data.get("away_starting_xi", [])) != 11:
            fail(f"{path.name} override must contain 11 starters per side")
        notes = " ".join(data.get("notes_cn", []))
        for token in ("Sky Sports", "Kenan Yildiz", "Mathew Ryan", "BC Place"):
            if token not in notes:
                fail(f"{path.name} override notes missing {token}")


def assert_aliases() -> None:
    if not ALIASES.is_file():
        fail("data/fixture_aliases.json missing")
    aliases = read_json(ALIASES)
    if aliases.get("1539001") != "66456942" or aliases.get("66456942") != "1539001":
        fail("fixture aliases must map 1539001 <-> 66456942")


def assert_code_paths() -> None:
    server = SERVER.read_text(encoding="utf-8")
    for token in (
        "MANUAL_LINEUPS_DIR",
        "manual_lineup_payload",
        "manual_lineup_payload_for_match",
        "card_path_for_manual_lineup",
        "fixture_id_candidates",
        "FIXTURE_ALIASES",
        'source="manual_verified"',
        "Sky Sports",
    ):
        if token not in server:
            fail(f"server missing manual override token: {token}")
    build = BUILD.read_text(encoding="utf-8")
    for token in (
        "MANUAL_LINEUPS_DIR",
        "manual_lineup_for_card",
        "apply_manual_lineup_override",
        "fixture_id_candidates",
        "FIXTURE_ALIASES",
        "lineup_source_name",
        "manual_lineup_fixture_id",
    ):
        if token not in build:
            fail(f"build script missing manual override token: {token}")


def assert_dashboard_data() -> None:
    result = subprocess.run([sys.executable, str(BUILD)], cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        fail(f"build_w1_dashboard_data.py failed: {result.stderr or result.stdout}")
    data = read_json(DASHBOARD)
    row = next((item for item in data.get("match_records", []) if item.get("match_en") in {"Australia vs Türkiye", "Australia vs Turkey"}), None)
    if not row:
        fail("Australia vs Turkey match record missing")
    if row.get("confirmed_lineup_available") is not True:
        fail("Australia vs Turkey confirmed_lineup_available must be true")
    expected = {
        "home_formation": "3-4-2-1",
        "away_formation": "4-2-3-1",
        "home_starting_count": 11,
        "away_starting_count": 11,
    }
    for key, value in expected.items():
        if row.get(key) != value:
            fail(f"Australia vs Turkey {key} mismatch: {row.get(key)}")
    lineups = row.get("lineups", {})
    if lineups.get("source") != "manual_verified" or lineups.get("source_name") != "Sky Sports":
        fail("Australia vs Turkey lineups source must be manual_verified / Sky Sports")
    if row.get("data_quality", {}).get("lineup", {}).get("status") != "ready":
        fail("Australia vs Turkey data_quality.lineup.status must be ready")
    if row.get("lineup_effect", {}).get("status") != "ready":
        fail("Australia vs Turkey lineup_effect.status must be ready")
    tactical = row.get("tactical_effect", {})
    if tactical.get("status") != "ready":
        fail("Australia vs Turkey tactical_effect.status must be ready")
    tactical_text = " ".join(tactical.get("home_style_tags", []) + tactical.get("away_style_tags", []))
    for token in ("三中卫", "翼卫推进", "中路保护", "中路组织", "攻守平衡", "控球推进"):
        if token not in tactical_text:
            fail(f"Australia vs Turkey tactical tags missing {token}")
    html = HTML.read_text(encoding="utf-8")
    for token in ("manual_verified", "Sky Sports", "3-4-2-1", "4-2-3-1"):
        if token not in html:
            fail(f"dashboard HTML missing {token}")


def http_json(path: str, payload: dict | None = None) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method="POST" if payload is not None else "GET")
    opener = request.build_opener(request.ProxyHandler({}))
    with opener.open(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def server_available() -> bool:
    try:
        return bool(http_json("/health").get("ok"))
    except (OSError, error.URLError, json.JSONDecodeError):
        return False


def assert_predict_1539001_done() -> None:
    proc = None
    if not server_available():
        env = dict(**__import__("os").environ)
        env["W1_DASHBOARD_PORT"] = TEST_PORT
        proc = subprocess.Popen(
            [sys.executable, str(SERVER)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        for _ in range(20):
            if server_available():
                break
            time.sleep(0.25)
    try:
        if not server_available():
            fail("local predict server is not available for /predict smoke")
        started = http_json("/predict", {"fixture_id": "1539001"})
        if not started.get("ok"):
            fail(f"/predict fixture_id=1539001 failed to start: {started}")
        progress = {}
        for _ in range(30):
            time.sleep(0.5)
            progress = http_json("/progress")
            if progress.get("status") in {"done", "failed", "error"}:
                break
        if progress.get("status") != "done":
            fail(f"/predict fixture_id=1539001 did not finish done: {progress.get('status')} {progress.get('message_cn')}")
        if progress.get("total_steps") != 10:
            fail("/progress total_steps must be 10")
        if any(step.get("state") != "done" for step in progress.get("steps", [])):
            fail("/progress steps 1-10 must all be done")
        current = progress.get("current_match", {})
        if str(current.get("fixture_id")) != "1539001":
            fail(f"current_fixture_id must be 1539001, got {current.get('fixture_id')}")
        data = read_json(DASHBOARD)
        row = next((item for item in data.get("match_records", []) if item.get("fixture_id") == "1539001"), None)
        if not row:
            fail("dashboard_data missing fixture_id=1539001 after /predict")
        lineups = row.get("lineups", {})
        if lineups.get("source") != "manual_verified":
            fail("dashboard lineups.source must remain manual_verified after /predict")
        if row.get("confirmed_lineup_available") is not True:
            fail("dashboard confirmed_lineup_available must be true after /predict")
        live_lineups = row.get("live_refresh", {}).get("modules", {}).get("lineups", {})
        if live_lineups.get("source") != "manual_verified" or live_lineups.get("status") != "success":
            fail(f"live_refresh lineups must be manual_verified success, got {live_lineups}")
        if "数据暂缺，保留上一版" in progress.get("message_cn", ""):
            fail("progress must not finish with stale data message")
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def main() -> int:
    try:
        assert_override_file()
        assert_aliases()
        assert_code_paths()
        assert_dashboard_data()
        assert_predict_1539001_done()
        for path in (*OVERRIDES, ALIASES, SERVER, BUILD, DASHBOARD, HTML):
            assert_no_forbidden(path)
    except (CheckError, json.JSONDecodeError) as exc:
        print(f"W1 manual lineup override check FAIL: {exc}", file=sys.stderr)
        return 1
    print("W1 manual lineup override check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
