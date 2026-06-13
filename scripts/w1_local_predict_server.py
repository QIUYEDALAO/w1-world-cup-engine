#!/usr/bin/env python3
"""Local W1 click-to-predict server.

The server binds only to 127.0.0.1 and serves the static dashboard plus a small
JSON API. It keeps credential material on the server side and writes progress to
state/w1_predict_progress.json.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
PORT = int(os.environ.get("W1_DASHBOARD_PORT", "8765"))
PROGRESS = ROOT / "state/w1_predict_progress.json"
WEATHER_CACHE = ROOT / "state/w1_weather_cache.json"
DASHBOARD_DATA = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
BUILD_SCRIPT = ROOT / "scripts/build_w1_dashboard_data.py"
WEATHER_CLIENT = ROOT / "scripts/w1_weather_client.py"
VENUES_JSON = ROOT / "data/static/world_cup_2026_venues.json"
WATCHER = ROOT / "scripts/w1_watcher.sh"
ENV_KEY_NAME = "APIFOOTBALL_" + "KEY"

STEPS = [
    "初始化比赛",
    "读取本地 match card",
    "查询赔率",
    "查询阵容/首发",
    "查询裁判",
    "查询比赛环境/天气",
    "计算参考倾向",
    "检查 W1 风控",
    "更新 dashboard",
]

_job_lock = threading.Lock()
_active_job: str | None = None


def now_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S CST", time.localtime())


def write_progress(payload: dict[str, Any]) -> None:
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    payload.setdefault("schema_version", "w1_predict_progress.v1")
    payload.setdefault("updated_at", now_ts())
    tmp = PROGRESS.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(PROGRESS)


def progress_payload(
    *,
    job_id: str,
    status: str,
    step_index: int,
    message: str,
    match: dict[str, Any],
    error: str | None = None,
) -> dict[str, Any]:
    steps = []
    for index, label in enumerate(STEPS, start=1):
        if index < step_index:
            state = "done"
        elif index == step_index and status == "running":
            state = "running"
        elif status == "done":
            state = "done"
        elif status in {"failed", "error"} and index == step_index:
            state = "failed"
        else:
            state = "waiting"
        steps.append({"index": index, "label": label, "state": state})

    return {
        "schema_version": "w1_predict_progress.v1",
        "job_id": job_id,
        "status": status,
        "total_steps": len(STEPS),
        "step_index": step_index,
        "step_label": STEPS[max(0, min(step_index - 1, len(STEPS) - 1))],
        "message_cn": message,
        "match": match,
        "current_match": match,
        "steps": steps,
        "error_cn": error,
        "dashboard_data_path": str(DASHBOARD_DATA.relative_to(ROOT)),
        "updated_at": now_ts(),
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def match_records() -> list[dict[str, Any]]:
    if not DASHBOARD_DATA.is_file():
        return []
    data = load_json(DASHBOARD_DATA)
    return data.get("match_records", [])


def find_match_by_fixture_id(fixture_id: Any) -> dict[str, Any] | None:
    if fixture_id in (None, ""):
        return None
    wanted = str(fixture_id)
    for row in match_records():
        if str(row.get("fixture_id")) == wanted:
            return row
    return None


def find_match_by_name(home: str, away: str) -> dict[str, Any] | None:
    for row in match_records():
        if row.get("home_team_cn") == home and row.get("away_team_cn") == away:
            return row
        if row.get("home_team_cn") == away and row.get("away_team_cn") == home:
            return row
    return None


def progress_match(row: dict[str, Any], stage_cn: str = "") -> dict[str, Any]:
    return {
        "fixture_id": str(row.get("fixture_id") or ""),
        "match": row.get("match") or f"{row.get('home_team_cn', '')} vs {row.get('away_team_cn', '')}",
        "home_team": row.get("home_team") or "",
        "away_team": row.get("away_team") or "",
        "home_team_cn": row.get("home_team_cn") or "",
        "away_team_cn": row.get("away_team_cn") or "",
        "stage_cn": stage_cn or row.get("prediction_stage_cn") or "",
    }


def resolve_predict_match(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    fixture_id = str(payload.get("fixture_id") or "").strip()
    if fixture_id:
        row = find_match_by_fixture_id(fixture_id)
        if not row:
            return None, f"未找到对应比赛 fixture_id: {fixture_id}"
        return progress_match(row, str(payload.get("stage_cn") or "")), None

    home = str(payload.get("home_team_cn") or payload.get("home") or "")
    away = str(payload.get("away_team_cn") or payload.get("away") or "")
    if not home or not away:
        return None, "请选择主队和客队。"
    row = find_match_by_name(home, away)
    if row:
        return progress_match(row, str(payload.get("stage_cn") or "")), None
    return {"home_team_cn": home, "away_team_cn": away, "stage_cn": str(payload.get("stage_cn") or "")}, None


def venue_mapping() -> dict[str, dict[str, Any]]:
    if not VENUES_JSON.is_file():
        return {}
    data = load_json(VENUES_JSON)
    return {row["venue_name"]: row for row in data.get("venues", [])}


def update_weather_cache(match: dict[str, Any], env: dict[str, str]) -> dict[str, Any] | None:
    selected = find_match_by_fixture_id(match.get("fixture_id"))
    if not selected:
        selected = find_match_by_name(match.get("home_team_cn", ""), match.get("away_team_cn", ""))
    if not selected:
        return None
    venue_name = selected.get("environment_context", {}).get("venue_name")
    venue = venue_mapping().get(venue_name or "")
    kickoff_utc = selected.get("kickoff_utc")
    if not venue or not kickoff_utc:
        return None
    result = run_command(
        [
            "python3",
            str(WEATHER_CLIENT),
            "--lat",
            str(venue["lat"]),
            "--lon",
            str(venue["lon"]),
            "--kickoff-utc",
            str(kickoff_utc),
        ],
        env,
    )
    try:
        weather = json.loads(result.stdout or "{}") if result.returncode == 0 else {
            "weather_status": "missing",
            "weather_reason_cn": "天气查询失败，保留上一版。",
        }
    except json.JSONDecodeError:
        weather = {"weather_status": "missing", "weather_reason_cn": "天气查询返回格式异常，保留上一版。"}
    cache = load_json(WEATHER_CACHE) if WEATHER_CACHE.is_file() else {"schema_version": "w1_weather_cache.v1", "fixtures": {}}
    cache.setdefault("schema_version", "w1_weather_cache.v1")
    cache.setdefault("fixtures", {})
    cache["fixtures"][str(selected["fixture_id"])] = {
        "fixture_id": selected["fixture_id"],
        "venue_name": venue_name,
        "lat": venue["lat"],
        "lon": venue["lon"],
        **weather,
    }
    write_json(WEATHER_CACHE, cache)
    return cache["fixtures"][str(selected["fixture_id"])]


def run_command(cmd: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=True, timeout=180)


def run_prediction(job_id: str, match: dict[str, Any]) -> None:
    global _active_job
    env = os.environ.copy()
    try:
        for idx, label in enumerate(STEPS, start=1):
            write_progress(
                progress_payload(
                    job_id=job_id,
                    status="running",
                    step_index=idx,
                    message=f"{label}中…",
                    match=match,
                )
            )
            time.sleep(0.25)

            selected_for_step = find_match_by_fixture_id(match.get("fixture_id"))
            if not selected_for_step and not match.get("fixture_id"):
                selected_for_step = find_match_by_name(match.get("home_team_cn", ""), match.get("away_team_cn", ""))
            if idx == 2 and not selected_for_step:
                write_progress(
                    progress_payload(
                        job_id=job_id,
                        status="running",
                        step_index=idx,
                        message="本地比赛记录暂缺，保留上一版。",
                        match=match,
                    )
                )

            if idx == 3:
                if env.get("W1_LOCAL_REAL_REFRESH") == "1" and env.get(ENV_KEY_NAME):
                    write_progress(
                        progress_payload(
                            job_id=job_id,
                            status="running",
                            step_index=idx,
                            message="正在通过 W1 watcher 安全入口刷新数据…",
                            match=match,
                        )
                    )
                    watcher_env = env.copy()
                    result = run_command([str(WATCHER)], watcher_env)
                    if result.returncode != 0:
                        raise RuntimeError("外部数据刷新失败，数据暂缺，保留上一版。")
                else:
                    write_progress(
                        progress_payload(
                            job_id=job_id,
                            status="running",
                            step_index=idx,
                            message="使用本地赔率快照，未触发外部刷新。",
                            match=match,
                        )
                    )

            if idx == 6:
                weather = update_weather_cache(match, env)
                weather_status = (weather or {}).get("weather_status")
                if weather_status == "ready":
                    message = "比赛环境/天气查询完成。"
                else:
                    message = "比赛环境/天气暂缺，保留上一版。"
                write_progress(
                    progress_payload(
                        job_id=job_id,
                        status="running",
                        step_index=idx,
                        message=message,
                        match=match,
                    )
                )

        build = run_command(["python3", str(BUILD_SCRIPT)], env)
        if build.returncode != 0:
            raise RuntimeError("dashboard 数据更新失败，数据暂缺，保留上一版。")

        selected = find_match_by_fixture_id(match.get("fixture_id"))
        if not selected and not match.get("fixture_id"):
            selected = find_match_by_name(match.get("home_team_cn", ""), match.get("away_team_cn", ""))
        write_progress(
            progress_payload(
                job_id=job_id,
                status="done",
                step_index=len(STEPS),
                message="查询完成，已更新 dashboard。",
                match=progress_match(selected, match.get("stage_cn", "")) if selected else match,
            )
        )
    except Exception as exc:  # noqa: BLE001 - convert all runtime failures to progress JSON
        write_progress(
            progress_payload(
                job_id=job_id,
                status="failed",
                step_index=len(STEPS),
                message="数据暂缺，保留上一版。",
                match=match,
                error=str(exc) or "数据暂缺，保留上一版。",
            )
        )
    finally:
        with _job_lock:
            _active_job = None


class Handler(SimpleHTTPRequestHandler):
    server_version = "W1LocalPredict/1.0"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler name
        path = urlparse(self.path).path
        if path == "/health":
            self.send_json({"ok": True, "service": "W1 local predict", "bind": HOST, "port": PORT})
            return
        if path == "/progress":
            if PROGRESS.is_file():
                self.send_json(load_json(PROGRESS))
            else:
                self.send_json(progress_payload(job_id="none", status="idle", step_index=1, message="等待开始预测。", match={}))
            return
        if path == "/dashboard-data":
            if DASHBOARD_DATA.is_file():
                self.send_json(load_json(DASHBOARD_DATA))
            else:
                self.send_json({"ok": False, "error_cn": "dashboard 数据不存在。"}, HTTPStatus.NOT_FOUND)
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler name
        global _active_job
        path = urlparse(self.path).path
        if path != "/predict":
            self.send_json({"ok": False, "error_cn": "接口不存在。"}, HTTPStatus.NOT_FOUND)
            return

        try:
            payload = self.read_body()
        except json.JSONDecodeError:
            self.send_json({"ok": False, "error_cn": "请求格式错误。"}, HTTPStatus.BAD_REQUEST)
            return

        match, error = resolve_predict_match(payload)
        if error:
            error_match = {
                "fixture_id": str(payload.get("fixture_id") or ""),
                "match": str(payload.get("match") or ""),
                "home_team_cn": str(payload.get("home_team_cn") or payload.get("home") or ""),
                "away_team_cn": str(payload.get("away_team_cn") or payload.get("away") or ""),
                "stage_cn": str(payload.get("stage_cn") or ""),
            }
            write_progress(progress_payload(job_id="error", status="error", step_index=1, message=error, match=error_match, error=error))
            status = HTTPStatus.NOT_FOUND if payload.get("fixture_id") else HTTPStatus.BAD_REQUEST
            self.send_json({"ok": False, "error_cn": error}, status)
            return

        with _job_lock:
            if _active_job:
                self.send_json({"ok": False, "error_cn": "已有查询正在进行，请稍后。", "job_id": _active_job}, HTTPStatus.CONFLICT)
                return
            job_id = uuid.uuid4().hex[:12]
            _active_job = job_id

        init_message = f"初始化比赛中：fixture_id={match.get('fixture_id', '未提供')}，{match.get('match') or ''}"
        write_progress(progress_payload(job_id=job_id, status="running", step_index=1, message=init_message, match=match))
        thread = threading.Thread(target=run_prediction, args=(job_id, match), daemon=True)
        thread.start()
        self.send_json({"ok": True, "job_id": job_id, "message_cn": "已开始查询。"})


def main() -> int:
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    if not PROGRESS.is_file():
        write_progress(progress_payload(job_id="none", status="idle", step_index=1, message="等待开始预测。", match={}))
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"W1 dashboard server: http://{HOST}:{PORT}/reports/dashboard/W1_VISUAL_DASHBOARD.html")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
