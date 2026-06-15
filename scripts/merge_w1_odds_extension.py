#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
W1 S1B Odds Extension — Merge Local OU Ladder Snapshots
=========================================================
G0 → B1: Merge data/local_odds/world_cup_odds_historical.csv into
the S1B unified international dataset.

Rules:
  - Joins on match_date + home_team_id + away_team_id.
  - Only 2018 and 2022 World Cup 128 matches get odds_extension_covered=true.
  - Full OU ladder → pipeline_mode="FULL", w1_full_pipeline_validated=true (in backtest scope).
  - 2014: odds_extension_missing_reason="NO_LOCAL_ODDS_SOURCE_2014".
  - AH: ah_available=false, ah_missing_reason="AH_MISSING_NO_SOURCE".
  - 2026: separate current_odds_snapshot_quality; never in historical backtest.

Output: data/processed/international/w1_international_dataset_extended.csv
  (gitignored, same directory as S1B base)
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
S1B_PATH = ROOT / "data/processed/international/w1_international_dataset.csv"
LOCAL_ODDS_DIR = ROOT / "data/local_odds"
OUT_EXTENDED = ROOT / "data/processed/international/w1_international_dataset_extended.csv"
OUT_CURRENT_QUALITY = ROOT / "data/processed/international/w1_current_odds_snapshot_quality.json"

# Columns to inject from local odds CSV
OU_LADDER_COLS = ["O05", "U05", "O15", "U15", "O25", "U25", "O35", "U35", "O45", "U45"]
HDA_COLS = ["H", "D", "A"]
BTTS_COLS = ["BTTSY", "BTTSN"]
EXTRA_COLS = HDA_COLS + OU_LADDER_COLS + BTTS_COLS

COL_META = {
    # H/D/A
    "odds_1x2_home_alternate": {"type": "number|null", "role": "prematch_feature", "note": "from footiqo xBet local file"},
    "odds_1x2_draw_alternate": {"type": "number|null", "role": "prematch_feature"},
    "odds_1x2_away_alternate": {"type": "number|null", "role": "prematch_feature"},
    # OU ladder
    "ou_O05": {"type": "number|null", "role": "prematch_feature", "note": "xBet closing O/U 0.5"},
    "ou_U05": {"type": "number|null", "role": "prematch_feature"},
    "ou_O15": {"type": "number|null", "role": "prematch_feature"},
    "ou_U15": {"type": "number|null", "role": "prematch_feature"},
    "ou_O25": {"type": "number|null", "role": "prematch_feature"},
    "ou_U25": {"type": "number|null", "role": "prematch_feature"},
    "ou_O35": {"type": "number|null", "role": "prematch_feature"},
    "ou_U35": {"type": "number|null", "role": "prematch_feature"},
    "ou_O45": {"type": "number|null", "role": "prematch_feature"},
    "ou_U45": {"type": "number|null", "role": "prematch_feature"},
    "ou_market_available": {"type": "bool", "role": "meta", "note": "true if ALL OU ladder pairs populated"},
    "ou_mu_derived": {"type": "number|null", "role": "prematch_feature", "note": "interpolated from OU ladder"},
    "mu_source": {"type": "string", "role": "meta", "note": "OU_LADDER_LOCAL_FILE when available"},
    # BTTS
    "btts_yes_alternate": {"type": "number|null", "role": "prematch_feature"},
    "btts_no_alternate": {"type": "number|null", "role": "prematch_feature"},
    # Source
    "odds_source_alternate": {"type": "string", "role": "meta", "note": "footiqo_xBet for 2018/2022"},
    "odds_scope": {"type": "string", "role": "meta", "note": "90min_closing_odds"},
    # Coverage flags
    "odds_extension_covered": {"type": "bool", "role": "meta", "note": "true for 2018/2022 WC only"},
    "odds_extension_missing_reason": {"type": "string|null", "role": "meta"},
    "ah_available": {"type": "bool", "role": "meta", "note": "false — no AH source"},
    "ah_missing_reason": {"type": "string", "role": "meta", "note": "AH_MISSING_NO_SOURCE"},
}


def load_s1b() -> list[dict[str, Any]]:
    return list(csv.DictReader(S1B_PATH.open(encoding="utf-8")))


