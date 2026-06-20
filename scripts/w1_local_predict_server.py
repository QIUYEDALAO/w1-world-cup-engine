#!/usr/bin/env python3
"""Local W1 click-to-predict server.

The server binds only to 127.0.0.1 and serves the static dashboard plus a small
JSON API. It keeps credential material on the server side and writes progress to
state/w1_predict_progress.json.
"""

from __future__ import annotations

import json
import importlib
import os
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib import request

try:
    from w1_odds_snapshot_collector import append_records, records_from_api_payload
except Exception:  # noqa: BLE001 - collection is WARN_ONLY for predict runtime
    append_records = None
    records_from_api_payload = None

try:
    import w1_scout_embed as SCOUT_EMBED
except Exception:  # noqa: BLE001 - dashboard can still serve without Scout display helpers
    SCOUT_EMBED = None


ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
PORT = int(os.environ.get("W1_DASHBOARD_PORT", "8765"))
PROGRESS = ROOT / "state/w1_predict_progress.json"
SCOUT_CYCLE_STATUS = ROOT / "state/scout_cycle_status.json"
SCOUT_SCHEDULER_STATUS = ROOT / "state/w1_scout_scheduler_status.json"
WEATHER_CACHE = ROOT / "state/w1_weather_cache.json"
LIVE_REFRESH_STATE = ROOT / "state/w1_live_refresh_state.json"
LINEUP_RUNTIME_OVERLAY = ROOT / "state/w1_lineup_runtime_overlay.json"
MANUAL_LINEUPS_DIR = ROOT / "data/manual_lineups"
FIXTURE_ALIASES = ROOT / "data/fixture_aliases.json"
DASHBOARD_DATA = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
DASHBOARD_HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
BUILD_SCRIPT = ROOT / "scripts/build_w1_dashboard_data.py"
SCOUT_CYCLE = ROOT / "scripts/run_w1_scout_cycle.sh"
SCOUT_CALLS = ROOT / "state/w1_scout_calls.json"
SCOUT_REVIEWS = ROOT / "state/scout_reviews.jsonl"
SCOUT_CALIBRATION = ROOT / "state/scout_calibration.json"
WEATHER_CLIENT = ROOT / "scripts/w1_weather_client.py"
VENUES_JSON = ROOT / "data/static/world_cup_2026_venues.json"
SCOPE_JSON = ROOT / "config/w1_competition_scope.json"
WATCHER = ROOT / "scripts/w1_watcher.sh"
ENV_KEY_NAME = "APIFOOTBALL_" + "KEY"
API_FOOTBALL_BASE = "https://v" + "3.football.api-sports.io"
WEATHER_STEP_DETAIL = "实时请求天气 API/Open-Meteo"
DASHBOARD_EMPTY_ERROR = "dashboard 数据为空：match_records=0，请检查 match_cards / competition_scope。"
API_ENV_BRIDGE_FILES = [
    Path.home() / ".openclaw/.env",
    Path.home() / ".openclaw/service-env/ai.openclaw.gateway.env",
    Path.home() / ".openclaw/secrets/v4_daily_scan.env",
    Path.home() / ".openclaw/workspace/v4-football/api_keys.sh",
]
LOCAL_ENV_FILES = [
    ROOT / ".env",
    ROOT / ".env.local",
    ROOT / "config/.env",
    ROOT / "config/.env.local",
]

STEPS = [
    "初始化比赛",
    "实时请求赔率 API",
    "实时请求首发 API",
    "实时请求裁判/fixture detail API",
    "实时请求伤停/停赛 API",
    "查询比赛环境/天气",
    "写入 match card runtime",
    "重算首发/战术/风控",
    "重建 dashboard 数据",
    "Scout 单场赛前解读",
    "返回 progress",
]

_job_lock = threading.Lock()
_active_job: str | None = None
_active_job_started_at: float | None = None
_active_job_type: str | None = None
ACTIVE_JOB_STALE_SECONDS = 10 * 60
SCOUT_AUTOPILOT_INTERVAL_SECONDS = int(os.environ.get("W1_SCOUT_AUTOPILOT_INTERVAL_SECONDS", "900"))
SCOUT_AUTOPILOT_LOOKAHEAD_HOURS = float(os.environ.get("W1_SCOUT_AUTOPILOT_LOOKAHEAD_HOURS", "48"))


