#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 FiveDim Lite Stage A builder.

Builds read-only FiveDim Lite cards from existing local artifacts. Phase A is an
availability skeleton: market_view wraps the existing candidate builder, while
the other four dimensions honestly expose local facts or missing/degraded state.
No external fetch, no model change, no production wiring.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CARDS_DIR = ROOT / "data/processed/match_cards/group_stage_round1"
DASHBOARD_DATA = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
POLICY_PATH = ROOT / "config/w1_fivedim_lite_policy.json"
OUTPUT_PATH_DEFAULT = ROOT / "state/w1_fivedim_lite_cards.json"

sys.path.insert(0, str(ROOT / "scripts"))
import w1_candidate_builder as CAND  # noqa: E402


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def get_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def fixture_id_from_card(card: dict[str, Any]) -> str:
    match_id = str(card.get("match", {}).get("match_id", ""))
    if ":" in match_id:
        return match_id.rsplit(":", 1)[-1]
    return str(card.get("fixture_id") or match_id)


def availability(value: Any, degraded_when_missing: bool = False) -> str:
    if value is None:
        return "degraded" if degraded_when_missing else "missing"
    if value == {} or value == [] or value == "":
        return "degraded" if degraded_when_missing else "missing"
    return "available"


def leaf(value: Any, source: str, basis: str, availability_value: str | None = None) -> dict[str, Any]:
    return {
        "value": value,
        "source": source,
        "basis": basis,
        "availability": availability_value or availability(value),
        "independent_edge": False,
    }


def count_list(value: Any) -> int | None:
    return len(value) if isinstance(value, list) else None


def dashboard_by_fixture() -> dict[str, dict[str, Any]]:
    if not DASHBOARD_DATA.is_file():
        return {}
    data = read_json(DASHBOARD_DATA)
    return {str(row.get("fixture_id")): row for row in data.get("match_records", [])}


def build_market_view(card: dict[str, Any], dash: dict[str, Any]) -> dict[str, Any]:
    matrix = CAND.matrix_from_dashboard_record(dash)
    candidates = CAND.build_candidates(
        matrix=matrix,
        card=card,
        score_distribution=dash.get("score_distribution", {}),
    )
    return {
        "availability": "available" if candidates.get("status") == "ready" else "missing",
        "basis": "market_implied",
        "source": "scripts/w1_candidate_builder.py",
        "independent_edge": False,
        "calibrated": False,
        "candidate_payload": candidates,
    }


def build_strength_view(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "home_team_name": leaf(get_path(card, "teams.home.name"), "match_card:teams.home.name", "manual_context"),
        "away_team_name": leaf(get_path(card, "teams.away.name"), "match_card:teams.away.name", "manual_context"),
        "home_fifa_rank": leaf(get_path(card, "teams.home.fifa_rank"), "match_card:teams.home.fifa_rank", "missing"),
        "away_fifa_rank": leaf(get_path(card, "teams.away.fifa_rank"), "match_card:teams.away.fifa_rank", "missing"),
        "home_elo_rating": leaf(get_path(card, "teams.home.elo_rating"), "match_card:teams.home.elo_rating", "missing"),
        "away_elo_rating": leaf(get_path(card, "teams.away.elo_rating"), "match_card:teams.away.elo_rating", "missing"),
        "recent_form": leaf(None, "not_available_locally", "missing"),
    }


def build_tactical_view(card: dict[str, Any]) -> dict[str, Any]:
    lineup_status = get_path(card, "lineups.status")
    degraded = str(lineup_status or "").upper() in {"MISSING", "WAIT", ""}
    return {
        "lineup_status": leaf(lineup_status, "match_card:lineups.status", "manual_context", "degraded" if degraded else availability(lineup_status)),
        "confirmed_lineup_available": leaf(
            bool(get_path(card, "lineups.confirmed_lineup_available")),
            "match_card:lineups.confirmed_lineup_available",
            "manual_context",
            "available",
        ),
        "home_formation": leaf(get_path(card, "lineups.formation_home"), "match_card:lineups.formation_home", "missing"),
        "away_formation": leaf(get_path(card, "lineups.formation_away"), "match_card:lineups.formation_away", "missing"),
        "historical_tactical_stats": leaf(None, "post_match_only_or_not_available_locally", "missing"),
    }


def build_chemistry_view(card: dict[str, Any]) -> dict[str, Any]:
    home_xi_count = count_list(get_path(card, "lineups.home_starting_xi"))
    away_xi_count = count_list(get_path(card, "lineups.away_starting_xi"))
    return {
        "home_squad_players_count": leaf(get_path(card, "squad.home.players_count"), "match_card:squad.home.players_count", "manual_context"),
        "away_squad_players_count": leaf(get_path(card, "squad.away.players_count"), "match_card:squad.away.players_count", "manual_context"),
        "home_starting_xi_count": leaf(
            home_xi_count,
            "match_card:lineups.home_starting_xi",
            "degraded",
            "available" if home_xi_count and home_xi_count >= 11 else "degraded",
        ),
        "away_starting_xi_count": leaf(
            away_xi_count,
            "match_card:lineups.away_starting_xi",
            "degraded",
            "available" if away_xi_count and away_xi_count >= 11 else "degraded",
        ),
        "player_club_league_context": leaf(None, "not_available_locally", "missing"),
    }


