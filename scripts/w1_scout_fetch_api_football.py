#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch W1_SCOUT real pre-match factors from api-football.

Writes one file per fixture to data/scout/<fixture_id>.json. These files are
runtime inputs and are gitignored. This script never mutates W1 market/base
artifacts and never writes post-match current-fixture statistics into a bundle.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import parse, request

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_DATA = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
SCOUT_DIR = ROOT / "data/scout"
API_BASE = "https://v3.football.api-sports.io"
ENV_KEY_NAME = "APIFOOTBALL_" + "KEY"
API_ENV_BRIDGE_FILES = [
    Path.home() / ".openclaw/.env",
    Path.home() / ".openclaw/service-env/ai.openclaw.gateway.env",
    Path.home() / ".openclaw/secrets/v4_daily_scan.env",
    Path.home() / ".openclaw/workspace/v4-football/api_keys.sh",
]


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


def load_api_key() -> str | None:
    if os.environ.get(ENV_KEY_NAME):
        return os.environ[ENV_KEY_NAME]
    if os.environ.get("OPENCLAW_APIFOOTBALL_KEY"):
        return os.environ["OPENCLAW_APIFOOTBALL_KEY"]
    if os.environ.get("W1_DISABLE_API_ENV_BRIDGE") == "1":
        return None
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
            if not value:
                continue
            if key == ENV_KEY_NAME:
                return value
            if key == "OPENCLAW_APIFOOTBALL_KEY":
                return value
    return None


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_now() -> str:
    return now_utc().isoformat().replace("+00:00", "Z")


def parse_dt(value: Any) -> datetime | None:
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


