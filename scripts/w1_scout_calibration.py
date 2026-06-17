#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1_SCOUT season calibration.

Computes self-check metrics from immutable pre-match reads, audit rows, and
post-match reviews. This is calibration of wording/readiness, not evidence of an
edge over the market.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "state/scout_lock.jsonl"
AUDIT = ROOT / "state/scout_audit.jsonl"
REVIEWS = ROOT / "state/scout_reviews.jsonl"
OUT = ROOT / "state/scout_calibration.json"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def available_dims(call: dict[str, Any]) -> int:
    readiness = call.get("data_readiness")
    if readiness == "高":
        return 5
    if readiness == "中":
        return 3
    if readiness == "低":
        return 1
    return 0


def main() -> int:
    locks = read_jsonl(LOCK)
    audits = read_jsonl(AUDIT)
    reviews = read_jsonl(REVIEWS)

    by_bucket: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "aligned": 0, "known": 0})
    for row in audits:
        bucket = row.get("direction_bucket") or "未分档"
        by_bucket[bucket]["n"] += 1
        if row.get("broadly_aligned") is not None:
            by_bucket[bucket]["known"] += 1
            by_bucket[bucket]["aligned"] += int(bool(row.get("broadly_aligned")))

    direction_calibration = {}
    for bucket, stats in by_bucket.items():
        known = stats["known"]
        direction_calibration[bucket] = {
            "n": stats["n"],
            "aligned": stats["aligned"],
            "aligned_rate": round(stats["aligned"] / known, 3) if known else None,
        }

    readiness_values = [available_dims((lock.get("call") or {})) for lock in locks]
    reviewed_ids = {str(row.get("fixture_id")) for row in reviews}
    finished_ids = {str(row.get("fixture_id")) for row in audits}
    payload = {
        "schema_version": "W1_SCOUT_CALIBRATION_V1",
        "updated_at_utc": now(),
        "locked_count": len(locks),
        "audited_count": len(audits),
        "reviewed_count": len(reviews),
        "review_coverage_rate": round(len(reviewed_ids & finished_ids) / len(finished_ids), 3) if finished_ids else None,
        "avg_readiness_dims": round(sum(readiness_values) / len(readiness_values), 3) if readiness_values else None,
        "direction_calibration": direction_calibration,
        "note_cn": "这是 Scout 解读的自我体检与校准,不是战胜市场的证据。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"scout calibration PASS: locked={len(locks)} audited={len(audits)} reviewed={len(reviews)} -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