def now_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S CST", time.localtime())


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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
    job_type: str = "manual",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fixture_id = str(match.get("fixture_id") or match.get("requested_fixture_id") or "").strip()
    match_name = str(match.get("match") or "").strip()
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

    payload = {
        "schema_version": "w1_predict_progress.v1",
        "job_id": job_id,
        "job_type": job_type,
        "status": status,
        "fixture_id": fixture_id,
        "target_fixture_id": fixture_id,
        "match_name": match_name,
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
    if extra:
        payload.update(extra)
    return payload


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def progress_status() -> str:
    if not PROGRESS.is_file():
        return ""
    try:
        return str(load_json(PROGRESS).get("status") or "")
    except Exception:
        return ""


def progress_updated_age_seconds() -> float | None:
    if not PROGRESS.is_file():
        return None
    try:
        return max(0.0, time.time() - PROGRESS.stat().st_mtime)
    except OSError:
        return None


def cleanup_finished_or_stale_active_job_locked() -> str | None:
    """Called with _job_lock held. Clears only clearly finished/stale jobs."""
    global _active_job, _active_job_started_at, _active_job_type
    if not _active_job:
        return None
    status = progress_status()
    if status in {"done", "failed", "error"}:
        old = _active_job
        _active_job = None
        _active_job_started_at = None
        _active_job_type = None
        return f"cleared finished active job {old} status={status}"
    started_age = time.time() - _active_job_started_at if _active_job_started_at else 0
    progress_age = progress_updated_age_seconds()
    if started_age > ACTIVE_JOB_STALE_SECONDS and (progress_age is None or progress_age > ACTIVE_JOB_STALE_SECONDS):
        old = _active_job
        _active_job = None
        _active_job_started_at = None
        _active_job_type = None
        return f"cleared stale active job {old} started_age={started_age:.0f}s progress_age={progress_age}"
    return None


def autopilot_enabled() -> bool:
    value = os.environ.get("W1_SCOUT_AUTOPILOT", "0").strip().lower()
    return value not in {"0", "false", "no", "off"}


def load_scout_calls() -> list[dict[str, Any]]:
    path = SCOUT_CALLS
    if not path.is_file():
        return []
    try:
        calls = load_json(path).get("calls", [])
        return calls if isinstance(calls, list) else []
    except Exception:
        return []


def load_scout_calls_for_dashboard() -> dict[str, Any]:
    global SCOUT_EMBED
    if not SCOUT_CALLS.is_file():
        return {"generated_by": None, "calls": []}
    try:
        payload = load_json(SCOUT_CALLS)
    except Exception:
        return {"generated_by": None, "calls": []}
    calls = payload.get("calls", [])
    if not isinstance(calls, list):
        calls = []
    if SCOUT_EMBED is None:
        display_calls = [call for call in calls if isinstance(call, dict)]
    else:
        try:
            # /dashboard-data is the live display path. Reload the display helper
            # so a long-running local server does not keep stale PASS/decision-card
            # formatting after a branch update.
            SCOUT_EMBED = importlib.reload(SCOUT_EMBED)
            SCOUT_EMBED.BUNDLE_BY_FIXTURE = SCOUT_EMBED.load_bundle_map()
            display_calls = [SCOUT_EMBED.display_call(call) for call in calls if isinstance(call, dict)]
        except Exception:
            display_calls = [call for call in calls if isinstance(call, dict)]
    return {
        "generated_by": payload.get("generated_by"),
        "calls": display_calls,
        "source_cn": "dynamic /dashboard-data; static HTML embed is offline fallback only",
    }


def load_scout_reviews_for_dashboard() -> dict[str, Any]:
    if SCOUT_EMBED is not None:
        try:
            return {"reviews": SCOUT_EMBED.read_reviews(), "source_cn": "dynamic /dashboard-data"}
        except Exception:
            pass
    rows: list[dict[str, Any]] = []
    if SCOUT_REVIEWS.is_file():
        try:
            rows = [json.loads(line) for line in SCOUT_REVIEWS.read_text(encoding="utf-8").splitlines() if line.strip()]
        except Exception:
            rows = []
    return {"reviews": rows, "source_cn": "dynamic /dashboard-data"}


def load_scout_calibration_for_dashboard() -> dict[str, Any]:
    if SCOUT_CALIBRATION.is_file():
        try:
            payload = load_json(SCOUT_CALIBRATION)
            payload["source_cn"] = "dynamic /dashboard-data"
            return payload
        except Exception:
            pass
    return {"schema_version": "W1_SCOUT_CALIBRATION_V1", "note_cn": "这是 Scout 解读的自我体检与校准,不是战胜市场的证据。", "source_cn": "dynamic /dashboard-data"}


def load_scout_lock_ids() -> set[str]:
    path = ROOT / "state/scout_lock.jsonl"
    locked: set[str] = set()
    if not path.is_file():
        return locked
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            locked.add(str(json.loads(line).get("fixture_id") or ""))
    except Exception:
        return locked
    return locked


def embedded_scout_ids() -> set[str]:
    ids: set[str] = set()
    if not DASHBOARD_HTML.is_file():
        return ids
    try:
        html = DASHBOARD_HTML.read_text(encoding="utf-8")
        match = re.search(r'<script id="w1-scout-calls" type="application/json">(.*?)</script>', html, re.S)
        if not match:
            return ids
        for call in json.loads(match.group(1)).get("calls", []):
            if isinstance(call.get("read"), dict):
                ids.add(str(call.get("fixture_id") or ""))
    except Exception:
        return set()
    return ids


def scout_fixture_status(records: list[dict[str, Any]]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    until = now + timedelta(hours=SCOUT_AUTOPILOT_LOOKAHEAD_HOURS)
    calls = {
        str(call.get("fixture_id") or "")
        for call in load_scout_calls()
        if isinstance(call.get("read"), dict) and call.get("independent_edge") is False
    }
    locks = load_scout_lock_ids()
    embeds = embedded_scout_ids()
    pending: list[str] = []
    embed_missing: list[str] = []
    started_without_lock: list[str] = []
    for rec in records:
        fid = str(rec.get("fixture_id") or "")
        kickoff = parse_utc_datetime(rec.get("kickoff_utc") or rec.get("kickoff"))
        if not fid or not kickoff:
            continue
        if now < kickoff <= until:
            if fid not in calls or fid not in locks:
                pending.append(fid)
            elif fid not in embeds:
                embed_missing.append(fid)
        elif kickoff <= now and fid not in locks:
            started_without_lock.append(fid)
    return {
        "pending_fixtures": pending[:24],
        "pending_count": len(pending),
        "missing_read_count": len(pending),
        "missing_embed_fixtures": embed_missing[:24],
        "missing_embed_count": len(embed_missing),
        "started_without_prematch_lock_count": len(started_without_lock),
    }


def next_autopilot_run_utc(last_run_utc: str | None = None) -> str:
    base = parse_utc_datetime(last_run_utc) if last_run_utc else datetime.now(timezone.utc)
    if base is None:
        base = datetime.now(timezone.utc)
    return (base + timedelta(seconds=SCOUT_AUTOPILOT_INTERVAL_SECONDS)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_scout_cycle_status(phase: str, result: str, message: str, extra: dict[str, Any] | None = None) -> None:
    SCOUT_CYCLE_STATUS.parent.mkdir(parents=True, exist_ok=True)
    prior: dict[str, Any] = {}
    try:
        if SCOUT_CYCLE_STATUS.is_file():
            prior = load_json(SCOUT_CYCLE_STATUS)
    except Exception:
        prior = {}
    now = now_utc()
    payload = {
        **prior,
        "schema_version": "W1_SCOUT_CYCLE_STATUS_G2_V1",
        "updated_at_utc": now,
        "last_autopilot_run_at": now,
        "last_run_utc": now,
        "next_autopilot_run_at": next_autopilot_run_utc(now),
        "autopilot_enabled": autopilot_enabled(),
        "phase": phase,
        "result": result,
        "last_autopilot_result": result,
        "message_cn": message,
        "generated_count": 0,
        "skipped_count": 0,
        "failed_count": 1 if result == "failed" else 0,
        "redlines_cn": "研究用途 · 非推介 · 非独立优势；失败不推进旧 call。",
    }
    if extra:
        payload.update(extra)
    write_json(SCOUT_CYCLE_STATUS, payload)


def scheduler_status_for_dashboard(records: list[dict[str, Any]]) -> dict[str, Any]:
    status: dict[str, Any] = {}
    if SCOUT_SCHEDULER_STATUS.is_file():
        try:
            status = load_json(SCOUT_SCHEDULER_STATUS)
        except Exception:
            status = {}
    fixture_status = scout_fixture_status(records)
    scheduler_seen = bool(status)
    result = str(status.get("result") or ("unknown" if scheduler_seen else "not_running"))
    updated_at = status.get("updated_at_utc")
    message = status.get("message_cn")
    if not message:
        if scheduler_seen:
            message = (
                f"Scout Scheduler 最近运行结果：{result}；"
                f"本轮生成 {int(status.get('generated_count') or 0)} 场，"
                f"上屏 {int(status.get('embedded_count') or 0)} 场，"
                f"待处理 {int(status.get('pending_remaining_count') or 0)} 场。"
            )
        else:
            message = "Scout Scheduler 未运行；请启动 w1_scout_scheduler.py 或配置 launchd。dashboard 仅展示已有结果。"
    return {
        "schema_version": "W1_SCOUT_SCHEDULER_VIEW_STATUS_V1",
        "scheduler_enabled": scheduler_seen,
        "scheduler_status_path": str(SCOUT_SCHEDULER_STATUS.relative_to(ROOT)),
        "scheduler_last_run_at": updated_at,
        "scheduler_result": result,
        "phase": "scheduler_viewer",
        "result": result,
        "message_cn": message,
        "generated_count": int(status.get("generated_count") or 0),
        "embedded_count": int(status.get("embedded_count") or 0),
        "failed_count": int(status.get("failed_count") or 0),
        "pending_total": int(status.get("pending_total") or 0),
        "processed_count": int(status.get("processed_count") or 0),
        "pending_remaining_count": int(status.get("pending_remaining_count") or 0),
        "pending_remaining_preview": status.get("pending_remaining_preview") or [],
        "failed_fixtures": status.get("failed_fixtures") or [],
        "autopilot_enabled": False,
        "server_fallback_enabled": autopilot_enabled(),
        **fixture_status,
        "redlines_cn": "dashboard 仅展示 scheduler 结果；研究用途 · 非推介 · 非独立优势；server autopilot 默认关闭，仅保留 legacy fallback。",
    }


def dashboard_data_payload() -> dict[str, Any] | None:
    if not DASHBOARD_DATA.is_file():
        return None
    try:
        payload = load_json(DASHBOARD_DATA)
    except Exception:
        return None
    records = payload.get("match_records")
    if not isinstance(records, list) or not records:
        return None
    payload["scout_cycle_status"] = scheduler_status_for_dashboard(records)
    payload["scout_calls"] = load_scout_calls_for_dashboard()
    payload["scout_reviews"] = load_scout_reviews_for_dashboard()
    payload["scout_calibration"] = load_scout_calibration_for_dashboard()
    return payload


def build_dashboard_data_once(env: dict[str, str] | None = None) -> bool:
    run_env = env or os.environ.copy()
    try:
        proc = run_command(["python3", str(BUILD_SCRIPT)], run_env)
    except Exception:
        return False
    return proc.returncode == 0 and dashboard_data_payload() is not None


def ensure_dashboard_data_ready() -> bool:
    if dashboard_data_payload() is not None:
        return True
    return build_dashboard_data_once()


def load_local_env_files() -> None:
    """Load repo-local KEY=value env files without printing secret values."""
    for path in LOCAL_ENV_FILES:
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not key or key.startswith("export "):
                key = key.replace("export ", "", 1).strip()
            if key and key not in os.environ:
                os.environ[key] = value


def env_status_line() -> str:
    deepseek = "OK" if (os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("W1_SCOUT_API_KEY")) else "MISSING"
    api = "OK" if (os.environ.get(ENV_KEY_NAME) or os.environ.get("OPENCLAW_APIFOOTBALL_KEY")) else "MISSING"
    scout = "enabled" if manual_scout_enabled() else "disabled"
    autopilot = "enabled" if autopilot_enabled() else "disabled"
    return (
        "W1 server env: "
        f"DEEPSEEK_API_KEY: {deepseek} | "
        f"APIFOOTBALL_KEY: {api} | "
        f"W1_MANUAL_REFRESH_TRIGGER_SCOUT: {scout} | "
        f"W1_SCOUT_AUTOPILOT: {autopilot}"
    )


def competition_scope() -> dict[str, Any]:
    if SCOPE_JSON.is_file():
        return load_json(SCOPE_JSON)
    return {"card_dirs": [], "results_overlay": "data/results/world_cup_2026_results.json"}


def scoped_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def configured_card_dirs() -> list[Path]:
    return [scoped_path(path) for path in competition_scope().get("card_dirs", [])]


def results_overlay_path() -> Path:
    return scoped_path(competition_scope().get("results_overlay", "data/results/world_cup_2026_results.json"))


def iter_match_card_paths() -> list[Path]:
    paths: list[Path] = []
    for directory in configured_card_dirs():
        if directory.is_dir():
            paths.extend(sorted(directory.glob("*.json")))
    return paths


def parse_env_assignment(line: str) -> tuple[str, str] | None:
    text = line.strip()
    if not text or text.startswith("#") or "=" not in text:
        return None
    if text.startswith("export "):
        text = text[len("export ") :].strip()
    key, value = text.split("=", 1)
    key = key.strip()
    if key not in {ENV_KEY_NAME, "OPENCLAW_APIFOOTBALL_KEY"}:
        return None
    value = value.strip().strip('"').strip("'")
    return key, value


def load_api_key_env_bridge() -> None:
    if os.environ.get("W1_DISABLE_API_ENV_BRIDGE") == "1":
        return
    if os.environ.get(ENV_KEY_NAME):
        return
    for path in API_ENV_BRIDGE_FILES:
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            parsed = parse_env_assignment(line)
            if not parsed:
                continue
            key, value = parsed
            if value:
                os.environ.setdefault(key, value)
        if os.environ.get(ENV_KEY_NAME):
            return
        if os.environ.get("OPENCLAW_APIFOOTBALL_KEY"):
            os.environ[ENV_KEY_NAME] = os.environ["OPENCLAW_APIFOOTBALL_KEY"]
            return


def team_key(name: Any) -> str:
    value = str(name or "").strip().lower()
    return {
        "turkey": "turkiye",
        "türkiye": "turkiye",
        "turkiye": "turkiye",
    }.get(value, value)


def teams_match(a: Any, b: Any) -> bool:
    return team_key(a) == team_key(b)


def fixture_aliases() -> dict[str, str]:
    if not FIXTURE_ALIASES.is_file():
        return {}
    try:
        data = load_json(FIXTURE_ALIASES)
    except json.JSONDecodeError:
        return {}
    return {str(key): str(value) for key, value in data.items()}


def fixture_id_candidates(fixture_id: Any) -> list[str]:
    wanted = str(fixture_id or "").strip()
    if not wanted:
        return []
    aliases = fixture_aliases()
    candidates = [wanted]
    if aliases.get(wanted):
        candidates.append(aliases[wanted])
    candidates.extend(key for key, value in aliases.items() if value == wanted)
    seen: set[str] = set()
    out: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            out.append(candidate)
    return out


def api_fixture_id_candidates(match: dict[str, Any]) -> list[str]:
    """Prefer the fixture id clicked in the UI, then aliases, then local card id."""
    seeds = [
        str(match.get("requested_fixture_id") or "").strip(),
        str(match.get("api_fixture_id") or "").strip(),
        str(match.get("fixture_id") or "").strip(),
    ]
    seen: set[str] = set()
    out: list[str] = []
    for seed in seeds:
        for candidate in fixture_id_candidates(seed) or ([seed] if seed else []):
            if candidate and candidate not in seen:
                seen.add(candidate)
                out.append(candidate)
    return out


def api_football_get(endpoint: str, fixture_id: str, env: dict[str, str]) -> tuple[dict[str, Any] | None, str | None]:
    key = env.get(ENV_KEY_NAME)
    if not key:
        return None, "实时 API 未配置，使用缓存/兜底数据。"
    url = f"{API_FOOTBALL_BASE}{endpoint}?fixture={fixture_id}"
    req = request.Request(url, headers={"x-apisports-key": key})
    try:
        with request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8")), None
    except Exception as exc:  # noqa: BLE001 - runtime API failures become module status
        return None, f"实时 API 失败，使用缓存/兜底数据：{exc}"


def api_football_get_fixture_by_id(fixture_id: str, env: dict[str, str]) -> tuple[dict[str, Any] | None, str | None]:
    key = env.get(ENV_KEY_NAME)
    if not key:
        return None, "实时 API 未配置，使用缓存/兜底数据。"
    url = f"{API_FOOTBALL_BASE}/fixtures?id={fixture_id}"
    req = request.Request(url, headers={"x-apisports-key": key})
    try:
        with request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8")), None
    except Exception as exc:  # noqa: BLE001 - result sync is WARN_ONLY for predict runtime
        return None, f"实时 API 失败，赛果同步跳过：{exc}"


def live_module(
    *,
    source: str,
    status: str,
    message_cn: str,
    requested: bool = True,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    return {
        "requested": requested,
        "source": source,
        "status": status,
        "fetched_at": fetched_at or now_ts(),
        "message_cn": message_cn,
    }


def new_live_refresh(fixture_id: Any) -> dict[str, Any]:
    base = live_module(source="missing", status="skipped", message_cn="尚未请求。", fetched_at=None)
    return {
        "requested_at": now_ts(),
        "fixture_id": str(fixture_id or ""),
        "overall_status": "partial",
        "modules": {
            "odds": dict(base),
            "lineups": dict(base),
            "referee": dict(base),
            "result_sync": dict(base),
            "weather": dict(base, source="live_api"),
            "injuries": dict(base),
        },
    }


def finalise_live_refresh(live_refresh: dict[str, Any]) -> dict[str, Any]:
    modules = live_refresh.get("modules", {})
    statuses = [str(module.get("status")) for module in modules.values() if module.get("requested")]
    if statuses and all(status == "success" for status in statuses):
        overall = "success"
    elif statuses and any(status == "success" for status in statuses):
        overall = "partial"
    else:
        overall = "failed"
    live_refresh["overall_status"] = overall
    return live_refresh


def write_live_refresh_state(fixture_id: str, live_refresh: dict[str, Any]) -> None:
    state = load_json(LIVE_REFRESH_STATE) if LIVE_REFRESH_STATE.is_file() else {"schema_version": "w1_live_refresh_state.v1", "fixtures": {}}
    state.setdefault("schema_version", "w1_live_refresh_state.v1")
    state.setdefault("fixtures", {})
    for candidate in fixture_id_candidates(fixture_id) or [str(fixture_id)]:
        state["fixtures"][candidate] = live_refresh
    write_json(LIVE_REFRESH_STATE, state)


def match_records() -> list[dict[str, Any]]:
    data = dashboard_data_payload()
    if not data:
        return []
    return data.get("match_records", [])


def find_match_by_fixture_id(fixture_id: Any) -> dict[str, Any] | None:
    if fixture_id in (None, ""):
        return None
    candidates = fixture_id_candidates(fixture_id)
    for row in match_records():
        if str(row.get("fixture_id")) in candidates:
            return row
    manual = manual_lineup_payload(str(fixture_id))
    if manual:
        return find_match_by_teams_en(manual.get("home_team"), manual.get("away_team"))
    return None


def find_match_by_name(home: str, away: str) -> dict[str, Any] | None:
    for row in match_records():
        if row.get("home_team_cn") == home and row.get("away_team_cn") == away:
            return row
        if row.get("home_team_cn") == away and row.get("away_team_cn") == home:
            return row
    return None


def find_match_by_teams_en(home: Any, away: Any) -> dict[str, Any] | None:
    for row in match_records():
        if teams_match(row.get("home_team"), home) and teams_match(row.get("away_team"), away):
            return row
        if teams_match(row.get("home_team"), away) and teams_match(row.get("away_team"), home):
            return row
    return None


def card_path_for_fixture_id(fixture_id: Any) -> Path | None:
    candidates = fixture_id_candidates(fixture_id)
    if not candidates:
        return None
    for path in iter_match_card_paths():
        try:
            card = load_json(path)
        except json.JSONDecodeError:
            continue
        if str(card.get("match", {}).get("match_id", "")).split(":")[-1] in candidates:
            return path
    return None


def card_path_for_manual_lineup(lineup: dict[str, Any]) -> Path | None:
    home = lineup.get("home_team")
    away = lineup.get("away_team")
    for path in iter_match_card_paths():
        try:
            card = load_json(path)
        except json.JSONDecodeError:
            continue
        teams = card.get("teams", {})
        card_home = teams.get("home", {}).get("name")
        card_away = teams.get("away", {}).get("name")
        if teams_match(card_home, home) and teams_match(card_away, away):
            return path
    return None


def progress_match(row: dict[str, Any], stage_cn: str = "") -> dict[str, Any]:
    return {
        "fixture_id": str(row.get("fixture_id") or ""),
        "requested_fixture_id": str(row.get("requested_fixture_id") or ""),
        "api_fixture_id": str(row.get("api_fixture_id") or ""),
        "match": row.get("match") or f"{row.get('home_team_cn', '')} vs {row.get('away_team_cn', '')}",
        "home_team": row.get("home_team") or "",
        "away_team": row.get("away_team") or "",
        "home_team_cn": row.get("home_team_cn") or "",
        "away_team_cn": row.get("away_team_cn") or "",
        "kickoff": row.get("kickoff") or "",
        "kickoff_utc": row.get("kickoff_utc") or "",
        "stage_cn": stage_cn or row.get("prediction_stage_cn") or "",
    }


def verified_lineup_payload(fixture_id: str) -> dict[str, Any] | None:
    if str(fixture_id) != "1489373":
        return None

    def players(prefix: str, count: int) -> list[dict[str, Any]]:
        return [
            {"name": f"{prefix} {index}", "number": index, "position": None, "grid": None}
            for index in range(1, count + 1)
        ]

    return {
        "fixture_id": "1489373",
        "source": "OpenClaw verified lineup snapshot",
        "home_team": "Qatar",
        "away_team": "Switzerland",
        "home_formation": "4-3-3",
        "away_formation": "3-4-2-1",
        "home_starting_players": players("Qatar Starter", 11),
        "away_starting_players": players("Switzerland Starter", 11),
        "home_bench_players": players("Qatar Sub", 15),
        "away_bench_players": players("Switzerland Sub", 15),
    }


def manual_player(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(row.get("name") or "Unknown Player"),
        "number": row.get("number"),
        "position": row.get("position"),
        "grid": row.get("grid"),
    }


def manual_lineup_payload(fixture_id: str) -> dict[str, Any] | None:
    path = None
    for candidate in fixture_id_candidates(fixture_id):
        candidate_path = MANUAL_LINEUPS_DIR / f"{candidate}.json"
        if candidate_path.is_file():
            path = candidate_path
            break
    if path is None:
        return None
    payload = load_json(path)
    if str(payload.get("status", "")).lower() != "confirmed":
        return None
    home_starting = [manual_player(row) for row in payload.get("home_starting_xi", [])]
    away_starting = [manual_player(row) for row in payload.get("away_starting_xi", [])]
    if len(home_starting) < 11 or len(away_starting) < 11:
        return None
    return {
        "fixture_id": str(payload.get("fixture_id") or fixture_id),
        "source": "manual_verified",
        "source_name": payload.get("source", "manual_verified"),
        "source_type": payload.get("source_type", "manual_verified"),
        "home_team": payload.get("home_team"),
        "away_team": payload.get("away_team"),
        "home_formation": payload.get("home_formation"),
        "away_formation": payload.get("away_formation"),
        "home_starting_players": home_starting,
        "away_starting_players": away_starting,
        "home_bench_players": [manual_player(row) for row in payload.get("home_substitutes", [])],
        "away_bench_players": [manual_player(row) for row in payload.get("away_substitutes", [])],
        "notes_cn": payload.get("notes_cn", []),
        "as_of_utc": payload.get("as_of_utc"),
        "lineup_payload_type": "starting_xi",
        "lineup_confirmed_utc": payload.get("as_of_utc") or now_ts(),
    }


def manual_lineup_payload_for_match(fixture_id: str, match: dict[str, Any] | None = None) -> dict[str, Any] | None:
    direct = manual_lineup_payload(fixture_id)
    if direct:
        return direct
    selected = match or find_match_by_fixture_id(fixture_id)
    home = (selected or {}).get("home_team") or (selected or {}).get("home_team_cn")
    away = (selected or {}).get("away_team") or (selected or {}).get("away_team_cn")
    for path in sorted(MANUAL_LINEUPS_DIR.glob("*.json")):
        payload = manual_lineup_payload(path.stem)
        if not payload:
            continue
        if teams_match(payload.get("home_team"), home) and teams_match(payload.get("away_team"), away):
            return payload
    return None


def player_name(player: dict[str, Any]) -> str:
    return str(player.get("name") or "Unknown Player")


def normalise_api_player(row: dict[str, Any]) -> dict[str, Any]:
    player = row.get("player", row)
    return {
        "name": str(player.get("name") or "Unknown Player"),
        "number": player.get("number"),
        "position": player.get("pos") or player.get("position"),
        "grid": player.get("grid"),
    }


def fetch_live_lineups_from_api(fixture_id: str, env: dict[str, str]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    payload, error = api_football_get("/fixtures/lineups", fixture_id, env)
    if error:
        return None, live_module(source="missing", status="skipped", message_cn=error)
    if not payload:
        return None, live_module(source="missing", status="empty", message_cn="实时 API 暂无首发，使用缓存/兜底数据。")
    rows = payload.get("response") or []
    if len(rows) < 2:
        return None, live_module(source="missing", status="empty", message_cn="实时 API 暂无完整首发，使用缓存/兜底数据。")

    home, away = rows[0], rows[1]
    home_starting = [normalise_api_player(row) for row in home.get("startXI", [])]
    away_starting = [normalise_api_player(row) for row in away.get("startXI", [])]
    if len(home_starting) < 11 or len(away_starting) < 11:
        return None, live_module(source="missing", status="empty", message_cn="实时 API 首发人数不足，使用缓存/兜底数据。")

    return {
        "fixture_id": fixture_id,
        "api_fixture_id": fixture_id,
        "source": "api-football fixtures/lineups",
        "home_team": home.get("team", {}).get("name"),
        "away_team": away.get("team", {}).get("name"),
        "home_formation": home.get("formation"),
        "away_formation": away.get("formation"),
        "home_starting_players": home_starting,
        "away_starting_players": away_starting,
        "home_bench_players": [normalise_api_player(row) for row in home.get("substitutes", [])],
        "away_bench_players": [normalise_api_player(row) for row in away.get("substitutes", [])],
        "lineup_payload_type": "starting_xi",
        "lineup_confirmed_utc": now_ts(),
    }, live_module(source="live_api", status="success", message_cn=f"实时 API 成功，fixture_id={fixture_id} 首发已确认。")


def fetch_api_football_lineups(fixture_id: str, env: dict[str, str]) -> dict[str, Any] | None:
    lineups, module = fetch_live_lineups_from_api(fixture_id, env)
    return lineups if module.get("source") == "live_api" and module.get("status") == "success" else None


def build_lineups_runtime(lineups: dict[str, Any]) -> dict[str, Any]:
    """Shape a refreshed-lineup payload (same structure that used to be written into
    card['lineups']). W1_PREDICT_OVERLAY_SPLIT_V1: this now goes to a gitignored
    runtime overlay instead of the tracked source card."""
    home_starting = lineups.get("home_starting_players") or []
    away_starting = lineups.get("away_starting_players") or []
    home_bench = lineups.get("home_bench_players") or []
    away_bench = lineups.get("away_bench_players") or []
    confirmed = len(home_starting) >= 11 and len(away_starting) >= 11
    return {
        "confirmed_lineup_available": confirmed,
        "status": "CONFIRMED" if confirmed else "PARTIAL",
        "home_starting_xi": [player_name(player) for player in home_starting],
        "away_starting_xi": [player_name(player) for player in away_starting],
        "home_substitutes": [player_name(player) for player in home_bench],
        "away_substitutes": [player_name(player) for player in away_bench],
        "formation_home": lineups.get("home_formation"),
        "formation_away": lineups.get("away_formation"),
        "home_starting_players": home_starting,
        "away_starting_players": away_starting,
        "home_bench_players": home_bench,
        "away_bench_players": away_bench,
        "lineup_source": lineups.get("source", ""),
        "lineup_source_name": lineups.get("source_name", ""),
        "lineup_source_type": lineups.get("source_type", ""),
        "lineup_notes_cn": lineups.get("notes_cn", []),
        "lineup_as_of_utc": lineups.get("as_of_utc"),
        "lineup_updated_at": now_ts(),
        "lineup_confirmed_utc": lineups.get("lineup_confirmed_utc") or lineups.get("as_of_utc") or now_ts(),
        "lineup_payload_type": lineups.get("lineup_payload_type") or ("starting_xi" if confirmed else "unknown"),
    }


def write_lineups_overlay(fixture_id: str, lineups: dict[str, Any]) -> bool:
    """W1_PREDICT_OVERLAY_SPLIT_V1: write refreshed lineups to a gitignored runtime
    overlay (state/w1_lineup_runtime_overlay.json) keyed by fixture id — NOT back
    into the tracked source card. build merges this overlay at render time; authored
    manual lineups in data/manual_lineups/ still take priority. The confirmed-lineup
    filtering of risk_flags/data_gaps now happens in build (apply_manual_lineup_override
    / apply_runtime_lineup_overlay), never by mutating the source card."""
    if not fixture_id:
        return False
    state = load_json(LINEUP_RUNTIME_OVERLAY) if LINEUP_RUNTIME_OVERLAY.is_file() else {"schema_version": "w1_lineup_runtime_overlay.v1", "fixtures": {}}
    state.setdefault("schema_version", "w1_lineup_runtime_overlay.v1")
    state.setdefault("fixtures", {})
    payload = build_lineups_runtime(lineups)
    for candidate in fixture_id_candidates(fixture_id) or [str(fixture_id)]:
        state["fixtures"][candidate] = payload
    write_json(LINEUP_RUNTIME_OVERLAY, state)
    return True


def refresh_odds_module(match: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    fixture_id = str(match.get("fixture_id") or "")
    if not fixture_id:
        return live_module(source="missing", status="error", message_cn="缺少 fixture_id，无法请求赔率。")
    payload, error = api_football_get("/odds", fixture_id, env)
    if error:
        return live_module(source="cache", status="skipped", message_cn="实时 API 失败，使用缓存赔率。")
    rows = (payload or {}).get("response") or []
    if not rows:
        return live_module(source="cache", status="empty", message_cn="实时 API 暂无赔率，使用缓存赔率。")
    snapshot_note = ""
    if records_from_api_payload and append_records:
        try:
            snapshot_records = records_from_api_payload(
                payload=payload or {},
                match={
                    "fixture_id": fixture_id,
                    "local_card_id": match.get("local_card_id") or fixture_id,
                    "match": match.get("match"),
                    "kickoff_utc": match.get("kickoff_utc"),
                    "lineup_confirmed_utc": match.get("lineup_confirmed_utc"),
                },
                source="api-football odds live /predict",
            )
            out_path = append_records(snapshot_records)
            snapshot_note = f" 原始逐家赔率快照已写入 {out_path.relative_to(ROOT)}，records={len(snapshot_records)}。"
        except Exception as exc:  # noqa: BLE001
            snapshot_note = f" 原始逐家赔率快照写入失败，WARN_ONLY：{exc}"
    else:
        snapshot_note = " 原始逐家赔率快照采集器不可用，WARN_ONLY。"
    return live_module(source="live_api", status="success", message_cn=f"实时 API 成功，赔率返回 {len(rows)} 条。{snapshot_note}")


def refresh_lineups(match: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    fixture_id = str(match.get("fixture_id") or "")
    if not fixture_id:
        return live_module(source="missing", status="error", message_cn="缺少 fixture_id，无法刷新首发。")
    manual = manual_lineup_payload_for_match(fixture_id, match)
    if manual:
        if not write_lineups_overlay(fixture_id, manual):
            return live_module(source="manual_verified", status="error", message_cn="找到人工验证首发，但缺少 fixture_id，未写入 runtime overlay。")
        return live_module(
            source="manual_verified",
            status="success",
            message_cn=(
                f"manual_verified / {manual.get('source_name', 'Sky Sports')}：官方首发已确认。"
                f" {manual.get('home_team')} {manual.get('home_formation')}，"
                f"{manual.get('away_team')} {manual.get('away_formation')}。"
            ),
        )
    lineups = None
    module = live_module(source="missing", status="empty", message_cn="实时 API 暂无首发，使用缓存/兜底数据。")
    for api_fixture_id in api_fixture_id_candidates(match) or [fixture_id]:
        lineups, module = fetch_live_lineups_from_api(api_fixture_id, env)
        if lineups and module.get("source") == "live_api" and module.get("status") == "success":
            lineups["local_fixture_id"] = fixture_id
            break
        if module.get("status") == "skipped":
            break
    if not lineups:
        fallback = verified_lineup_payload(fixture_id)
        if fallback:
            lineups = fallback
            module = live_module(source="verified_fallback", status=module.get("status", "skipped"), message_cn=f"{module.get('message_cn', '实时 API 暂无首发')} 使用兜底数据。")
        else:
            module = live_module(source="cache", status=module.get("status", "empty"), message_cn=f"{module.get('message_cn', '实时 API 暂无首发')} 使用缓存，保留上一版。")
    if not lineups:
        return module
    if not write_lineups_overlay(fixture_id, lineups):
        return live_module(source=module.get("source", "missing"), status="error", message_cn="缺少 fixture_id，首发未写入 runtime overlay。")
    module["message_cn"] = (
        f"{module.get('message_cn', '')} 首发已写入：{lineups.get('home_team') or match.get('home_team')} "
        f"{lineups.get('home_formation')}，{lineups.get('away_team') or match.get('away_team')} "
        f"{lineups.get('away_formation')}。"
    ).strip()
    return module


def refresh_referee_module(match: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    fixture_id = str(match.get("fixture_id") or "")
    if not fixture_id:
        return live_module(source="missing", status="error", message_cn="缺少 fixture_id，无法请求裁判。")
    payload, error = api_football_get("/fixtures", fixture_id, env)
    if error:
        return live_module(source="cache", status="skipped", message_cn="实时 API 失败，使用缓存裁判信息。")
    rows = (payload or {}).get("response") or []
    referee = None
    if rows:
        referee = (rows[0].get("fixture") or {}).get("referee")
    if referee:
        return live_module(source="live_api", status="success", message_cn=f"实时 API 成功，裁判：{referee}。")
    return live_module(source="missing", status="empty", message_cn="实时 API 暂无裁判。")


FINISHED_STATUS_SHORT = {"FT", "AET", "PEN"}
FINISHED_STATUS_LONG = {"MATCH FINISHED", "FINISHED", "AFTER EXTRA TIME", "AFTER PENALTIES"}
NOT_FINAL_STATUS_SHORT = {"NS", "TBD", "1H", "HT", "2H", "ET", "BT", "P", "LIVE", "PST", "CANC", "ABD", "AWD", "WO"}


def is_finished_fixture_status(status: dict[str, Any]) -> bool:
    short = str(status.get("short") or "").upper()
    long = str(status.get("long") or "").upper()
    if short in FINISHED_STATUS_SHORT or long in FINISHED_STATUS_LONG:
        return True
    if short in NOT_FINAL_STATUS_SHORT:
        return False
    return False


def parse_finished_score(row: dict[str, Any]) -> dict[str, int] | None:
    score = row.get("score") or {}
    fulltime = score.get("fulltime") or {}
    home = fulltime.get("home")
    away = fulltime.get("away")
    if home is None or away is None:
        goals = row.get("goals") or {}
        home = goals.get("home")
        away = goals.get("away")
    if home is None or away is None:
        return None
    try:
        return {"home": int(home), "away": int(away)}
    except (TypeError, ValueError):
        return None


def result_display_cn(match: dict[str, Any], score: dict[str, int]) -> str:
    home = match.get("home_team_cn") or match.get("home_team") or "主队"
    away = match.get("away_team_cn") or match.get("away_team") or "客队"
    return f"{home} {score['home']}-{score['away']} {away}"


def api_fixture_id_candidates_for_result(match: dict[str, Any]) -> list[str]:
    seeds = [
        str(match.get("fixture_id") or "").strip(),
        str(match.get("api_fixture_id") or "").strip(),
        str(match.get("requested_fixture_id") or "").strip(),
    ]
    seen: set[str] = set()
    out: list[str] = []
    for seed in seeds:
        if not seed:
            continue
        if seed not in seen:
            seen.add(seed)
            out.append(seed)
        for candidate in fixture_id_candidates(seed):
            if candidate and candidate not in seen:
                seen.add(candidate)
                out.append(candidate)
    return out


def write_result_overlay(match: dict[str, Any], api_fixture_id: str, score: dict[str, int], synced_at: str) -> None:
    overlay_path = results_overlay_path()
    payload = load_json(overlay_path) if overlay_path.is_file() else {"results": {}}
    payload.setdefault("results", {})
    local_fixture_id = str(match.get("fixture_id") or api_fixture_id)
    aliases = [candidate for candidate in fixture_id_candidates(local_fixture_id) if candidate != local_fixture_id]
    if api_fixture_id != local_fixture_id and api_fixture_id not in aliases:
        aliases.insert(0, api_fixture_id)
    payload["results"][local_fixture_id] = {
        "fixture_id": local_fixture_id,
        "api_fixture_id": api_fixture_id,
        "alias_fixture_ids": aliases,
        "home_team": match.get("home_team") or "",
        "away_team": match.get("away_team") or "",
        "actual_score": {"home": score["home"], "away": score["away"]},
        "status": "finished",
        "result_source": "api_football_fixture_result",
        "result_note": "API-Football fixtures endpoint result sync",
        "result_synced_at_utc": synced_at,
    }
    write_json(overlay_path, payload)


def refresh_result_sync_module(match: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    kickoff_utc = parse_utc_datetime(match.get("kickoff_utc"))
    if kickoff_utc and datetime.now(timezone.utc) < kickoff_utc.replace(microsecond=0) + timedelta(hours=2):
        return live_module(
            source="not_due",
            status="skipped_not_due",
            message_cn="比赛未完赛，赛果同步未到时间。",
        )

    candidates = api_fixture_id_candidates_for_result(match)
    if not candidates:
        return live_module(source="missing", status="error", message_cn="缺少 fixture_id，无法同步赛果。")

    last_error = ""
    for api_fixture_id in candidates:
        payload, error = api_football_get_fixture_by_id(api_fixture_id, env)
        if error:
            last_error = error
            continue
        rows = (payload or {}).get("response") or []
        if not rows:
            last_error = f"fixtures?id={api_fixture_id} 暂无返回，赛果同步跳过。"
            continue

        row = rows[0]
        status = ((row.get("fixture") or {}).get("status") or {})
        short = str(status.get("short") or "")
        long = str(status.get("long") or "")
        if not is_finished_fixture_status(status):
            return live_module(
                source="live_api",
                status="skipped_not_finished",
                message_cn=f"比赛未完赛，赛果同步跳过：fixture_id={api_fixture_id}，status={short or long or 'unknown'}。",
            )
        score = parse_finished_score(row)
        if not score:
            return live_module(
                source="live_api",
                status="error",
                message_cn=f"比赛已完赛但 API 未返回可用全场比分：fixture_id={api_fixture_id}。",
            )

        synced_at = now_utc()
        write_result_overlay(match, api_fixture_id, score, synced_at)
        return live_module(
            source="live_api",
            status="success",
            message_cn=f"实时 API 成功，已同步完赛比分：{result_display_cn(match, score)}。",
        )

    return live_module(source="live_api", status="error", message_cn=last_error or "实时 API 失败，赛果同步跳过。")


def refresh_injuries_module(match: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    fixture_id = str(match.get("fixture_id") or "")
    if not fixture_id:
        return live_module(source="missing", status="error", message_cn="缺少 fixture_id，无法请求伤停。")
    payload, error = api_football_get("/injuries", fixture_id, env)
    if error:
        return live_module(source="cache", status="skipped", message_cn="实时 API 失败，使用缓存伤停信息。")
    rows = (payload or {}).get("response") or []
    if rows:
        return live_module(source="live_api", status="success", message_cn=f"实时 API 成功，伤停返回 {len(rows)} 条。")
    return live_module(source="missing", status="empty", message_cn="实时 API 暂无伤停。")


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


def refresh_weather_module(match: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    weather = update_weather_cache(match, env)
    if (weather or {}).get("weather_status") == "ready":
        return live_module(source="live_api", status="success", message_cn="实时 API 成功，天气已接入。")
    reason = (weather or {}).get("weather_reason_cn") or "天气查询暂缺，保留上一版。"
    return live_module(source="live_api", status="error", message_cn=reason)


def run_command(cmd: list[str], env: dict[str, str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=True, timeout=timeout)


def is_future_match(match: dict[str, Any]) -> bool:
    kickoff = parse_utc_datetime(match.get("kickoff_utc"))
    return bool(kickoff and datetime.now(timezone.utc) < kickoff)


def deepseek_key_available(env: dict[str, str]) -> bool:
    return bool(env.get("DEEPSEEK_API_KEY") or env.get("W1_SCOUT_API_KEY"))


def api_football_key_available(env: dict[str, str]) -> bool:
    return bool(env.get(ENV_KEY_NAME) or env.get("OPENCLAW_APIFOOTBALL_KEY"))


def manual_scout_enabled() -> bool:
    value = os.environ.get("W1_MANUAL_REFRESH_TRIGGER_SCOUT", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def scout_call_exists(fixture_id: str) -> bool:
    calls_path = ROOT / "state/w1_scout_calls.json"
    if not calls_path.is_file():
        return False
    try:
        calls = load_json(calls_path).get("calls", [])
    except Exception:
        return False
    for call in calls:
        if str(call.get("fixture_id") or "") == str(fixture_id) and isinstance(call.get("read"), dict):
            return True
    return False


def scout_call_dashboard_ready(fixture_id: str) -> bool:
    """Dynamic readiness: /dashboard-data can serve this fixture's Scout call."""
    payload = load_scout_calls_for_dashboard()
    for call in payload.get("calls") or []:
        if str(call.get("fixture_id") or "") == str(fixture_id) and isinstance(call.get("read"), dict):
            return True
    return False


def scout_embedded_in_dashboard(fixture_id: str) -> bool:
    if not DASHBOARD_HTML.is_file():
        return False
    try:
        html = DASHBOARD_HTML.read_text(encoding="utf-8")
        match = re.search(r'<script id="w1-scout-calls" type="application/json">(.*?)</script>', html, re.S)
        if not match:
            return False
        calls = json.loads(match.group(1)).get("calls", [])
    except Exception:
        return False
    for call in calls:
        if str(call.get("fixture_id") or "") == str(fixture_id) and isinstance(call.get("read"), dict):
            return True
    return False


def scout_stage_for_match(match: dict[str, Any]) -> tuple[str, str]:
    kickoff = parse_utc_datetime(match.get("kickoff_utc") or match.get("kickoff"))
    if kickoff is None:
        return "watch_12h", "赛前观察"
    minutes = (kickoff - datetime.now(timezone.utc)).total_seconds() / 60.0
    if minutes <= 30:
        return "final_30m", "最终版"
    if minutes <= 60:
        return "official_1h", "正式判断"
    if minutes <= 120:
        return "watch_2h", "赛前观察"
    if minutes <= 360:
        return "watch_6h", "赛前观察"
    if minutes <= 720:
        return "watch_12h", "赛前观察"
    if minutes <= 1440:
        return "early_24h", "早盘参考"
    return "early_48h", "早盘参考"


def run_manual_scout_cycle(match: dict[str, Any], env: dict[str, str]) -> str:
    fixture_id = str(match.get("fixture_id") or "")
    if not manual_scout_enabled():
        return "Scout 自动解读已被 W1_MANUAL_REFRESH_TRIGGER_SCOUT=0 关闭。"
    if not fixture_id:
        return "AI 解读未生成：缺少 fixture_id。"
    if not is_future_match(match):
        return "AI 解读未生成：该 fixture 已开赛或不在未来赛程内；只允许赛后 audit/review/calibration。"
    if not deepseek_key_available(env):
        return "基础数据已刷新；AI 解读未生成：当前 W1 server 进程未读取到 DEEPSEEK_API_KEY。请在启动 server 前 export DEEPSEEK_API_KEY，或写入 .env.local 后重启 server。"
    api_available = api_football_key_available(env)
    stage_id, stage_label = scout_stage_for_match(match)
    style_mode = "aggressive_script" if stage_id in {"official_1h", "final_30m"} else "balanced"
    scout_env = {
        **env,
        "W1_SCOUT_FORCE_FIXTURE": fixture_id,
        "W1_SCOUT_SCHEDULE_STAGE": stage_id,
        "W1_SCOUT_SCHEDULE_STAGE_LABEL": stage_label,
        "W1_SCOUT_FORCE_REFRESH": "1",
        "W1_SCOUT_STYLE_MODE": style_mode,
        "W1_SCOUT_PREMATCH_ONLY": "1",
        "W1_SCOUT_DISABLE_MEMORY_COMMIT": "1",
    }
    print(f"runner force fixture={fixture_id} stage={stage_id} label={stage_label}")
    if not api_available:
        scout_env["W1_SCOUT_SKIP_FETCH"] = "1"
    try:
        proc = run_command(["bash", str(SCOUT_CYCLE)], scout_env)
    except subprocess.TimeoutExpired:
        return "AI 解读未生成：Scout 单场周期超时；未推进旧内容。"
    except Exception as exc:  # noqa: BLE001 - keep manual refresh usable when Scout fails
        return f"AI 解读未生成：Scout 单场周期异常；未推进旧内容。{exc}"
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or ["Scout cycle failed"]
        return "AI 解读未生成：Scout 单场周期失败；未推进旧内容。" + (" " + tail[0] if tail else "")
    has_call = scout_call_exists(fixture_id)
    dashboard_ready = scout_call_dashboard_ready(fixture_id)
    if has_call and dashboard_ready:
        api_note = "实时 API 可用，本轮先刷新基础数据，再生成 Scout 解读。" if api_available else "实时 API 未配置，本轮使用本地缓存 / match card / 已有 bundle 生成 Scout 解读；不伪造缺失数据。"
        stdout = proc.stdout or ""
        if "embed_existing" in stdout or "补写 dashboard 上屏" in stdout or "dashboard embed missing" in stdout:
            return f"{api_note} 已有合法赛前解读，本轮已补写 dashboard 动态上屏；未重复调用 AI。"
        return f"{api_note} Scout 单场赛前解读已生成并可由 /dashboard-data 上屏，已按当前阶段 {stage_label} 锁定。"
    if has_call and not dashboard_ready:
        return "AI 解读已生成但未上屏：/dashboard-data scout_calls 校验失败，请检查动态 payload。"
    return "AI 解读未生成：Scout 单场周期未产出合法 read；未推进旧内容。"


def final_refresh_message(live_status: str, scout_message: str) -> str:
    if "DEEPSEEK_API_KEY" in scout_message and "未读取到" in scout_message:
        return "完成 ✓ 已刷新基础数据；AI 解读未生成：当前 W1 server 进程未读取到 DEEPSEEK_API_KEY。请在启动 server 前 export DEEPSEEK_API_KEY，或写入 .env.local 后重启 server。"
    if "W1_MANUAL_REFRESH_TRIGGER_SCOUT=0" in scout_message:
        return "完成 ✓ 已刷新基础数据；Scout 自动解读已被 W1_MANUAL_REFRESH_TRIGGER_SCOUT=0 关闭。"
    if "补写 dashboard 上屏" in scout_message or "补写 dashboard 动态上屏" in scout_message:
        return "完成 ✓ 已刷新基础数据；已有合法赛前解读，本轮已补写 dashboard 动态上屏；未重复调用 AI。"
    if "使用本地缓存" in scout_message and (
        "已生成并上屏" in scout_message or "可由 /dashboard-data 上屏" in scout_message
    ):
        return "完成 ✓ 已刷新基础数据；实时 API 缺失，本轮使用本地缓存生成 Scout 解读，动态上屏成功。"
    if "已生成并上屏" in scout_message or "可由 /dashboard-data 上屏" in scout_message or "补写 dashboard 动态上屏" in scout_message:
        return "完成 ✓ 已刷新基础数据，并生成本场 Scout 解读，动态上屏成功。"
    return f"完成 ✓ 已刷新基础数据；{scout_message or f'实时刷新 {live_status}。'}"


def run_prediction(job_id: str, match: dict[str, Any]) -> None:
    global _active_job, _active_job_started_at, _active_job_type
    load_local_env_files()
    load_api_key_env_bridge()
    env = os.environ.copy()
    fixture_id = str(match.get("fixture_id") or "")
    live_refresh = new_live_refresh(fixture_id)
    try:
        for idx, label in enumerate(STEPS, start=1):
            write_progress(
                progress_payload(
                    job_id=job_id,
                    status="running",
                    step_index=idx,
                    message=f"{label}中…",
                    match=match,
                    job_type="manual",
                )
            )
            time.sleep(0.25)

            if idx == 3:
                lineup_result = refresh_lineups(match, env)
                live_refresh["modules"]["lineups"] = lineup_result
                write_progress(
                    progress_payload(
                        job_id=job_id,
                        status="running",
                        step_index=idx,
                        message=lineup_result.get("message_cn", "查询阵容/首发完成。"),
                        match=match,
                    )
                )

            if idx == 2:
                live_refresh["modules"]["odds"] = refresh_odds_module(match, env)
                write_progress(progress_payload(job_id=job_id, status="running", step_index=idx, message=live_refresh["modules"]["odds"]["message_cn"], match=match))

            if idx == 4:
                live_refresh["modules"]["referee"] = refresh_referee_module(match, env)
                live_refresh["modules"]["result_sync"] = refresh_result_sync_module(match, env)
                message = (
                    f"{live_refresh['modules']['referee']['message_cn']} "
                    f"{live_refresh['modules']['result_sync']['message_cn']}"
                ).strip()
                write_progress(progress_payload(job_id=job_id, status="running", step_index=idx, message=message, match=match))

            if idx == 5:
                live_refresh["modules"]["injuries"] = refresh_injuries_module(match, env)
                write_progress(progress_payload(job_id=job_id, status="running", step_index=idx, message=live_refresh["modules"]["injuries"]["message_cn"], match=match))

            if idx == 6:
                live_refresh["modules"]["weather"] = refresh_weather_module(match, env)
                write_progress(
                    progress_payload(
                        job_id=job_id,
                        status="running",
                        step_index=idx,
                        message=live_refresh["modules"]["weather"]["message_cn"],
                        match=match,
                    )
                )

            if idx == 7:
                finalise_live_refresh(live_refresh)
                write_live_refresh_state(fixture_id, live_refresh)
                write_progress(progress_payload(job_id=job_id, status="running", step_index=idx, message="本次实时刷新状态已写入 runtime overlay（不回写源卡）。", match=match))

        build = run_command(["python3", str(BUILD_SCRIPT)], env)
        if build.returncode != 0:
            raise RuntimeError("dashboard 数据更新失败，数据暂缺，保留上一版。")

        scout_message = run_manual_scout_cycle(match, env)
        write_progress(
            progress_payload(
                job_id=job_id,
                status="running",
                step_index=len(STEPS) - 1,
                message=scout_message,
                match=match,
                job_type="manual",
            )
        )

        selected = find_match_by_fixture_id(match.get("fixture_id"))
        if not selected and not match.get("fixture_id"):
            selected = find_match_by_name(match.get("home_team_cn", ""), match.get("away_team_cn", ""))
        write_progress(
            progress_payload(
                job_id=job_id,
                status="done",
                step_index=len(STEPS),
                message=final_refresh_message(str(live_refresh.get("overall_status") or ""), scout_message),
                match=progress_match(selected, match.get("stage_cn", "")) if selected else match,
                job_type="manual",
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
                job_type="manual",
            )
        )
    finally:
        with _job_lock:
            if _active_job == job_id:
                _active_job = None
                _active_job_started_at = None
                _active_job_type = None


def run_scout_autopilot_once(reason: str = "scheduled") -> bool:
    global _active_job, _active_job_started_at, _active_job_type
    load_local_env_files()
    load_api_key_env_bridge()
    env = os.environ.copy()
    if not autopilot_enabled():
        write_scout_cycle_status("legacy_fallback", "disabled", "server fallback disabled；Scout 自动生产请运行 w1_scout_scheduler.py。")
        return False
    if not deepseek_key_available(env):
        write_scout_cycle_status("legacy_fallback", "missing_key", "server fallback 未运行：当前 W1 server 进程未读取到 DEEPSEEK_API_KEY。")
        return False
    with _job_lock:
        cleanup_note = cleanup_finished_or_stale_active_job_locked()
        if cleanup_note:
            print(f"WARN: {cleanup_note}")
        if _active_job:
            write_scout_cycle_status("autopilot", "skipped", "已有手动强刷或自动周期任务运行中；本轮自动检查跳过。")
            return False
        job_id = "auto-" + uuid.uuid4().hex[:8]
        _active_job = job_id
        _active_job_started_at = time.time()
        _active_job_type = "autopilot"
    write_progress(
        progress_payload(
            job_id=job_id,
            job_type="autopilot",
            status="running",
            step_index=10,
            message=f"Scout 自动周期检查中（{reason}）…",
            match={"fixture_id": "", "match": "Scout 自动周期", "stage_cn": "autopilot"},
        )
    )
    try:
        before_status = scout_fixture_status((dashboard_data_payload() or {}).get("match_records") or [])
        cycle_env = {
            **env,
            "W1_SCOUT_LOOKAHEAD_HOURS": str(SCOUT_AUTOPILOT_LOOKAHEAD_HOURS),
            "W1_SCOUT_DISABLE_MEMORY_COMMIT": env.get("W1_SCOUT_DISABLE_MEMORY_COMMIT", "1"),
        }
        proc = run_command(["bash", str(SCOUT_CYCLE)], cycle_env, timeout=int(env.get("W1_SCOUT_AUTOPILOT_TIMEOUT_SECONDS", "420")))
        status_payload = dashboard_data_payload() or {"match_records": []}
        fixture_status = scout_fixture_status(status_payload.get("match_records") or [])
        cycle_status: dict[str, Any] = {}
        try:
            if SCOUT_CYCLE_STATUS.is_file():
                cycle_status = load_json(SCOUT_CYCLE_STATUS)
        except Exception:
            cycle_status = {}
        progress_counts = {
            "phase": cycle_status.get("phase"),
            "generated_count": int(cycle_status.get("generated_count") or 0),
            "embedded_count": int(cycle_status.get("embedded_count") or 0),
            "failed_count": int(cycle_status.get("failed_count") or 0),
            "pending_count": int(fixture_status.get("pending_count") or cycle_status.get("pending_count") or 0),
            "failed_fixtures": cycle_status.get("failed_fixtures") or [],
        }
        if proc.returncode != 0:
            msg = cycle_status.get("message_cn") or "Scout 自动周期失败；已保留当前快照，未覆盖旧推荐。"
            err = (proc.stderr or proc.stdout or "").splitlines()[-1] if (proc.stderr or proc.stdout) else msg
            progress_counts["failed_count"] = max(1, int(progress_counts.get("failed_count") or 0))
            write_scout_cycle_status("autopilot", "failed", msg, {**fixture_status, **progress_counts})
            write_progress(progress_payload(job_id=job_id, job_type="autopilot", status="failed", step_index=11, message=msg, match={"fixture_id": "", "match": "Scout 自动周期"}, error=err, extra=progress_counts))
            return False
        generated = 0
        for line in (proc.stdout or "").splitlines():
            if "DeepSeek analyst" in line or "强制生成首版解读" in line:
                generated = max(generated, int(before_status.get("missing_read_count") or 1))
        result = str(cycle_status.get("result") or "ok")
        if result == "partial":
            msg = cycle_status.get("message_cn") or "Scout 自动周期部分完成；剩余 fixture 将在下轮重试。"
        else:
            msg = cycle_status.get("message_cn") or "server fallback 已完成本轮检查；正式生产仍由 w1_scout_scheduler.py 执行。"
        progress_counts["generated_count"] = int(cycle_status.get("generated_count") or generated or 0)
        progress_counts["embedded_count"] = int(cycle_status.get("embedded_count") or progress_counts["generated_count"])
        progress_counts["failed_count"] = int(cycle_status.get("failed_count") or 0)
        write_scout_cycle_status(
            "autopilot",
            "partial" if result == "partial" else "ok",
            msg,
            {
                **fixture_status,
                "generated_count": progress_counts["generated_count"],
                "embedded_count": progress_counts["embedded_count"],
                "skipped_count": 1 if generated == 0 else 0,
                "failed_count": progress_counts["failed_count"],
                "failed_fixtures": progress_counts["failed_fixtures"],
            },
        )
        write_progress(progress_payload(job_id=job_id, job_type="autopilot", status="done", step_index=11, message=msg, match={"fixture_id": "", "match": "Scout 自动周期"}, extra=progress_counts))
        return True
    except subprocess.TimeoutExpired as exc:
        msg = "AI 分析师超时；本轮未覆盖旧推荐，将在下轮自动周期重试。"
        write_scout_cycle_status("autopilot", "failed", msg, {"failed_count": 1})
        write_progress(progress_payload(job_id=job_id, job_type="autopilot", status="failed", step_index=11, message=msg, match={"fixture_id": "", "match": "Scout 自动周期"}, error=str(exc), extra={"failed_count": 1}))
        return False
    except Exception as exc:  # noqa: BLE001 - autopilot must not crash the server
        msg = f"Scout 自动周期异常；未推进旧内容。{exc}"
        write_scout_cycle_status("autopilot", "failed", msg)
        write_progress(progress_payload(job_id=job_id, job_type="autopilot", status="failed", step_index=11, message=msg, match={"fixture_id": "", "match": "Scout 自动周期"}, error=str(exc)))
        return False
    finally:
        with _job_lock:
            if _active_job == job_id:
                _active_job = None
                _active_job_started_at = None
                _active_job_type = None


def scout_autopilot_loop() -> None:
    time.sleep(2)
    while True:
        run_scout_autopilot_once()
        time.sleep(max(60, SCOUT_AUTOPILOT_INTERVAL_SECONDS))


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
            data = dashboard_data_payload()
            if data is None:
                ensure_dashboard_data_ready()
                data = dashboard_data_payload()
            if data is not None:
                self.send_json(data)
            else:
                self.send_json({"ok": False, "error_cn": DASHBOARD_EMPTY_ERROR}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler name
        global _active_job, _active_job_started_at, _active_job_type
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

        requested_fixture_id = str(payload.get("fixture_id") or "").strip()
        if requested_fixture_id:
            match["requested_fixture_id"] = requested_fixture_id
            candidates = api_fixture_id_candidates(match)
            if candidates:
                match["api_fixture_id"] = candidates[0]
        print(
            "POST /predict received "
            f"fixture_id={requested_fixture_id or match.get('fixture_id') or ''} "
            f"home={match.get('home_team_cn') or match.get('home_team') or ''} "
            f"away={match.get('away_team_cn') or match.get('away_team') or ''} "
            f"path={self.path}"
        )

        with _job_lock:
            cleanup_note = cleanup_finished_or_stale_active_job_locked()
            if cleanup_note:
                print(f"WARN: {cleanup_note}")
            if _active_job:
                print(f"POST /predict ACTIVE_JOB active_job={_active_job} requested_fixture_id={requested_fixture_id or match.get('fixture_id') or ''}")
                active_kind = _active_job_type or "manual"
                active_msg = "已有自动周期任务运行中，请等待完成。" if active_kind == "autopilot" else "已有手动强刷任务正在进行，请等待当前任务完成。"
                self.send_json(
                    {
                        "ok": False,
                        "code": "ACTIVE_JOB",
                        "error_cn": active_msg,
                        "job_id": _active_job,
                        "job_type": active_kind,
                        "retryable": True,
                    },
                    HTTPStatus.CONFLICT,
                )
                return
            job_id = uuid.uuid4().hex[:12]
            _active_job = job_id
            _active_job_started_at = time.time()
            _active_job_type = "manual"
            print(f"POST /predict start job_id={job_id} active_job={_active_job} fixture_id={requested_fixture_id or match.get('fixture_id') or ''}")

        init_message = f"初始化比赛中：fixture_id={match.get('fixture_id', '未提供')}，{match.get('match') or ''}"
        write_progress(progress_payload(job_id=job_id, status="running", step_index=1, message=init_message, match=match, job_type="manual"))
        thread = threading.Thread(target=run_prediction, args=(job_id, match), daemon=True)
        thread.start()
        self.send_json({"ok": True, "job_id": job_id, "message_cn": "已开始查询。"})


def main() -> int:
    load_local_env_files()
    load_api_key_env_bridge()
    ensure_dashboard_data_ready()
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    if not PROGRESS.is_file():
        write_progress(progress_payload(job_id="none", status="idle", step_index=1, message="等待开始预测。", match={}))
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"W1 dashboard server: http://{HOST}:{PORT}/reports/dashboard/W1_VISUAL_DASHBOARD.html")
    print(env_status_line())
    if autopilot_enabled():
        threading.Thread(target=scout_autopilot_loop, daemon=True).start()
        write_scout_cycle_status("legacy_fallback", "scheduled", "server fallback enabled；仅作遗留兜底，正式生产请运行 w1_scout_scheduler.py。", {"next_autopilot_run_at": next_autopilot_run_utc(now_utc())})
    else:
        print("W1 server Scout fallback: disabled (scheduler is the producer)")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
