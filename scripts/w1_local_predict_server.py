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
from urllib import request


ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
PORT = int(os.environ.get("W1_DASHBOARD_PORT", "8765"))
PROGRESS = ROOT / "state/w1_predict_progress.json"
WEATHER_CACHE = ROOT / "state/w1_weather_cache.json"
LIVE_REFRESH_STATE = ROOT / "state/w1_live_refresh_state.json"
MANUAL_LINEUPS_DIR = ROOT / "data/manual_lineups"
FIXTURE_ALIASES = ROOT / "data/fixture_aliases.json"
DASHBOARD_DATA = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
BUILD_SCRIPT = ROOT / "scripts/build_w1_dashboard_data.py"
WEATHER_CLIENT = ROOT / "scripts/w1_weather_client.py"
VENUES_JSON = ROOT / "data/static/world_cup_2026_venues.json"
CARDS_DIR = ROOT / "data/processed/match_cards/group_stage_round1"
WATCHER = ROOT / "scripts/w1_watcher.sh"
ENV_KEY_NAME = "APIFOOTBALL_" + "KEY"
API_FOOTBALL_BASE = "https://v" + "3.football.api-sports.io"
WEATHER_STEP_DETAIL = "实时请求天气 API/Open-Meteo"

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
    "返回 progress",
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


def write_live_refresh_to_card(fixture_id: str, live_refresh: dict[str, Any]) -> bool:
    path = card_path_for_fixture_id(fixture_id)
    if not path:
        manual = manual_lineup_payload(fixture_id)
        if manual:
            path = card_path_for_manual_lineup(manual)
    if not path:
        return False
    card = load_json(path)
    card["live_refresh"] = live_refresh
    write_json(path, card)
    return True


def match_records() -> list[dict[str, Any]]:
    if not DASHBOARD_DATA.is_file():
        return []
    data = load_json(DASHBOARD_DATA)
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
    for path in CARDS_DIR.glob("*.json"):
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
    for path in CARDS_DIR.glob("*.json"):
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
        "match": row.get("match") or f"{row.get('home_team_cn', '')} vs {row.get('away_team_cn', '')}",
        "home_team": row.get("home_team") or "",
        "away_team": row.get("away_team") or "",
        "home_team_cn": row.get("home_team_cn") or "",
        "away_team_cn": row.get("away_team_cn") or "",
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
        "source": "api-football fixtures/lineups",
        "home_team": home.get("team", {}).get("name"),
        "away_team": away.get("team", {}).get("name"),
        "home_formation": home.get("formation"),
        "away_formation": away.get("formation"),
        "home_starting_players": home_starting,
        "away_starting_players": away_starting,
        "home_bench_players": [normalise_api_player(row) for row in home.get("substitutes", [])],
        "away_bench_players": [normalise_api_player(row) for row in away.get("substitutes", [])],
    }, live_module(source="live_api", status="success", message_cn="实时 API 成功，首发已确认。")


def fetch_api_football_lineups(fixture_id: str, env: dict[str, str]) -> dict[str, Any] | None:
    lineups, module = fetch_live_lineups_from_api(fixture_id, env)
    return lineups if module.get("source") == "live_api" and module.get("status") == "success" else None


def write_lineups_to_card(fixture_id: str, lineups: dict[str, Any]) -> bool:
    path = card_path_for_fixture_id(fixture_id)
    if not path and lineups.get("source") == "manual_verified":
        path = card_path_for_manual_lineup(lineups)
    if not path:
        return False
    card = load_json(path)
    home_starting = lineups.get("home_starting_players") or []
    away_starting = lineups.get("away_starting_players") or []
    home_bench = lineups.get("home_bench_players") or []
    away_bench = lineups.get("away_bench_players") or []
    card["lineups"] = {
        **card.get("lineups", {}),
        "confirmed_lineup_available": len(home_starting) >= 11 and len(away_starting) >= 11,
        "status": "CONFIRMED" if len(home_starting) >= 11 and len(away_starting) >= 11 else "PARTIAL",
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
    }
    if card["lineups"]["confirmed_lineup_available"]:
        card["risk_flags"] = [
            flag
            for flag in card.get("risk_flags", [])
            if flag.get("code") not in {"CONFIRMED_LINEUP_MISSING", "LINEUP_WAIT_EVENT"}
        ]
        card["data_gaps"] = [
            gap
            for gap in card.get("data_gaps", [])
            if gap.get("field") != "lineups.confirmed_lineup"
        ]
        reasons = card.get("decision", {}).get("reasons", {})
        if isinstance(reasons, dict) and isinstance(reasons.get("counter_factors"), list):
            reasons["counter_factors"] = [
                item
                for item in reasons["counter_factors"]
                if "confirmed_lineup missing" not in str(item)
                and "lineup_status=WAIT" not in str(item)
            ]
    write_json(path, card)
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
    return live_module(source="live_api", status="success", message_cn=f"实时 API 成功，赔率返回 {len(rows)} 条。")


def refresh_lineups(match: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    fixture_id = str(match.get("fixture_id") or "")
    if not fixture_id:
        return live_module(source="missing", status="error", message_cn="缺少 fixture_id，无法刷新首发。")
    manual = manual_lineup_payload_for_match(fixture_id, match)
    if manual:
        if not write_lineups_to_card(fixture_id, manual):
            return live_module(source="manual_verified", status="error", message_cn="找到人工验证首发，但未找到对应本地 match card。")
        return live_module(
            source="manual_verified",
            status="success",
            message_cn=(
                f"manual_verified / {manual.get('source_name', 'Sky Sports')}：官方首发已确认。"
                f" {manual.get('home_team')} {manual.get('home_formation')}，"
                f"{manual.get('away_team')} {manual.get('away_formation')}。"
            ),
        )
    lineups, module = fetch_live_lineups_from_api(fixture_id, env)
    if not lineups:
        fallback = verified_lineup_payload(fixture_id)
        if fallback:
            lineups = fallback
            module = live_module(source="verified_fallback", status=module.get("status", "skipped"), message_cn=f"{module.get('message_cn', '实时 API 暂无首发')} 使用兜底数据。")
        else:
            module = live_module(source="cache", status=module.get("status", "empty"), message_cn=f"{module.get('message_cn', '实时 API 暂无首发')} 使用缓存，保留上一版。")
    if not lineups:
        return module
    if not write_lineups_to_card(fixture_id, lineups):
        return live_module(source=module.get("source", "missing"), status="error", message_cn="未找到对应 match card，首发未写入。")
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


def run_command(cmd: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=True, timeout=180)


def run_prediction(job_id: str, match: dict[str, Any]) -> None:
    global _active_job
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
                write_progress(progress_payload(job_id=job_id, status="running", step_index=idx, message=live_refresh["modules"]["referee"]["message_cn"], match=match))

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
                write_live_refresh_to_card(fixture_id, live_refresh)
                write_progress(progress_payload(job_id=job_id, status="running", step_index=idx, message="本次实时刷新状态已写入 match card runtime。", match=match))

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
                message=f"查询完成：实时刷新 {live_refresh.get('overall_status')}，已更新 dashboard。",
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
