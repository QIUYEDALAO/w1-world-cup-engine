#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1_FORWARD_LEDGER_PROSPECTIVE_RUN_V1 — append post-match audits.

For each immutable pre_match_view that (a) has a LOCAL result in
data/results/round1_results.json, (b) was locked before kickoff
(lock_as_of_utc <= kickoff_utc), and (c) has not been audited yet, append a
post_match_audit row that scores the LOCKED 1X2 prediction against the actual
result (RPS / logloss / Brier). The locked prediction is copied verbatim — the
pre_match_view is never modified. Append-only, gitignored, no external fetch.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / "data/forward_ledger/w1_pre_match_view.jsonl"
AUDIT = ROOT / "data/forward_ledger/w1_post_match_audit.jsonl"
RESULTS = ROOT / "data/results/round1_results.json"


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def outcome(h: int, a: int) -> str:
    return "H" if h > a else ("A" if a > h else "D")


def rps_1x2(p: tuple[float, float, float], oc: str) -> float:
    obs = {"H": (1, 0, 0), "D": (0, 1, 0), "A": (0, 0, 1)}[oc]
    cp = [p[0], p[0] + p[1]]
    co = [obs[0], obs[0] + obs[1]]
    return round((cp[0] - co[0]) ** 2 + (cp[1] - co[1]) ** 2, 6)


def logloss_1x2(p: dict[str, float], oc: str) -> float:
    return round(-math.log(max({"H": p["p_home"], "D": p["p_draw"], "A": p["p_away"]}[oc], 1e-12)), 6)


def brier_1x2(p: dict[str, float], oc: str) -> float:
    obs = {"H": (1, 0, 0), "D": (0, 1, 0), "A": (0, 0, 1)}[oc]
    return round((p["p_home"] - obs[0]) ** 2 + (p["p_draw"] - obs[1]) ** 2 + (p["p_away"] - obs[2]) ** 2, 6)


def result_index() -> dict[str, dict[str, Any]]:
    if not RESULTS.is_file():
        return {}
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    idx: dict[str, dict[str, Any]] = {}
    for fid, row in data.get("results", {}).items():
        idx[str(fid)] = row
        for alias in row.get("alias_fixture_ids", []):
            idx[str(alias)] = row
    return idx


def parse_score(row: dict[str, Any]) -> tuple[int, int] | None:
    sc = row.get("actual_score")
    if isinstance(sc, dict) and isinstance(sc.get("home"), int) and isinstance(sc.get("away"), int):
        return sc["home"], sc["away"]
    if isinstance(sc, str) and "-" in sc:
        try:
            h, a = sc.split("-", 1)
            return int(h), int(a)
        except ValueError:
            return None
    return None


def main() -> int:
    if not VIEW.is_file():
        print(f"SKIP audit: no pre_match_view store ({VIEW.relative_to(ROOT)}). Run w1_forward_lock_pre_match_view.py first.")
        return 0

    views = [json.loads(l) for l in VIEW.open(encoding="utf-8") if l.strip()]
    results = result_index()
    audited: set[str] = set()
    if AUDIT.is_file():
        for l in AUDIT.open(encoding="utf-8"):
            if l.strip():
                audited.add(str(json.loads(l).get("fixture_id")))

    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    appended, skip_no_result, skip_audited, skip_hindsight = 0, 0, 0, 0
    with AUDIT.open("a", encoding="utf-8") as fh:
        for v in views:
            fid = str(v.get("fixture_id"))
            if fid in audited:
                skip_audited += 1
                continue
            row = results.get(fid)
            if not row:
                skip_no_result += 1
                continue
            score = parse_score(row)
            if score is None:
                skip_no_result += 1
                continue
            ko = parse_dt(v.get("kickoff_utc"))
            lock = parse_dt(v.get("lock_as_of_utc"))
            if ko is not None and (lock is None or lock > ko):
                skip_hindsight += 1  # not genuinely pre-match; refuse to audit (no hindsight)
                continue
            pred = v.get("locked_prediction", {})
            oc = outcome(score[0], score[1])
            p_tuple = (pred.get("p_home", 0.0), pred.get("p_draw", 0.0), pred.get("p_away", 0.0))
            audit = {
                "schema_version": "W1_PROSPECTIVE_AUDIT_V1",
                "record_type": "post_match_audit",
                "fixture_id": fid,
                "match": v.get("match"),
                "kickoff_utc": v.get("kickoff_utc"),
                "lock_as_of_utc": v.get("lock_as_of_utc"),
                "locked_prediction": pred,  # verbatim copy — immutability
                "result": {"home": score[0], "away": score[1], "outcome": oc, "source": "local_round1_results"},
                "prospective_calibration": {
                    "evaluation_method": "prospective_locked_pre_match_1x2",
                    "rps_1x2": rps_1x2(p_tuple, oc),
                    "logloss_1x2": logloss_1x2(pred, oc),
                    "brier_1x2": brier_1x2(pred, oc),
                    "prob_of_actual_outcome": round({"H": pred.get("p_home", 0.0), "D": pred.get("p_draw", 0.0), "A": pred.get("p_away", 0.0)}[oc], 6),
                },
                "audited_at_utc": now_utc(),
            }
            fh.write(json.dumps(audit, ensure_ascii=False) + "\n")
            appended += 1

    total = sum(1 for _ in AUDIT.open(encoding="utf-8")) if AUDIT.is_file() else 0
    print(f"W1 post_match_audit: appended {appended} (skipped: no local result={skip_no_result}, "
          f"already audited={skip_audited}, refused non-pre-match={skip_hindsight}); audit store total rows={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
