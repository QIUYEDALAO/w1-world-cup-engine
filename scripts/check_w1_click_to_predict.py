#!/usr/bin/env python3
"""Validate W1 click-to-predict local server and dashboard wiring."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


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
        "读取本地 match card",
        "查询赔率",
        "查询阵容/首发",
        "查询裁判",
        "计算参考倾向",
        "检查 W1 风控",
        "更新 dashboard",
        "数据暂缺，保留上一版",
    ):
        if token not in text:
            fail(f"dashboard missing token: {token}")


def assert_progress_schema() -> None:
    if not PROGRESS.is_file():
        fail("progress file is missing")
    data = json.loads(read(PROGRESS))
    if data.get("schema_version") != "w1_predict_progress.v1":
        fail("progress schema mismatch")
    for key in ("status", "step_index", "step_label", "message_cn", "steps", "updated_at"):
        if key not in data:
            fail(f"progress missing key: {key}")
    steps = data.get("steps", [])
    if len(steps) != 8:
        fail("progress must contain 8 steps")


def main() -> int:
    try:
        for path in (SERVER, RUNNER, HTML):
            if not path.is_file():
                fail(f"missing file: {path.relative_to(ROOT)}")
            assert_no_forbidden(path)
        assert_server()
        assert_runner()
        assert_dashboard()
        assert_progress_schema()
    except (CheckError, json.JSONDecodeError) as exc:
        print(f"W1 click-to-predict check FAIL: {exc}", file=sys.stderr)
        return 1

    print("W1 click-to-predict check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
