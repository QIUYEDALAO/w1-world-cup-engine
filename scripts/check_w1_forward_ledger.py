#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 Forward-Ledger checker.

Validates the pre-match snapshot ledger: required fields, as_of_utc present,
availability flags, and the leakage guard (NO post-match field). Append-only is
enforced structurally (JSONL). Skips cleanly if the gitignored ledger is absent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data/forward_ledger/w1_forward_ledger.jsonl"
SCHEMA = ROOT / "config/w1_forward_ledger_schema.json"
REQUIRED = ["fixture_id", "as_of_utc", "snapshot_phase", "data_source", "availability"]
errors: list[str] = []


def fail(m: str) -> None:
    errors.append(m)


def main() -> int:
    if not SCHEMA.is_file():
        print("FAIL: config/w1_forward_ledger_schema.json missing", file=sys.stderr)
        return 1
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    forbidden = set(schema.get("forbidden_fields", []))
    allowed_sources = set(schema.get("allowed_sources", []))

    if not LEDGER.is_file():
        print("SKIP check_w1_forward_ledger: ledger not generated yet (run snapshot_w1_forward_ledger.py)")
        return 0

    n = 0
    for i, line in enumerate(LEDGER.open(encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        n += 1
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            fail(f"line {i}: invalid JSON (append-only JSONL expected)")
            continue
        for k in REQUIRED:
            if k not in row:
                fail(f"line {i}: missing required field {k}")
        if not row.get("as_of_utc"):
            fail(f"line {i}: empty as_of_utc")
        if row.get("data_source") not in allowed_sources:
            fail(f"line {i}: data_source '{row.get('data_source')}' not in allowed {sorted(allowed_sources)} (no external source)")
        hit = forbidden.intersection(row.keys())
        if hit:
            fail(f"line {i}: LEAKAGE — post-match field(s) present: {sorted(hit)}")
        av = row.get("availability", {})
        if not isinstance(av, dict) or not {"lineup", "odds", "weather", "referee", "tactical"}.issubset(av):
            fail(f"line {i}: availability flags incomplete")

    if errors:
        for e in errors[:20]:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"W1 forward-ledger check FAIL ({len(errors)})")
        return 1
    print(f"W1 forward-ledger check PASS (rows={n}, no post-match leakage, as_of present)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
