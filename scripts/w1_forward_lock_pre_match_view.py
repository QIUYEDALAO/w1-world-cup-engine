#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1_FORWARD_LEDGER_PROSPECTIVE_RUN_V1 — lock immutable pre-match views.

Reads the pre-match snapshot ledger (data/forward_ledger/w1_forward_ledger.jsonl)
and, for each fixture, LOCKS a single immutable pre_match_view from the latest
snapshot whose as_of_utc <= kickoff_utc (genuine pre-match, no hindsight). The
locked prediction is the market-implied 1X2 probabilities (V1 scope).

Immutable / write-once: if a view already exists for a fixture it is left untouched.
Append-only JSONL store, gitignored. No external fetch; no model change.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data/forward_ledger/w1_forward_ledger.jsonl"
VIEW = ROOT / "data/forward_ledger/w1_pre_match_view.jsonl"


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def locked_p1x2(odds: dict[str, Any] | None) -> dict[str, float] | None:
    if not isinstance(odds, dict):
        return None
    try:
        h, d, a = float(odds.get("home")), float(odds.get("draw")), float(odds.get("away"))
    except (TypeError, ValueError):
        return None
    s = h + d + a
    if s <= 0:
        return None
    return {"p_home": round(h / s, 6), "p_draw": round(d / s, 6), "p_away": round(a / s, 6)}


def pick_pre_match_snapshot(snaps: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Latest snapshot with as_of <= kickoff (genuine pre-match). If kickoff unknown,
    fall back to the latest snapshot by as_of."""
    ko = parse_dt(snaps[0].get("kickoff_utc"))
    eligible = []
    for s in snaps:
        ao = parse_dt(s.get("as_of_utc"))
        if ao is None:
            continue
        if ko is None or ao <= ko:
            eligible.append((ao, s))
    if not eligible:
        return None
    eligible.sort(key=lambda x: x[0])
    return eligible[-1][1]


def main() -> int:
    if not LEDGER.is_file():
        print(f"SKIP lock: pre-match ledger not found ({LEDGER.relative_to(ROOT)}). Run snapshot_w1_forward_ledger.py first.")
        return 0

    rows = [json.loads(l) for l in LEDGER.open(encoding="utf-8") if l.strip()]
    by_fixture: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_fixture.setdefault(str(r.get("fixture_id")), []).append(r)

    already: set[str] = set()
    if VIEW.is_file():
        for l in VIEW.open(encoding="utf-8"):
            if l.strip():
                already.add(str(json.loads(l).get("fixture_id")))

    VIEW.parent.mkdir(parents=True, exist_ok=True)
    locked, skipped_existing, skipped_no_pred = 0, 0, 0
    with VIEW.open("a", encoding="utf-8") as fh:
        for fid, snaps in by_fixture.items():
            if fid in already:
                skipped_existing += 1
                continue
            snap = pick_pre_match_snapshot(snaps)
            if snap is None:
                skipped_no_pred += 1
                continue
            pred = locked_p1x2(snap.get("odds_1x2"))
            if pred is None:
                skipped_no_pred += 1
                continue
            view = {
                "schema_version": "W1_PROSPECTIVE_AUDIT_V1",
                "record_type": "pre_match_view",
                "fixture_id": fid,
                "match": snap.get("match"),
                "kickoff_utc": snap.get("kickoff_utc"),
                "lock_as_of_utc": snap.get("as_of_utc"),
                "snapshot_phase": snap.get("snapshot_phase"),
                "locked_prediction": {"source": "market_implied_1x2", **pred},
                "availability": snap.get("availability", {}),
                "locked_at_utc": now_utc(),
            }
            fh.write(json.dumps(view, ensure_ascii=False) + "\n")
            locked += 1

    total = sum(1 for _ in VIEW.open(encoding="utf-8")) if VIEW.is_file() else 0
    print(f"W1 pre_match_view lock: locked {locked} new (skipped existing={skipped_existing}, "
          f"no usable pre-match 1X2={skipped_no_pred}); view store total rows={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
