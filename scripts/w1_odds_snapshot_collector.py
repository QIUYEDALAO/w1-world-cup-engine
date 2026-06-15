#!/usr/bin/env python3
"""Collect raw per-bookmaker W1 odds snapshots.

The collector stores raw API-Football bookmaker odds as JSONL. It deliberately
does not devig, aggregate, calibrate thresholds, or derive lambda values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "data/odds_snapshots"
RAW_ROOT = OUT_ROOT / "raw"
SCHEMA_PATH = OUT_ROOT / "schema.json"
INDEX_PATH = OUT_ROOT / "index.json"

PHASES = (
    ("T-48h", 48),
    ("T-24h", 24),
    ("T-12h", 12),
    ("T-6h", 6),
    ("T-1h", 1),
    ("T-30m", 0.5),
)


SNAPSHOT_SCHEMA: dict[str, Any] = {
    "schema_version": "W1_ODDS_SNAPSHOT_RAW_V1",
    "description": "Raw per-bookmaker odds snapshots. Devig and consensus are analysis-time operations, not write-time mutations.",
    "required_fields": [
        "fixture_id",
        "local_card_id",
        "alias_fixture_ids",
        "match",
        "kickoff_utc",
        "captured_at_utc",
        "phase",
        "source",
        "bookmaker",
        "market",
        "raw_odds",
        "line",
        "suspended",
        "stale",
        "live",
        "book_count_by_market",
        "api_payload_ref",
        "raw_payload_hash",
        "lineup_confirmed_utc",
    ],
    "markets": {
        "1X2": "raw_odds contains home/draw/away if available",
        "OU": "raw_odds contains over/under and line",
        "AH": "raw_odds contains home/away and line",
    },
    "non_goals": [
        "Do not store consensus-only rows as bookmaker rows.",
        "Do not devig at write time.",
        "Do not calibrate odds movement thresholds from a single fixture.",
    ],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = str(raw).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except ValueError:
        return None


def phase_from_kickoff(kickoff_utc: str | None, captured_at_utc: str) -> str:
    kickoff = parse_utc(kickoff_utc)
    captured = parse_utc(captured_at_utc)
    if not kickoff or not captured:
        return "AD_HOC"
    delta_hours = (kickoff - captured).total_seconds() / 3600
    if delta_hours <= 0:
        return "CLOSING"
    return min(PHASES, key=lambda item: abs(delta_hours - item[1]))[0]


def payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_aliases() -> dict[str, list[str]]:
    path = ROOT / "data/fixture_aliases.json"
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for k, v in raw.items():
        out.setdefault(str(k), [])
        if v:
            out[str(k)].append(str(v))
    return out


def infer_market(bet_name: str) -> str | None:
    name = bet_name.lower()
    if name in {"match winner", "1x2"} or "winner" in name:
        return "1X2"
    if "goals over/under" in name or "over/under" in name:
        return "OU"
    if "asian handicap" in name or "handicap" in name:
        return "AH"
    return None


def normalise_value(market: str, value: str, odd: Any) -> tuple[str | None, dict[str, Any]]:
    value_text = str(value)
    raw_odds = {"label": value_text, "odds": float(odd) if odd not in (None, "") else None}
    if market == "1X2":
        return None, raw_odds
    parts = value_text.split()
    line = parts[-1] if parts else None
    return line, raw_odds


def records_from_api_payload(
    *,
    payload: dict[str, Any],
    match: dict[str, Any],
    captured_at_utc: str | None = None,
    source: str = "api-football odds",
    api_payload_ref: str | None = None,
) -> list[dict[str, Any]]:
    captured = captured_at_utc or utc_now()
    fixture_id = str(match.get("fixture_id") or match.get("local_card_id") or "")
    aliases = load_aliases().get(fixture_id, [])
    kickoff_utc = match.get("kickoff_utc")
    phase = match.get("phase") or phase_from_kickoff(kickoff_utc, captured)
    digest = payload_hash(payload)
    rows: list[dict[str, Any]] = []
    response = payload.get("response") or []
    for fixture_row in response:
        bookmakers = fixture_row.get("bookmakers") or []
        book_count_by_market: dict[str, int] = {}
        for bookmaker in bookmakers:
            for bet in bookmaker.get("bets") or []:
                market = infer_market(str(bet.get("name", "")))
                if market:
                    book_count_by_market[market] = book_count_by_market.get(market, 0) + 1
        for bookmaker in bookmakers:
            bookmaker_name = str(bookmaker.get("name") or bookmaker.get("id") or "unknown")
            for bet in bookmaker.get("bets") or []:
                market = infer_market(str(bet.get("name", "")))
                if not market:
                    continue
                for value in bet.get("values") or []:
                    line, raw_odds = normalise_value(market, value.get("value"), value.get("odd"))
                    rows.append(
                        {
                            "schema_version": "W1_ODDS_SNAPSHOT_RAW_V1",
                            "fixture_id": fixture_id,
                            "local_card_id": str(match.get("local_card_id") or fixture_id),
                            "alias_fixture_ids": aliases,
                            "match": match.get("match"),
                            "kickoff_utc": kickoff_utc,
                            "captured_at_utc": captured,
                            "phase": phase,
                            "source": source,
                            "bookmaker": bookmaker_name,
                            "market": market,
                            "raw_odds": raw_odds,
                            "line": line,
                            "suspended": bool(value.get("suspended", False)),
                            "stale": bool(value.get("stale", False)),
                            "live": bool(value.get("live", False)),
                            "book_count_by_market": book_count_by_market,
                            "api_payload_ref": api_payload_ref,
                            "raw_payload_hash": digest,
                            "lineup_confirmed_utc": match.get("lineup_confirmed_utc"),
                        }
                    )
    return rows


def write_schema() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(json.dumps(SNAPSHOT_SCHEMA, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_records(records: list[dict[str, Any]], captured_at_utc: str | None = None) -> Path:
    captured = parse_utc(captured_at_utc or (records[0]["captured_at_utc"] if records else utc_now())) or datetime.now(timezone.utc)
    day_dir = RAW_ROOT / captured.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    out_path = day_dir / "odds_snapshots.jsonl"
    if records:
        with out_path.open("a", encoding="utf-8") as fh:
            for record in records:
                fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    else:
        out_path.touch(exist_ok=True)
    update_index(out_path, len(records))
    return out_path


def update_index(out_path: Path, new_records: int) -> None:
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.is_file() else {
        "schema_version": "W1_ODDS_SNAPSHOT_INDEX_V1",
        "raw_root": "data/odds_snapshots/raw",
        "files": [],
        "total_records": 0,
        "empty_reason": None,
    }
    rel = str(out_path.relative_to(ROOT))
    files = {item["path"]: item for item in index.get("files", [])}
    item = files.setdefault(rel, {"path": rel, "records": 0})
    item["records"] = int(item.get("records", 0)) + int(new_records)
    files[rel] = item
    index["files"] = sorted(files.values(), key=lambda row: row["path"])
    index["total_records"] = sum(int(item.get("records", 0)) for item in index["files"])
    if index["total_records"] == 0:
        index["empty_reason"] = "No live API odds payload has been captured yet; schema is ready and empty JSONL is intentional."
    else:
        index["empty_reason"] = None
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def initialise_empty() -> Path:
    write_schema()
    out_path = append_records([], utc_now())
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--init-empty", action="store_true", help="create schema, index, and an empty JSONL file")
    parser.add_argument("--payload", type=Path, help="API-Football odds payload JSON")
    parser.add_argument("--fixture-id")
    parser.add_argument("--match")
    parser.add_argument("--kickoff-utc")
    parser.add_argument("--lineup-confirmed-utc")
    args = parser.parse_args()
    write_schema()
    if args.init_empty or not args.payload:
        out_path = initialise_empty()
        print(f"W1 odds snapshot collection initialized: {out_path.relative_to(ROOT)}")
        return 0
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    match = {
        "fixture_id": args.fixture_id,
        "local_card_id": args.fixture_id,
        "match": args.match,
        "kickoff_utc": args.kickoff_utc,
        "lineup_confirmed_utc": args.lineup_confirmed_utc,
    }
    records = records_from_api_payload(payload=payload, match=match, api_payload_ref=str(args.payload))
    out_path = append_records(records)
    print(f"W1 odds snapshot records written: records={len(records)} path={out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