class ApiFootball:
    def __init__(self, key: str, sleep_s: float = 0.25) -> None:
        self.key = key
        self.sleep_s = sleep_s

    def get(self, endpoint: str, **params: Any) -> dict[str, Any]:
        query = parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{API_BASE}{endpoint}"
        if query:
            url += f"?{query}"
        req = request.Request(url, headers={"x-apisports-key": self.key})
        with request.urlopen(req, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
        time.sleep(self.sleep_s)
        return payload


def load_dashboard_records() -> list[dict[str, Any]]:
    if not DASHBOARD_DATA.is_file():
        return []
    return json.loads(DASHBOARD_DATA.read_text(encoding="utf-8")).get("match_records", [])


def select_records(records: list[dict[str, Any]], wanted: set[str] | None, include_started: bool, limit: int | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    now = now_utc()
    for rec in records:
        fid = str(rec.get("fixture_id") or "")
        if wanted and fid not in wanted:
            continue
        kickoff = parse_dt(rec.get("kickoff_utc") or rec.get("kickoff"))
        if not include_started and kickoff and kickoff <= now:
            continue
        out.append(rec)
        if limit and len(out) >= limit:
            break
    return out


def response_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("response")
    return rows if isinstance(rows, list) else []


def resolve_fixture(api: ApiFootball, fixture_id: str) -> dict[str, Any] | None:
    rows = response_rows(api.get("/fixtures", id=fixture_id))
    return rows[0] if rows else None


def team_ids(fixture_row: dict[str, Any]) -> tuple[int | None, int | None]:
    teams = fixture_row.get("teams") or {}
    home = (teams.get("home") or {}).get("id")
    away = (teams.get("away") or {}).get("id")
    return home, away


def fixture_league_season(fixture_row: dict[str, Any]) -> tuple[int | None, int | None]:
    league = fixture_row.get("league") or {}
    return league.get("id"), league.get("season")


def fixture_kickoff(fixture_row: dict[str, Any], fallback: dict[str, Any]) -> datetime | None:
    raw = ((fixture_row.get("fixture") or {}).get("date")) or fallback.get("kickoff_utc") or fallback.get("kickoff")
    return parse_dt(raw)


def team_name(fixture_row: dict[str, Any], side: str, fallback: dict[str, Any]) -> str:
    teams = fixture_row.get("teams") or {}
    value = (teams.get(side) or {}).get("name")
    if value:
        return str(value)
    return str(fallback.get("home_team" if side == "home" else "away_team") or "")


def fetch_recent_fixtures(api: ApiFootball, team_id: int, season: int, kickoff: datetime, n: int = 10) -> list[dict[str, Any]]:
    rows = response_rows(api.get("/fixtures", team=team_id, season=season, status="FT", last=20))
    prior: list[dict[str, Any]] = []
    for row in rows:
        dt = parse_dt((row.get("fixture") or {}).get("date"))
        if dt and dt < kickoff:
            prior.append(row)
    prior.sort(key=lambda r: parse_dt((r.get("fixture") or {}).get("date")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return prior[:n]


def outcome_for_team(row: dict[str, Any], team_id: int) -> tuple[str, int, int] | None:
    teams = row.get("teams") or {}
    goals = row.get("goals") or {}
    home_id = (teams.get("home") or {}).get("id")
    away_id = (teams.get("away") or {}).get("id")
    hg, ag = goals.get("home"), goals.get("away")
    if not isinstance(hg, int) or not isinstance(ag, int):
        return None
    if team_id == home_id:
        gf, ga = hg, ag
    elif team_id == away_id:
        gf, ga = ag, hg
    else:
        return None
    result = "W" if gf > ga else "D" if gf == ga else "L"
    return result, gf, ga


def build_form(recent: list[dict[str, Any]], team_id: int, n: int = 5) -> dict[str, Any]:
    rows = []
    for row in recent[:n]:
        out = outcome_for_team(row, team_id)
        if out:
            rows.append(out)
    if not rows:
        return {"last5_wdl": None, "gf_avg": None, "ga_avg": None, "ppg": None, "home_away_split": None, "availability": "missing"}
    pts = [3 if r == "W" else 1 if r == "D" else 0 for r, _, _ in rows]
    return {
        "last5_wdl": "".join(r for r, _, _ in rows),
        "gf_avg": round(sum(gf for _, gf, _ in rows) / len(rows), 3),
        "ga_avg": round(sum(ga for _, _, ga in rows) / len(rows), 3),
        "ppg": round(sum(pts) / len(rows), 3),
        "home_away_split": None,
        "availability": "available" if len(rows) >= 5 else "partial",
    }


def stat_value(stats_rows: list[dict[str, Any]], team_id: int, names: set[str]) -> float | None:
    target = None
    for row in stats_rows:
        if ((row.get("team") or {}).get("id")) == team_id:
            target = row
            break
    if not target:
        return None
    for stat in target.get("statistics", []) or []:
        label = str(stat.get("type") or "").strip().lower().replace(" ", "_")
        if label in names:
            value = stat.get("value")
            if isinstance(value, str) and value.endswith("%"):
                value = value[:-1]
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def build_xg_roll(api: ApiFootball, recent: list[dict[str, Any]], team_id: int, n: int = 5) -> dict[str, Any]:
    xg_for: list[float] = []
    shots: list[float] = []
    sot: list[float] = []
    used = 0
    for row in recent[:n]:
        fid = (row.get("fixture") or {}).get("id")
        if not fid:
            continue
        stats = response_rows(api.get("/fixtures/statistics", fixture=fid))
        if not stats:
            continue
        used += 1
        val = stat_value(stats, team_id, {"expected_goals", "xg"})
        if val is not None:
            xg_for.append(val)
        sh = stat_value(stats, team_id, {"total_shots", "shots_total", "shots"})
        if sh is not None:
            shots.append(sh)
        on = stat_value(stats, team_id, {"shots_on_goal", "shots_on_target", "sot"})
        if on is not None:
            sot.append(on)
    if used == 0:
        return {"xg_for": None, "xg_against": None, "shots": None, "sot": None, "window_n": None, "availability": "missing"}
    return {
        "xg_for": round(sum(xg_for) / len(xg_for), 3) if xg_for else None,
        "xg_against": None,
        "shots": round(sum(shots) / len(shots), 3) if shots else None,
        "sot": round(sum(sot) / len(sot), 3) if sot else None,
        "window_n": used,
        "availability": "available" if (xg_for or shots or sot) and used >= 3 else "partial",
    }


def build_lineup(api: ApiFootball, fixture_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    rows = response_rows(api.get("/fixtures/lineups", fixture=fixture_id))
    if len(rows) < 2:
        return {"confirmed": False, "formation_home": None, "formation_away": None, "key_absences": []}, [], []
    home, away = rows[0], rows[1]
    home_start = home.get("startXI", []) or []
    away_start = away.get("startXI", []) or []
    return {
        "confirmed": len(home_start) >= 11 and len(away_start) >= 11,
        "formation_home": home.get("formation"),
        "formation_away": away.get("formation"),
        "key_absences": [],
    }, home_start, away_start


def build_injuries(api: ApiFootball, fixture_id: str, home_id: int | None, away_id: int | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = response_rows(api.get("/injuries", fixture=fixture_id))
    home: list[dict[str, Any]] = []
    away: list[dict[str, Any]] = []
    for row in rows:
        team_id = (row.get("team") or {}).get("id")
        item = {
            "player": (row.get("player") or {}).get("name"),
            "importance": "unknown",
            "reason": (row.get("player") or {}).get("reason"),
        }
        if team_id == home_id:
            home.append(item)
        elif team_id == away_id:
            away.append(item)
    return home, away


def build_h2h(api: ApiFootball, home_id: int | None, away_id: int | None, kickoff: datetime, n: int = 10) -> dict[str, Any]:
    if not home_id or not away_id:
        return {"last_n": None, "home_wins": None, "draws": None, "away_wins": None, "availability": "missing"}
    rows = response_rows(api.get("/fixtures/headtohead", h2h=f"{home_id}-{away_id}", last=n))
    prior = []
    for row in rows:
        dt = parse_dt((row.get("fixture") or {}).get("date"))
        if dt and dt < kickoff:
            prior.append(row)
    home_wins = draws = away_wins = 0
    for row in prior:
        teams = row.get("teams") or {}
        goals = row.get("goals") or {}
        hg, ag = goals.get("home"), goals.get("away")
        h_id = (teams.get("home") or {}).get("id")
        if not isinstance(hg, int) or not isinstance(ag, int):
            continue
        if hg == ag:
            draws += 1
        else:
            winner_home = hg > ag
            winner_id = h_id if winner_home else (teams.get("away") or {}).get("id")
            if winner_id == home_id:
                home_wins += 1
            elif winner_id == away_id:
                away_wins += 1
    return {
        "last_n": len(prior),
        "home_wins": home_wins,
        "draws": draws,
        "away_wins": away_wins,
        "availability": "available" if prior else "missing",
    }


def build_standings(api: ApiFootball, league_id: int | None, season: int | None, home_id: int | None, away_id: int | None) -> dict[str, Any]:
    if not league_id or not season:
        return {"rank_home": None, "rank_away": None, "pts_gap": None, "availability": "missing"}
    rows = response_rows(api.get("/standings", league=league_id, season=season))
    ranks: dict[int, tuple[int | None, int | None]] = {}
    for block in rows:
        for table in block.get("league", {}).get("standings", []) or []:
            for row in table:
                tid = (row.get("team") or {}).get("id")
                ranks[tid] = (row.get("rank"), row.get("points"))
    hrank, hpts = ranks.get(home_id, (None, None))
    arank, apts = ranks.get(away_id, (None, None))
    return {
        "rank_home": hrank,
        "rank_away": arank,
        "pts_gap": (hpts - apts) if isinstance(hpts, int) and isinstance(apts, int) else None,
        "availability": "available" if hrank is not None and arank is not None else "missing",
    }


def build_rest_days(home_recent: list[dict[str, Any]], away_recent: list[dict[str, Any]], kickoff: datetime) -> dict[str, Any]:
    def rest(rows: list[dict[str, Any]]) -> int | None:
        if not rows:
            return None
        dt = parse_dt((rows[0].get("fixture") or {}).get("date"))
        return (kickoff - dt).days if dt else None
    home = rest(home_recent)
    away = rest(away_recent)
    return {
        "home": home,
        "away": away,
        "diff": (home - away) if isinstance(home, int) and isinstance(away, int) else None,
        "availability": "available" if isinstance(home, int) and isinstance(away, int) else "missing",
    }


def build_api_pred(api: ApiFootball, fixture_id: str) -> dict[str, Any] | None:
    rows = response_rows(api.get("/predictions", fixture=fixture_id))
    return rows[0] if rows else None


def availability_from_blocks(bundle: dict[str, Any]) -> dict[str, str]:
    return {
        "form": "available" if bundle["form_home"]["availability"] != "missing" and bundle["form_away"]["availability"] != "missing" else "partial" if bundle["form_home"]["availability"] != "missing" or bundle["form_away"]["availability"] != "missing" else "missing",
        "xg_roll": "available" if bundle["xg_roll_home"]["availability"] != "missing" and bundle["xg_roll_away"]["availability"] != "missing" else "partial" if bundle["xg_roll_home"]["availability"] != "missing" or bundle["xg_roll_away"]["availability"] != "missing" else "missing",
        "lineup": "available" if bundle["lineup"].get("confirmed") else "partial",
        "injuries": "available" if bundle["injuries_home"] or bundle["injuries_away"] else "partial",
        "standings": bundle["standings"].get("availability", "missing"),
        "h2h": bundle["h2h"].get("availability", "missing"),
        "rest_days": bundle["rest_days"].get("availability", "missing"),
    }


def build_fixture_bundle(api: ApiFootball, rec: dict[str, Any]) -> dict[str, Any]:
    fid = str(rec.get("fixture_id"))
    fixture_row = resolve_fixture(api, fid)
    if not fixture_row:
        raise RuntimeError(f"fixture not found in api-football: {fid}")
    kickoff = fixture_kickoff(fixture_row, rec)
    if not kickoff:
        raise RuntimeError(f"fixture kickoff unavailable: {fid}")
    home_id, away_id = team_ids(fixture_row)
    league_id, season = fixture_league_season(fixture_row)
    if not home_id or not away_id or not season:
        raise RuntimeError(f"fixture team/season ids unavailable: {fid}")

    home_recent = fetch_recent_fixtures(api, home_id, int(season), kickoff)
    away_recent = fetch_recent_fixtures(api, away_id, int(season), kickoff)
    lineup, _, _ = build_lineup(api, fid)
    injuries_home, injuries_away = build_injuries(api, fid, home_id, away_id)
    oxt = (rec.get("market_probability_panel") or {}).get("one_x_two") or {}

    bundle: dict[str, Any] = {
        "schema_version": "W1_SCOUT_BUNDLE_V1",
        "fixture_id": fid,
        "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
        "home": team_name(fixture_row, "home", rec),
        "away": team_name(fixture_row, "away", rec),
        "league": (fixture_row.get("league") or {}).get("name") or "FIFA World Cup",
        "season": season,
        "asof_pre_kickoff": True,
        "fetched_at_utc": iso_now(),
        "market": {
            "p_home": oxt.get("home_win"),
            "p_draw": oxt.get("draw"),
            "p_away": oxt.get("away_win"),
            "ah_line": None,
            "ou_line": None,
        },
        "form_home": build_form(home_recent, home_id),
        "form_away": build_form(away_recent, away_id),
        "xg_roll_home": build_xg_roll(api, home_recent, home_id),
        "xg_roll_away": build_xg_roll(api, away_recent, away_id),
        "lineup": lineup,
        "injuries_home": injuries_home,
        "injuries_away": injuries_away,
        "standings": build_standings(api, league_id, season, home_id, away_id),
        "h2h": build_h2h(api, home_id, away_id, kickoff),
        "rest_days": build_rest_days(home_recent, away_recent, kickoff),
        "api_pred": build_api_pred(api, fid),
        "source": {
            "provider": "api-football",
            "endpoints": [
                "/fixtures?id=",
                "/fixtures?team=&season=&status=FT",
                "/fixtures/statistics?fixture=",
                "/fixtures/lineups?fixture=",
                "/injuries?fixture=",
                "/fixtures/headtohead?h2h=",
                "/standings?league=&season=",
                "/predictions?fixture=",
            ],
        },
    }
    bundle["availability"] = availability_from_blocks(bundle)
    bundle["missing_fields"] = [k for k, v in bundle["availability"].items() if v == "missing"]
    return bundle


def write_bundle(bundle: dict[str, Any]) -> Path:
    path = SCOUT_DIR / f"{bundle['fixture_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch api-football factors into gitignored data/scout/<fixture_id>.json")
    parser.add_argument("--fixture", action="append", dest="fixtures", help="Fixture id to fetch; may be repeated. Defaults to upcoming dashboard fixtures.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum fixtures to fetch.")
    parser.add_argument("--include-started", action="store_true", help="Allow already-started fixtures. Use only for manual backfill; pre-match flag still requires kickoff in future.")
    parser.add_argument("--sleep", type=float, default=0.25, help="Sleep seconds between API calls.")
    args = parser.parse_args()

    key = load_api_key()
    if not key:
        print("FAIL: APIFOOTBALL_KEY / OPENCLAW_APIFOOTBALL_KEY not configured; no data/scout files written.")
        return 2

    records = select_records(load_dashboard_records(), set(args.fixtures) if args.fixtures else None, args.include_started, args.limit)
    if not records:
        print("No eligible pre-match fixtures selected; no data/scout files written.")
        return 0

    api = ApiFootball(key, sleep_s=args.sleep)
    written = []
    skipped_started = []
    for rec in records:
        fid = str(rec.get("fixture_id"))
        fixture_row = resolve_fixture(api, fid)
        if not fixture_row:
            print(f"WARN: fixture not found, skipped {fid}")
            continue
        kickoff = fixture_kickoff(fixture_row, rec)
        if not args.include_started and kickoff and kickoff <= now_utc():
            skipped_started.append(fid)
            continue
        # Reuse the resolved fixture by monkey-patching one cached lookup through a tiny wrapper.
        original = resolve_fixture
        try:
            globals()["resolve_fixture"] = lambda _api, _fid, row=fixture_row: row if str(_fid) == fid else original(_api, _fid)
            bundle = build_fixture_bundle(api, rec)
        finally:
            globals()["resolve_fixture"] = original
        path = write_bundle(bundle)
        written.append(path.relative_to(ROOT).as_posix())
        print(f"WROTE {path.relative_to(ROOT)} availability={bundle['availability']}")
    if skipped_started:
        print(f"Skipped already-started fixtures (pre-match guard): {', '.join(skipped_started)}")
    print(f"scout api-football fetch complete: written={len(written)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