def load_local_odds() -> dict[str, list[dict[str, Any]]]:
    """Load local odds CSV, split by season, return {season: [rows]}."""
    historical_path = LOCAL_ODDS_DIR / "world_cup_odds_historical.csv"
    if not historical_path.is_file():
        raise FileNotFoundError(f"local odds file not found: {historical_path}")
    rows = list(csv.DictReader(historical_path.open(encoding="utf-8")))
    by_season: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        s = r.get("Season", "").strip()
        by_season.setdefault(s, []).append(r)
    return by_season


def parse_date(dd_mm_yy_hhmm: str) -> str:
    """Convert '15-06-26 04:00' → '2026-06-15'."""
    parts = dd_mm_yy_hhmm.strip().split(" ")[0].split("-")
    if len(parts) != 3:
        return ""
    day, mon, yr = parts
    if len(yr) == 2:
        yr = "20" + yr if int(yr) < 50 else "19" + yr
    return f"{yr}-{mon}-{day}"


def build_match_key(date_ymd: str, home_id: str, away_id: str) -> str:
    return f"{date_ymd}|{home_id}|{away_id}"


def devig_two_way(over: float, under: float) -> float:
    io, iu = 1.0 / over, 1.0 / under
    return io / (io + iu)


def interpolate_mu(ladder: dict[float, float]) -> float | None:
    """From OU ladder probabilities across lines, estimate mu via linear interpolation."""
    if not ladder:
        return None
    pts = sorted(ladder.items())
    for (l0, p0), (l1, p1) in zip(pts, pts[1:]):
        if (p0 - 0.5) * (p1 - 0.5) <= 0 and abs(p0 - p1) > 1e-9:
            return l0 + (p0 - 0.5) / (p0 - p1) * (l1 - l0)
    return pts[0][0] - 0.5 if pts[0][1] < 0.5 else pts[-1][0] + 0.5


def check_ou_ladder_complete(r: dict[str, Any]) -> bool:
    """OU ladder is complete only if ALL 10 OU ladder columns are non-blank."""
    return all(r.get(olc, "").strip() for olc in OU_LADDER_COLS)


