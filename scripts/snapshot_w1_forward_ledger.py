#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 Forward-Ledger: append pre-match snapshots for upcoming fixtures.

Reads ONLY local dashboard data / match cards (no external fetch). For each
not-yet-finished fixture it appends one pre-match snapshot row (as_of=now) with
availability flags and null placeholders where data is absent. Never writes any
post-match field (leakage guard enforced by the schema + checker).

Store: data/forward_ledger/w1_forward_ledger.jsonl (append-only, gitignored).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
LEDGER = ROOT / "data/forward_ledger/w1_forward_ledger.jsonl"

FORBIDDEN = {
    "actual_score", "result", "home_goals", "away_goals", "home_goals_90", "away_goals_90",
    "finish_type", "score", "post_match_calibration", "rps", "rps_1x2", "log_loss",
    "exact_score_log_loss", "outcome", "hit_status", "actual_score_probability",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def snapshot_phase(kickoff: datetime | None, as_of: datetime) -> str:
    if not kickoff:
        return "unknown"
    h = (kickoff - as_of).total_seconds() / 3600
    if h <= 0:
        return "pre_kickoff"
    for label, thr in (("T-1h", 1), ("T-2h", 2), ("T-6h", 6), ("T-12h", 12), ("T-24h", 24), ("T-48h", 48)):
        if h <= thr:
            return label
    return "T-48h"


def build_snapshot(r: dict[str, Any], as_of: str) -> dict[str, Any]:
    ko = parse_dt(r.get("kickoff_utc"))
    lineups = r.get("lineups", {}) or {}
    env = r.get("environment_context", {}) or {}
    om = r.get("odds_movement", {}) or {}
    dq = r.get("data_quality", {}) or {}
    odds_q = (dq.get("odds") or {}) if isinstance(dq, dict) else {}
    mp = r.get("market_probability_panel", {}) or {}
    mc = (mp.get("market_comparison") or {}) if isinstance(mp, dict) else {}
    oxt = mc.get("one_x_two_market") or {}
    tac = r.get("tactical_effect", {}) or {}
    referee_name = r.get("referee_name") or None
    referee_assigned = bool(referee_name) or str(r.get("referee_status", "")).upper() == "READY"

    lineup_ok = bool(lineups.get("home_starting_players") or r.get("lineup_confirmed"))
    odds_ok = bool(oxt) or str(r.get("odds_status", "")).upper() == "READY"
    weather_ok = str(env.get("weather_status", "")).lower() == "ready"
    tactical_ok = bool(tac.get("tactical_summary_cn") or tac.get("status") == "ready")

    snap = {
        "schema_version": "W1_FORWARD_LEDGER_V1",
        "fixture_id": str(r.get("fixture_id")),
        "match": r.get("match"),
        "kickoff_utc": r.get("kickoff_utc"),
        "as_of_utc": as_of,
        "snapshot_phase": snapshot_phase(ko, parse_dt(as_of)),
        "data_source": "local_card",
        "lineup_status": r.get("lineup_status") or lineups.get("status"),
        "confirmed_lineup": bool(r.get("lineup_confirmed")),
        "confirmed_lineup_utc": r.get("lineup_confirmed_utc"),
        "home_starting_xi": [p.get("name") if isinstance(p, dict) else p for p in (lineups.get("home_starting_players") or [])],
        "away_starting_xi": [p.get("name") if isinstance(p, dict) else p for p in (lineups.get("away_starting_players") or [])],
        "home_formation": r.get("home_formation"),
        "away_formation": r.get("away_formation"),
        "key_absences": (r.get("lineup_effect", {}) or {}).get("key_absences", []),
        "odds_phase": r.get("prediction_stage_cn") or r.get("prediction_stage"),
        "odds_1x2": {"home": oxt.get("home_win"), "draw": oxt.get("draw"), "away": oxt.get("away_win")},
        "candidates_snapshot": r.get("candidates_snapshot", {}),
        "odds_snapshot_utc": odds_q.get("snapshot_time"),
        "market_movement_status": om.get("status"),
        "weather_status": env.get("weather_status"),
        "temperature_c": env.get("temperature_c"),
        "wind_kmh": env.get("wind_speed_kmh"),
        "precip_prob": env.get("precipitation_probability_pct"),
        "referee_assigned": referee_assigned,
        "referee_name": referee_name,
        "tactical_notes": [tac["tactical_summary_cn"]] if tac.get("tactical_summary_cn") else [],
        "availability": {
            "lineup": lineup_ok, "odds": odds_ok, "weather": weather_ok,
            "referee": referee_assigned, "tactical": tactical_ok,
        },
    }
    # leakage guard: never emit a forbidden field
    for k in list(snap.keys()):
        if k in FORBIDDEN:
            del snap[k]
    return snap


def is_upcoming(r: dict[str, Any], as_of: datetime) -> bool:
    if r.get("status") == "finished":
        return False
    ko = parse_dt(r.get("kickoff_utc"))
    # snapshot if kickoff unknown or still in the future
    return ko is None or ko > as_of


def main() -> int:
    if not DASH.is_file():
        raise SystemExit(f"dashboard data not found: {DASH}")
    data = json.loads(DASH.read_text(encoding="utf-8"))
    as_of = now_utc()
    as_of_dt = parse_dt(as_of)
    rows = [r for r in data.get("match_records", []) if is_upcoming(r, as_of_dt)]
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with LEDGER.open("a", encoding="utf-8") as fh:
        for r in rows:
            snap = build_snapshot(r, as_of)
            fh.write(json.dumps(snap, ensure_ascii=False, sort_keys=True) + "\n")
            written += 1
    total = sum(1 for _ in LEDGER.open(encoding="utf-8")) if LEDGER.is_file() else 0
    print(f"W1 forward-ledger: appended {written} pre-match snapshots (as_of={as_of}); ledger total rows={total}")
    if written == 0:
        print("  note: no upcoming (not-finished, future-kickoff) fixtures in local data right now.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
