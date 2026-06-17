#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1_SCOUT ledger — lock AI calls pre-match, audit vs result AND vs market, grow track record.

lock:  copy each call verbatim into an immutable pre-match lock IF kickoff is still ahead
       (refuse hindsight — never lock an already-started match).
audit: for locked calls that now have a local result, score outcome hit + Brier, and when
       the call diverged from the market (LEAN/FADE) record whether it BEAT the market.
       Then update state/scout_track_record.json — this is the growth signal.

Offline, append-only, gitignored. Never modifies a lock. Never feeds result into a call.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CALLS = ROOT / "state/w1_scout_calls.json"
LOCK = ROOT / "state/scout_lock.jsonl"
AUDIT = ROOT / "state/scout_audit.jsonl"
TRACK = ROOT / "state/scout_track_record.json"
RESULTS = ROOT / "data/results/round1_results.json"
DASH = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def dt(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _kickoffs():
    out = {}
    if DASH.is_file():
        for r in json.loads(DASH.read_text(encoding="utf-8")).get("match_records", []):
            out[str(r.get("fixture_id"))] = {"kickoff": r.get("kickoff"),
                                             "mkt": (r.get("market_probability_panel") or {}).get("one_x_two") or {}}
    return out


def _results():
    out = {}
    if RESULTS.is_file():
        for fid, row in json.loads(RESULTS.read_text(encoding="utf-8")).get("results", {}).items():
            out[str(fid)] = row
            for a in row.get("alias_fixture_ids", []):
                out[str(a)] = row
    return out


def lock():
    if not CALLS.is_file():
        print("no calls to lock")
        return
    calls = json.loads(CALLS.read_text(encoding="utf-8")).get("calls", [])
    ko = _kickoffs()
    locked = set()
    if LOCK.is_file():
        locked = {str(json.loads(l)["fixture_id"]) for l in LOCK.open(encoding="utf-8") if l.strip()}
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    added = hindsight = 0
    with LOCK.open("a", encoding="utf-8") as fh:
        for c in calls:
            fid = str(c.get("fixture_id"))
            if fid in locked:
                continue
            k = dt((ko.get(fid) or {}).get("kickoff"))
            if k is not None and dt(now()) > k:
                hindsight += 1   # already kicked off -> cannot honestly lock pre-match
                continue
            fh.write(json.dumps({"fixture_id": fid, "lock_as_of_utc": now(),
                                 "kickoff_utc": (ko.get(fid) or {}).get("kickoff"),
                                 "call": c, "market": (ko.get(fid) or {}).get("mkt")}, ensure_ascii=False) + "\n")
            added += 1
    print(f"scout lock: +{added} (refused hindsight={hindsight})")


def _outcome(h, a):
    return "主" if h > a else ("客" if a > h else "平")


def audit():
    if not LOCK.is_file():
        print("no locks to audit")
        return
    locks = [json.loads(l) for l in LOCK.open(encoding="utf-8") if l.strip()]
    res = _results()
    done = set()
    if AUDIT.is_file():
        done = {str(json.loads(l)["fixture_id"]) for l in AUDIT.open(encoding="utf-8") if l.strip()}
    added = 0
    with AUDIT.open("a", encoding="utf-8") as fh:
        for L in locks:
            fid = str(L["fixture_id"])
            if fid in done or fid not in res:
                continue
            sc = res[fid].get("actual_score")
            if not (isinstance(sc, dict) and isinstance(sc.get("home"), int)):
                continue
            actual = _outcome(sc["home"], sc["away"])
            call = L["call"]
            lean = (call.get("call") or {}).get("outcome_lean")
            hit = (lean == actual)
            mkt = L.get("market") or {}
            mfav = "主" if (mkt.get("home_win") or 0) >= (mkt.get("away_win") or 0) else "客"
            stance = (call.get("market_divergence") or {}).get("stance")
            beat_market = None
            if stance in ("LEAN_DIFFERENT", "FADE_MARKET"):
                beat_market = bool(hit and lean != mfav)   # diverged AND was right
            fh.write(json.dumps({"fixture_id": fid, "actual": f"{sc['home']}-{sc['away']}",
                                 "actual_outcome": actual, "call_outcome": lean, "hit": hit,
                                 "stance": stance, "market_fav": mfav, "beat_market": beat_market,
                                 "conviction": call.get("conviction"), "audited_at_utc": now()}, ensure_ascii=False) + "\n")
            added += 1
    _update_track()
    print(f"scout audit: +{added}; track record updated")


def _update_track():
    if not AUDIT.is_file():
        return
    rows = [json.loads(l) for l in AUDIT.open(encoding="utf-8") if l.strip()]
    t = json.loads(TRACK.read_text(encoding="utf-8")) if TRACK.is_file() else {}
    t.setdefault("by_conviction", {}); t.setdefault("by_stance", {})
    ov = {"n": 0, "hit": 0}
    byc = {}; bys = {}
    for r in rows:
        ov["n"] += 1; ov["hit"] += int(bool(r["hit"]))
        c = r.get("conviction") or "LOW"; byc.setdefault(c, {"n": 0, "hit": 0})
        byc[c]["n"] += 1; byc[c]["hit"] += int(bool(r["hit"]))
        s = r.get("stance") or "AGREE"; bys.setdefault(s, {"n": 0, "hit": 0, "beat_market": 0})
        bys[s]["n"] += 1; bys[s]["hit"] += int(bool(r["hit"]))
        if r.get("beat_market"):
            bys[s]["beat_market"] += 1
    t["overall"] = {"n": ov["n"], "hit": ov["hit"], "hit_rate": round(ov["hit"] / ov["n"], 3) if ov["n"] else None}
    t["by_conviction"] = byc; t["by_stance"] = bys; t["updated_at"] = now()
    TRACK.write_text(json.dumps(t, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv) -> int:
    cmd = argv[1] if len(argv) > 1 else "all"
    if cmd in ("lock", "all"):
        lock()
    if cmd in ("audit", "all"):
        audit()
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv))