def build_environment_view(card: dict[str, Any], dash: dict[str, Any]) -> dict[str, Any]:
    env = dash.get("environment_context", {}) if isinstance(dash, dict) else {}
    weather_status = env.get("weather_status")
    weather_availability = "missing" if str(weather_status or "").lower() in {"missing", "暂缺", ""} else "available"
    return {
        "venue_name": leaf(get_path(card, "match.venue.name") or env.get("venue_name"), "match_card/dashboard:venue", "manual_context"),
        "venue_city": leaf(get_path(card, "match.venue.city") or env.get("city"), "match_card/dashboard:venue", "manual_context"),
        "venue_country": leaf(get_path(card, "match.venue.country") or env.get("country"), "match_card/dashboard:venue", "manual_context"),
        "altitude_m": leaf(env.get("altitude_m"), "dashboard.environment_context.altitude_m", "local_static"),
        "roof_status": leaf(env.get("roof_status"), "dashboard.environment_context.roof_status", "local_static"),
        "weather_status": leaf(weather_status, "dashboard.environment_context.weather_status", "degraded", weather_availability),
        "weather_context": leaf(
            {
                "temperature_c": env.get("temperature_c"),
                "humidity_pct": env.get("humidity_pct"),
                "wind_speed_kmh": env.get("wind_speed_kmh"),
                "precipitation_probability_pct": env.get("precipitation_probability_pct"),
            },
            "dashboard.environment_context.weather_*",
            "degraded",
            weather_availability,
        ),
        "rest_days": leaf(None, "not_available_locally", "missing"),
    }


def collect_field_states(card: dict[str, Any]) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    degraded: list[str] = []
    for dim_name, dim in card.items():
        if not dim_name.endswith("_view") or not isinstance(dim, dict):
            continue
        if dim_name == "market_view":
            if dim.get("availability") != "available":
                missing.append("market_view")
            continue
        for key, value in dim.items():
            if not isinstance(value, dict):
                continue
            state = value.get("availability")
            if state == "missing":
                missing.append(f"{dim_name}.{key}")
            elif state == "degraded":
                degraded.append(f"{dim_name}.{key}")
    return missing, degraded


def basis_tags(card: dict[str, Any]) -> dict[str, int]:
    tags: dict[str, int] = {}
    for dim_name, dim in card.items():
        if not dim_name.endswith("_view") or not isinstance(dim, dict):
            continue
        if dim_name == "market_view":
            tags[dim.get("basis", "missing")] = tags.get(dim.get("basis", "missing"), 0) + 1
            continue
        for value in dim.values():
            if isinstance(value, dict):
                basis = str(value.get("basis", "missing"))
                tags[basis] = tags.get(basis, 0) + 1
    return tags


def dimension_availability(dim_name: str, missing: list[str], degraded: list[str]) -> str:
    dim_missing = any(x.startswith(f"{dim_name}.") for x in missing)
    dim_degraded = any(x.startswith(f"{dim_name}.") for x in degraded)
    if dim_missing and dim_degraded:
        return "degraded"
    if dim_degraded:
        return "degraded"
    if dim_missing:
        return "missing"
    return "available"


def build_card(card_path: Path, dash_by_fixture: dict[str, dict[str, Any]]) -> dict[str, Any]:
    raw = read_json(card_path)
    fid = fixture_id_from_card(raw)
    dash = dash_by_fixture.get(fid, {})
    teams = raw.get("teams", {})
    out: dict[str, Any] = {
        "schema_version": "W1_FIVEDIM_CARD_V1",
        "stage": "W1_FIVEDIM_LITE_STAGE_A",
        "metadata": {
            "fixture_id": fid,
            "match": f"{teams.get('home', {}).get('name')} vs {teams.get('away', {}).get('name')}",
            "kickoff_utc": raw.get("match", {}).get("kickoff_utc"),
            "card_path": str(card_path.relative_to(ROOT)),
        },
        "source_summary": {
            "match_card": str(card_path.relative_to(ROOT)),
            "dashboard_data": str(DASHBOARD_DATA.relative_to(ROOT)) if DASHBOARD_DATA.is_file() else None,
            "policy": str(POLICY_PATH.relative_to(ROOT)),
            "external_fetch_performed": False,
            "production_wired": False,
        },
        "market_view": build_market_view(raw, dash),
        "strength_view": build_strength_view(raw),
        "tactical_view": build_tactical_view(raw),
        "chemistry_view": build_chemistry_view(raw),
        "environment_view": build_environment_view(raw, dash),
        "availability_flags": {},
        "missing_fields": [],
        "degraded_fields": [],
        "basis_tags": {},
        "redline_flags": {
            "independent_edge": False,
            "calibrated": False,
            "external_fetch": False,
            "post_match_only_in_prematch_view": False,
        },
        "independent_edge": False,
    }
    missing, degraded = collect_field_states(out)
    out["missing_fields"] = missing
    out["degraded_fields"] = degraded
    out["basis_tags"] = basis_tags(out)
    out["availability_flags"] = {
        "market_view": out["market_view"]["availability"],
        "strength_view": dimension_availability("strength_view", missing, degraded),
        "tactical_view": dimension_availability("tactical_view", missing, degraded),
        "chemistry_view": dimension_availability("chemistry_view", missing, degraded),
        "environment_view": dimension_availability("environment_view", missing, degraded),
    }
    return out


def build_all() -> dict[str, Any]:
    dash = dashboard_by_fixture()
    cards = [build_card(path, dash) for path in sorted(CARDS_DIR.glob("*.json"))]
    return {
        "schema_version": "W1_FIVEDIM_LITE_STAGE_A_OUTPUT_V1",
        "stage": "W1_FIVEDIM_LITE_STAGE_A",
        "research_only": True,
        "production_wired": False,
        "external_fetch_performed": False,
        "cards_count": len(cards),
        "cards": cards,
    }


def main() -> int:
    policy = read_json(POLICY_PATH)
    output_path = ROOT / policy.get("output_path", str(OUTPUT_PATH_DEFAULT))
    payload = build_all()
    write_json(output_path, payload)
    print(f"W1 FiveDim Lite Stage A built: cards={payload['cards_count']} output={output_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
