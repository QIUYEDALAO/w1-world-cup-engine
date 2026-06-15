#!/usr/bin/env python3
"""Validate W1_ODDS_SNAPSHOT_COLLECTION_V1 artifacts."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "data/odds_snapshots/schema.json"
INDEX = ROOT / "data/odds_snapshots/index.json"
COLLECTOR = ROOT / "scripts/w1_odds_snapshot_collector.py"

FORBIDDEN = ("投注", "下注", "资金", "稳赚", "必胜", "保证命中")


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load(path: Path) -> dict:
    return json.loads(read(path))


def validate_record(row: dict, path: Path, line_no: int) -> None:
    required = [
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
    ]
    for key in required:
        if key not in row:
            fail(f"{path}:{line_no} missing {key}")
    if row["market"] not in {"1X2", "OU", "AH"}:
        fail(f"{path}:{line_no} invalid market")
    if not isinstance(row["bookmaker"], str) or not row["bookmaker"]:
        fail(f"{path}:{line_no} bookmaker missing")
    if not isinstance(row["raw_odds"], dict) or "odds" not in row["raw_odds"]:
        fail(f"{path}:{line_no} raw_odds must preserve raw bookmaker odds")
    if row["bookmaker"].upper().startswith("CONSENSUS"):
        fail(f"{path}:{line_no} consensus rows must not be stored as bookmaker rows")


def main() -> int:
    try:
        for path in (SCHEMA, INDEX, COLLECTOR):
            if not path.is_file():
                fail(f"missing {path.relative_to(ROOT)}")
        schema = load(SCHEMA)
        if schema.get("schema_version") != "W1_ODDS_SNAPSHOT_RAW_V1":
            fail("schema version mismatch")
        for key in ("bookmaker", "raw_odds", "captured_at_utc", "phase", "market", "line", "lineup_confirmed_utc"):
            if key not in schema.get("required_fields", []):
                fail(f"schema missing required field {key}")
        collector = read(COLLECTOR)
        for token in ("records_from_api_payload", "bookmaker", "raw_odds", "Do not devig at write time", "lineup_confirmed_utc"):
            if token not in collector:
                fail(f"collector missing token {token}")
        if "devig_" in collector or "consensus" in collector.lower() and "Do not store consensus" not in collector:
            fail("collector must not devig or write consensus-only rows")
        index = load(INDEX)
        if index.get("schema_version") != "W1_ODDS_SNAPSHOT_INDEX_V1":
            fail("index version mismatch")
        files = index.get("files", [])
        if not files:
            fail("index must list at least the empty/current JSONL target")
        total = int(index.get("total_records") or 0)
        if total == 0 and not index.get("empty_reason"):
            fail("empty collection must explain why no live data is present")
        for item in files:
            path = ROOT / item["path"]
            if not path.is_file():
                fail(f"indexed JSONL missing: {item['path']}")
            records = 0
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if not line.strip():
                    continue
                records += 1
                validate_record(json.loads(line), path, line_no)
            if records != int(item.get("records") or 0):
                fail(f"{item['path']} index record count mismatch")
        text = "\n".join([read(SCHEMA), read(INDEX), read(COLLECTOR)])
        for term in FORBIDDEN:
            if term in text:
                fail(f"forbidden wording found: {term}")
        if re.search(r"api[_-]?key|secret|password|Bearer ", text, re.I):
            fail("secret-like literal found")
    except Exception as exc:  # noqa: BLE001
        print(f"W1 odds snapshot collection check FAIL: {exc}", file=sys.stderr)
        return 1
    print("W1 odds snapshot collection check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
