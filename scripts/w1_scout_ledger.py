#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1_SCOUT ledger — lock AI reads pre-match, audit vs result, grow calibration memory.

lock:  copy each read verbatim into an immutable pre-match lock IF kickoff is still ahead
       (refuse hindsight — never lock an already-started match).
audit: for locked reads that now have a local result, record outcome context,
       direction bucket, data readiness, and whether the stated tilt broadly aligned
       with the result. Then update state/scout_track_record.json — this is calibration
       memory, not a claim of market edge.

Offline, append-only, gitignored. Never modifies a lock. Never feeds result into a call.
"""
from __future__ import annotations

import json
import hashlib
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


def digest_read(call):
    blob = json.dumps(call, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


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
                                 "prematch_read_digest": digest_read(c),
                                 "call": c, "market": (ko.get(fid) or {}).get("mkt")}, ensure_ascii=False) + "\n")
            added += 1
    print(f"scout lock: +{added} (refused hindsight={hindsight})")


def _outcome(h, a):
    return "主" if h > a else ("客" if a > h else "平")


def _read_text(call):
    read = call.get("read") if isinstance(call, dict) else None
    if isinstance(read, dict):
        return " ".join(str(read.get(k) or "") for k in ("tilt_cn", "score_band_cn", "vs_market_cn"))
    legacy = call.get("call") if isinstance(call, dict) else None
    if isinstance(legacy, dict):
        return str(legacy.get("outcome_lean") or "")
    return ""


def _direction_bucket(call):
    text = _read_text(call)
    if any(token in text for token in ("明显", "大优", "强势", "压倒")):
        return "明显占优"
    if any(token in text for token in ("小优", "略优", "稍占优", "不败")):
        return "小优"
    if any(token in text for token in ("势均", "均衡", "五五", "胶着")):
        return "势均"
    return "未分档"


def _tilt_side(call):
    text = _read_text(call)
    if any(token in text for token in ("主队", "主胜", "主场", "home", "主")):
        return "主"
    if any(token in text for token in ("客队", "客胜", "away", "客")):
        return "客"
    if any(token in text for token in ("平局", "势均", "均衡", "五五", "平")):
        return "平"
    return None


def _broadly_aligned(tilt, actual):
    if tilt is None:
        return None
    if tilt == "平":
        return actual == "平"
    return actual == tilt or actual == "平"


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
            tilt = _tilt_side(call)
            aligned = _broadly_aligned(tilt, actual)
            mkt = L.get("market") or {}
            mfav = "主" if (mkt.get("home_win") or 0) >= (mkt.get("away_win") or 0) else "客"
            fh.write(json.dumps({"fixture_id": fid, "actual": f"{sc['home']}-{sc['away']}",
                                 "actual_outcome": actual, "read_tilt_side": tilt,
                                 "direction_bucket": _direction_bucket(call),
                                 "data_readiness": call.get("data_readiness"),
                                 "broadly_aligned": aligned, "market_fav": mfav,
                                 "prematch_read_digest": L.get("prematch_read_digest") or digest_read(call),
                                 "audited_at_utc": now()}, ensure_ascii=False) + "\n")
            added += 1
    _update_track()
    print(f"scout audit: +{added}; track record updated")


def _update_track():
    if not AUDIT.is_file():
        return
    rows = [json.loads(l) for l in AUDIT.open(encoding="utf-8") if l.strip()]
    t = json.loads(TRACK.read_text(encoding="utf-8")) if TRACK.is_file() else {}
    ov = {"n": 0, "aligned": 0, "aligned_known": 0}
    byr = {}; byt = {}
    for r in rows:
        ov["n"] += 1
        if r.get("broadly_aligned") is not None:
            ov["aligned_known"] += 1
            ov["aligned"] += int(bool(r.get("broadly_aligned")))
        rd = r.get("data_readiness") or "unknown"; byr.setdefault(rd, {"n": 0, "aligned": 0, "aligned_known": 0})
        byr[rd]["n"] += 1
        if r.get("broadly_aligned") is not None:
            byr[rd]["aligned_known"] += 1; byr[rd]["aligned"] += int(bool(r.get("broadly_aligned")))
        b = r.get("direction_bucket") or "未分档"; byt.setdefault(b, {"n": 0, "aligned": 0, "aligned_known": 0})
        byt[b]["n"] += 1
        if r.get("broadly_aligned") is not None:
            byt[b]["aligned_known"] += 1; byt[b]["aligned"] += int(bool(r.get("broadly_aligned")))
    t["overall"] = {"n": ov["n"], "aligned": ov["aligned"], "aligned_known": ov["aligned_known"],
                    "alignment_rate": round(ov["aligned"] / ov["aligned_known"], 3) if ov["aligned_known"] else None}
    t["by_readiness"] = byr; t["by_tilt_bucket"] = byt; t["updated_at"] = now()
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
