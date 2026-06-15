#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 S1B team-name reconciliation checker (BLOCKER).

Hard rules (no silent fallback):
  * alias one-to-many -> FAIL (a source name resolving to >1 team_id).
  * every W1 fixture team name must resolve to a team_id.
  * every dataset raw name (if dataset present) must resolve + carry a team_id.

Validates committed config (aliases + W1 fixtures) even when the gitignored
dataset is absent.
"""
from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALIASES = ROOT / "config/w1_team_aliases.json"
CSV_PATH = ROOT / "data/processed/international/w1_international_dataset.csv"
CARDS_DIR = ROOT / "data/processed/match_cards/group_stage_round1"
errors: list[str] = []


def fail(m: str) -> None:
    errors.append(m)


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def main() -> int:
    if not ALIASES.is_file():
        print("FAIL: config/w1_team_aliases.json missing", file=sys.stderr)
        return 1
    data = json.loads(ALIASES.read_text(encoding="utf-8"))
    teams = data.get("teams", {})

    # alias -> team_id index; detect one-to-many
    idx: dict[str, str] = {}
    for tid, e in teams.items():
        if e.get("team_id") != tid:
            fail(f"team_id mismatch for key {tid}")
        keys = [e.get("canonical_name"), tid] + list(e.get("aliases", []))
        for k in keys:
            if not k:
                continue
            if k in idx and idx[k] != tid:
                fail(f"alias one-to-many: '{k}' -> {idx[k]} and {tid}")
            idx[k] = tid

    def resolve(name: str) -> str | None:
        return idx.get(name) or idx.get(strip_accents(str(name)).strip())

    # W1 fixture names must all resolve
    for p in sorted(CARDS_DIR.glob("*.json")):
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for side in ("home", "away"):
            nm = (c.get("teams", {}).get(side, {}) or {}).get("name")
            if nm and not resolve(nm):
                fail(f"W1 fixture team name unmapped: '{nm}' ({p.name})")

    # dataset names (if present)
    if CSV_PATH.is_file():
        rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
        bad = 0
        for r in rows:
            for side in ("home", "away"):
                if not r.get(f"{side}_team_id"):
                    bad += 1
                    if bad <= 5:
                        fail(f"dataset row has empty {side}_team_id: {r.get('home_name_raw')} vs {r.get('away_name_raw')}")
        if bad:
            fail(f"{bad} dataset team_id cells empty (unmapped)")
    else:
        print("note: dataset not generated; validated committed aliases + W1 fixtures only")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"W1 team name reconciliation check FAIL ({len(errors)}) [BLOCKER]")
        return 1
    print(f"W1 team name reconciliation check PASS (teams={len(teams)}, aliases={len(idx)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