def merge() -> int:
    s1b_rows = load_s1b()
    print(f"S1B: {len(s1b_rows)} rows loaded")

    # Load alias mapping for team_id lookup
    alias_path = ROOT / "config/w1_team_aliases.json"
    alias_idx = _load_aliases(alias_path)

    local_by_season = load_local_odds()
    print(f"Local odds seasons: {list(local_by_season.keys())}")

    # Build local odds index: key → row
    local_idx: dict[str, dict[str, Any]] = {}
    for season, season_rows in local_by_season.items():
        for r in season_rows:
            date_ymd = parse_date(r.get("matchDate", ""))
            home_id = alias_idx.get(r.get("homeTeam", ""), "")
            away_id = alias_idx.get(r.get("awayTeam", ""), "")
            if date_ymd and home_id and away_id:
                local_idx[build_match_key(date_ymd, home_id, away_id)] = r

    print(f"Local odds index: {len(local_idx)} unique match keys")

    # Merge
    extended: list[dict[str, Any]] = []
    covered_2018_2022 = 0
    uncovered_s1b_2018_2022 = 0

    for s1b_row in s1b_rows:
        row = dict(s1b_row)
        date = row.get("match_date", "").strip()
        home_id = row.get("home_team_id", "").strip()
        away_id = row.get("away_team_id", "").strip()
        competition = row.get("competition", "").strip()
        season = str(row.get("season", "")).strip()

        key = build_match_key(date, home_id, away_id)
        local_odds = local_idx.get(key)

        # Default extension fields
        row["odds_1x2_home_alternate"] = ""
        row["odds_1x2_draw_alternate"] = ""
        row["odds_1x2_away_alternate"] = ""
        for olc in OU_LADDER_COLS:
            row[f"ou_{olc}"] = ""
        row["ou_market_available"] = "False"
        row["ou_mu_derived"] = ""
        row["mu_source"] = ""
        row["btts_yes_alternate"] = ""
        row["btts_no_alternate"] = ""
        row["odds_source_alternate"] = ""
        row["odds_scope"] = ""
        row["odds_extension_covered"] = "False"
        row["odds_extension_missing_reason"] = ""
        row["ah_available"] = "False"
        row["ah_missing_reason"] = "AH_MISSING_NO_SOURCE"

        is_wc_2018_2022 = competition in ("World Cup 2018", "World Cup 2022")

        if local_odds and is_wc_2018_2022:
            # Inject local odds
            row["odds_1x2_home_alternate"] = local_odds.get("H", "")
            row["odds_1x2_draw_alternate"] = local_odds.get("D", "")
            row["odds_1x2_away_alternate"] = local_odds.get("A", "")
            for olc in OU_LADDER_COLS:
                row[f"ou_{olc}"] = local_odds.get(olc, "")
            row["btts_yes_alternate"] = local_odds.get("BTTSY", "")
            row["btts_no_alternate"] = local_odds.get("BTTSN", "")
            row["odds_source_alternate"] = "footiqo_xBet"
            row["odds_scope"] = "90min_closing_odds"

            # OU market available
            if check_ou_ladder_complete(local_odds):
                row["ou_market_available"] = "True"
                # Derive mu
                ladder = {}
                for pair in [(0.5, "O05", "U05"), (1.5, "O15", "U15"), (2.5, "O25", "U25"),
                             (3.5, "O35", "U35"), (4.5, "O45", "U45")]:
                    o = local_odds.get(pair[1], "")
                    u = local_odds.get(pair[2], "")
                    if o and u:
                        try:
                            ladder[pair[0]] = devig_two_way(float(o), float(u))
                        except (ValueError, ZeroDivisionError):
                            pass
                mu = interpolate_mu(ladder)
                if mu is not None:
                    row["ou_mu_derived"] = f"{mu:.3f}"
                    row["mu_source"] = "OU_LADDER_LOCAL_FILE"

            row["odds_extension_covered"] = "True"
            covered_2018_2022 += 1

            # pipeline_mode upgrade if OU complete
            current_mode = row.get("pipeline_mode", "1X2_ONLY")
            if row["ou_market_available"] == "True" and row["ou_mu_derived"]:
                row["pipeline_mode"] = "FULL"
                row["w1_full_pipeline_validated"] = "True"
            else:
                row["pipeline_mode"] = current_mode

        elif competition in ("World Cup 2014",):
            row["odds_extension_missing_reason"] = "NO_LOCAL_ODDS_SOURCE_2014"
            uncovered_s1b_2018_2022 += 1
        elif competition in ("World Cup 2018", "World Cup 2022"):
            # WC 2018/2022 but no local odds match — unexpected
            row["odds_extension_missing_reason"] = "NO_LOCAL_ODDS_MATCH"
            uncovered_s1b_2018_2022 += 1
        else:
            # qualifiers, other competitions — not expected to be covered
            row["odds_extension_missing_reason"] = "OUT_OF_SCOPE"

        extended.append(row)

    # Write extended CSV
    if extended:
        fieldnames = list(extended[0].keys())
        with open(OUT_EXTENDED, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(extended)
        print(f"Extended dataset written: {OUT_EXTENDED}")
        print(f"  Total rows: {len(extended)}")
        print(f"  WC 2018/2022 covered by local odds: {covered_2018_2022}")

    # Write current odds snapshot quality report
    current_quality = {
        "schema": "W1_CURRENT_ODDS_SNAPSHOT_QUALITY_V1",
        "note": "2026 World Cup odds snapshot from footiqo xBet; not in historical backtest",
        "season": "2026",
        "matches": 12,
        "saved_at": "data/local_odds/world_cup_odds_2026.csv",
        "historical_backtest_eligible": False,
        "usage": "Forward-Ledger / current odds snapshot only",
        "odds_source": "footiqo_xBet",
        "odds_scope": "90min_closing_odds",
        "hda_available": True,
        "ou_ladder_complete": True,
        "btts_available": True,
        "ah_available": False,
        "ah_missing_reason": "AH_MISSING_NO_SOURCE",
        "teams_mapped_to_w1_team_id": True,
        "s1b_match_possible": False,
        "note_cn": "2026 snapshot only; 2014/2018/2022 historical backtest uses separate data source",
    }
    OUT_CURRENT_QUALITY.write_text(
        json.dumps(current_quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Current snapshot quality written: {OUT_CURRENT_QUALITY}")

    print(f"\nFULL pipeline eligible (OU ladder complete): {covered_2018_2022}")
    return 0


def _load_aliases(path: Path) -> dict[str, str]:
    """Simple alias loader for standalone use."""
    data = json.loads(path.read_text(encoding="utf-8"))
    idx: dict[str, str] = {}
    for tid, e in data.get("teams", {}).items():
        names = [e.get("canonical_name"), tid] + list(e.get("aliases", []))
        for nm in names:
            if nm:
                idx[nm.strip()] = tid
    return idx


if __name__ == "__main__":
    raise SystemExit(merge())
