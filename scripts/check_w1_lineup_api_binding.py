#!/usr/bin/env python3
"""Validate W1_LINEUP_API_BINDING_FIX_V1."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "scripts/w1_local_predict_server.py"
BUILDER = ROOT / "scripts/build_w1_dashboard_data.py"
ALIASES = ROOT / "data/fixture_aliases.json"
DASHBOARD_DATA = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
GERMANY_CARD = ROOT / "data/processed/match_cards/group_stage_round1/fixture_1489374_germany_vs_cura-ao.json"
SCORE_ENGINE = ROOT / "scripts/w1_score_engine.py"


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load(path: Path) -> dict:
    return json.loads(read(path))


def refresh_lineups_source() -> str:
    source = read(SERVER)
    match = re.search(r"def refresh_lineups\(.*?^def refresh_referee_module", source, re.S | re.M)
    if not match:
        fail("refresh_lineups block not found")
    return match.group(0)


def main() -> int:
    try:
        for path in (SERVER, BUILDER, ALIASES, DASHBOARD_DATA, GERMANY_CARD, SCORE_ENGINE):
            if not path.is_file():
                fail(f"missing required file: {path.relative_to(ROOT)}")

        aliases = load(ALIASES)
        if aliases.get("66457070") != "1489374" or aliases.get("1489374") != "66457070":
            fail("fixture alias 66457070 <-> 1489374 is not configured")

        server_source = read(SERVER)
        for marker in ("api_fixture_id_candidates", "requested_fixture_id", "fetch_live_lineups_from_api(api_fixture_id"):
            if marker not in server_source:
                fail(f"server missing lineup API binding marker: {marker}")

        lineup_block = refresh_lineups_source()
        if "api_fixture_id_candidates(match)" not in lineup_block:
            fail("refresh_lineups must try request/alias API fixture ids")
        if "write_lineups_to_card(fixture_id, lineups)" not in lineup_block:
            fail("refresh_lineups must write back to the local match card fixture id")
        if "lambda" in lineup_block.lower():
            fail("lineup refresh must not directly adjust lambda")

        builder_source = read(BUILDER)
        for marker in ("squad_ready_lineup_missing", "lineup_confirmed", "lineup_source", "lineup_updated_at"):
            if marker not in builder_source:
                fail(f"builder missing dashboard binding marker: {marker}")
        for marker in ("lineup_payload_type", "lineup_confirmed_utc"):
            if marker not in builder_source or marker not in server_source:
                fail(f"lineup binding missing marker: {marker}")

        card = load(GERMANY_CARD)
        lineups = card.get("lineups", {})
        squad = card.get("squad", {})
        home_squad = squad.get("home", {})
        away_squad = squad.get("away", {})
        squad_available = bool(home_squad.get("available")) and bool(away_squad.get("available"))
        home_xi = lineups.get("home_starting_xi") or []
        away_xi = lineups.get("away_starting_xi") or []
        card_confirmed = bool(lineups.get("confirmed_lineup_available"))
        if squad_available and (len(home_xi) < 11 or len(away_xi) < 11) and card_confirmed:
            fail("squad-only data must not be marked as confirmed starting XI")

        data = load(DASHBOARD_DATA)
        rows = data.get("match_records", [])
        row = next((item for item in rows if str(item.get("fixture_id")) == "1489374"), None)
        if not row:
            fail("Germany vs Curacao match_record 1489374 missing")

        dq_lineup = row.get("data_quality", {}).get("lineup", {})
        row_confirmed = bool(row.get("lineup_confirmed") or row.get("confirmed_lineup_available"))
        if card_confirmed or row_confirmed:
            if not row_confirmed:
                fail("confirmed starting XI in card must be reflected in dashboard_data")
            if row.get("lineup_payload_type") != "starting_xi":
                fail("confirmed lineup must expose lineup_payload_type=starting_xi")
            if not row.get("lineup_confirmed_utc"):
                fail("confirmed lineup must expose lineup_confirmed_utc")
            if int(row.get("home_starting_count") or 0) < 11 or int(row.get("away_starting_count") or 0) < 11:
                fail("confirmed lineup must expose 11 starters per team")
            if not (row.get("lineup_source") or row.get("lineups", {}).get("source")):
                fail("confirmed lineup must expose lineup_source")
            if not row.get("lineup_updated_at"):
                fail("confirmed lineup must expose lineup_updated_at")
        else:
            if squad_available:
                status = str(dq_lineup.get("status") or "")
                if status not in {"squad_ready_lineup_missing", "名单已获取，首发未确认"}:
                    fail("squad-ready lineup-missing state must be explicit in dashboard_data")
                if row.get("lineup_payload_type") == "starting_xi":
                    fail("squad-only data must not expose lineup_payload_type=starting_xi")
            if row_confirmed:
                fail("dashboard_data must not mark squad-only data as confirmed")

        score_source = read(SCORE_ENGINE)
        if "DEFAULT_RHO = -0.057766" not in score_source:
            fail("DEFAULT_RHO changed unexpectedly")

        print("PASS W1_LINEUP_API_BINDING_FIX_V1")
        return 0
    except CheckError as exc:
        print(f"FAIL W1_LINEUP_API_BINDING_FIX_V1: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
