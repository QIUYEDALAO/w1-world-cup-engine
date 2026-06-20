#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read and standardize W1 raw odds snapshots for policy-time analysis.

Runtime raw data stays under data/odds_snapshots/raw. This module only reads and
normalizes it; it never rewrites raw snapshots or derives model probabilities.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data/odds_snapshots/raw"

PHASE_TO_STAGE = {
    "T-48H": "early_48h",
    "T-48": "early_48h",
    "T-24H": "early_24h",
    "T-24": "early_24h",
    "T-12H": "watch_12h",
    "T-12": "watch_12h",
    "T-6H": "watch_6h",
    "T-6": "watch_6h",
    "T-2H": "watch_2h",
    "T-2": "watch_2h",
    "T-1H": "official_1h",
    "T-1": "official_1h",
    "T-30M": "final_30m",
    "CLOSING": "final_30m",
}


def _num(value: Any) -> float | None:
    if value in (None, "", [], {}):
        return None
    try:
        out = float(str(value).replace("+", ""))
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _stage_id(row: dict[str, Any]) -> str:
    phase = str(row.get("phase") or "").strip().upper()
    return PHASE_TO_STAGE.get(phase, "unknown")


def _side_from_label(label: Any) -> str | None:
    low = str(label or "").strip().lower()
    if low.startswith("home"):
        return "home"
    if low.startswith("away"):
        return "away"
    return None


def _target_line(bundle: dict[str, Any] | None) -> float | None:
    if not isinstance(bundle, dict):
        return None
    market = bundle.get("market") if isinstance(bundle.get("market"), dict) else {}
    ah = market.get("ah") if isinstance(market.get("ah"), dict) else {}
    return _num(ah.get("home_handicap", market.get("ah_line")))


def _book_count(row: dict[str, Any], market: str = "AH") -> int:
    counts = row.get("book_count_by_market") if isinstance(row.get("book_count_by_market"), dict) else {}
    value = counts.get(market)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _raw_rows(fid: str) -> tuple[list[dict[str, Any]], set[str]]:
    rows: list[dict[str, Any]] = []
    sources: set[str] = set()
    if not RAW_ROOT.is_dir():
        return rows, sources
    for path in sorted(RAW_ROOT.glob("*/*.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if fid not in line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ids = {str(row.get("fixture_id") or ""), str(row.get("local_card_id") or "")}
            ids.update(str(item) for item in (row.get("alias_fixture_ids") or []))
            if fid not in ids:
                continue
            rows.append(row)
            sources.add(str(path.relative_to(ROOT)))
    return rows, sources


def _bundle_snapshots(fid: str, bundle: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(bundle, dict):
        return []
    rows = bundle.get("odds_snapshots")
    if not isinstance(rows, list):
        rows = (bundle.get("market") or {}).get("odds_snapshots") if isinstance(bundle.get("market"), dict) else []
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if row.get("fixture_id") and str(row.get("fixture_id")) != str(fid):
            continue
        dt = _parse_dt(row.get("captured_at") or row.get("captured_at_utc"))
        out.append({
            "fixture_id": str(fid),
            "stage_id": str(row.get("stage_id") or "unknown"),
            "captured_at": dt.isoformat().replace("+00:00", "Z") if dt else str(row.get("captured_at") or row.get("captured_at_utc") or ""),
            "_dt": dt,
            "home_team": row.get("home_team"),
            "away_team": row.get("away_team"),
            "home_handicap": _num(row.get("home_handicap")),
            "away_handicap": _num(row.get("away_handicap")),
            "home_price": _num(row.get("home_price")),
            "away_price": _num(row.get("away_price")),
            "bookmaker_count": int(row.get("bookmaker_count") or 0),
            "source": str(row.get("source") or "bundle"),
        })
    return out


def fixture_snapshots(fid: str, bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return standardized AH snapshots and source metadata for one fixture."""
    embedded = _bundle_snapshots(fid, bundle)
    if embedded:
        snapshots = sorted(embedded, key=lambda row: row.get("_dt") or datetime.min.replace(tzinfo=timezone.utc))
        for row in snapshots:
            row.pop("_dt", None)
        return {
            "snapshots": snapshots,
            "raw_count": len(snapshots),
            "source": "bundle",
        }

    raw_rows, sources = _raw_rows(str(fid))
    target = _target_line(bundle)
    groups: dict[str, dict[float, dict[str, Any]]] = {}
    meta: dict[str, dict[str, Any]] = {}
    raw_ah_count = 0
    for row in raw_rows:
        if row.get("market") != "AH":
            continue
        if row.get("suspended") or row.get("stale") or row.get("live"):
            continue
        raw_ah_count += 1
        captured = str(row.get("captured_at_utc") or row.get("captured_at") or "")
        if not captured:
            continue
        line = _num(row.get("line"))
        odds = _num((row.get("raw_odds") or {}).get("odds"))
        side = _side_from_label((row.get("raw_odds") or {}).get("label"))
        if line is None or odds is None or side not in {"home", "away"}:
            continue
        line_bucket = groups.setdefault(captured, {}).setdefault(line, {"home": [], "away": [], "bookmakers": set()})
        line_bucket[side].append(odds)
        if row.get("bookmaker"):
            line_bucket["bookmakers"].add(str(row.get("bookmaker")))
        meta[captured] = {
            "fixture_id": str(row.get("fixture_id") or fid),
            "stage_id": _stage_id(row),
            "captured_at": captured,
            "home_team": None,
            "away_team": None,
            "bookmaker_count_hint": _book_count(row, "AH"),
            "source": str(row.get("source") or "football_api"),
        }

    snapshots: list[dict[str, Any]] = []
    for captured, lines in groups.items():
        complete = []
        for line, sides in lines.items():
            if sides.get("home") and sides.get("away"):
                count = min(len(sides["home"]), len(sides["away"]))
                target_distance = abs(line - target) if target is not None else abs(abs(line) - 0.5)
                complete.append((target_distance, -count, abs(line), line, sides))
        if not complete:
            continue
        _, _, _, line, sides = sorted(complete)[0]
        m = meta.get(captured, {})
        dt = _parse_dt(captured)
        bookmaker_count = min(len(sides["home"]), len(sides["away"])) or int(m.get("bookmaker_count_hint") or 0)
        snapshots.append({
            "fixture_id": str(fid),
            "stage_id": str(m.get("stage_id") or "unknown"),
            "captured_at": dt.isoformat().replace("+00:00", "Z") if dt else captured,
            "_dt": dt,
            "home_team": m.get("home_team"),
            "away_team": m.get("away_team"),
            "home_handicap": round(float(line), 3),
            "away_handicap": round(float(-line), 3),
            "home_price": round(float(median(sides["home"])), 3),
            "away_price": round(float(median(sides["away"])), 3),
            "bookmaker_count": bookmaker_count,
            "source": m.get("source") or "football_api",
        })
    snapshots.sort(key=lambda row: row.get("_dt") or datetime.min.replace(tzinfo=timezone.utc))
    for row in snapshots:
        row.pop("_dt", None)
    if not snapshots and isinstance(bundle, dict):
        market = bundle.get("market") if isinstance(bundle.get("market"), dict) else {}
        ah = market.get("ah") if isinstance(market.get("ah"), dict) else {}
        home_handicap = _num(ah.get("home_handicap", market.get("ah_line")))
        away_handicap = _num(ah.get("away_handicap"))
        if away_handicap is None and home_handicap is not None:
            away_handicap = -home_handicap
        home_price = _num(ah.get("home_price", market.get("ah_home_price")))
        away_price = _num(ah.get("away_price", market.get("ah_away_price")))
        captured_at = ah.get("odds_updated_at") or market.get("odds_updated_at")
        if home_handicap is not None and away_handicap is not None and home_price is not None and away_price is not None:
            dt = _parse_dt(captured_at)
            snapshots.append({
                "fixture_id": str(fid),
                "stage_id": "current_overlay",
                "captured_at": dt.isoformat().replace("+00:00", "Z") if dt else str(captured_at or ""),
                "home_team": bundle.get("home"),
                "away_team": bundle.get("away"),
                "home_handicap": round(float(home_handicap), 3),
                "away_handicap": round(float(away_handicap), 3),
                "home_price": round(float(home_price), 3),
                "away_price": round(float(away_price), 3),
                "bookmaker_count": int(ah.get("bookmaker_count") or market.get("bookmaker_count") or 0),
                "source": "data/scout_current_odds",
                "snapshot_type": "current_only",
            })
            return {
                "snapshots": snapshots,
                "raw_count": 1,
                "source": "data/scout_current_odds",
            }
    return {
        "snapshots": snapshots,
        "raw_count": raw_ah_count or len(raw_rows),
        "source": ",".join(sorted(sources)) if sources else "missing",
    }


def summarize_fixture(fid: str, bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = fixture_snapshots(fid, bundle)
    snaps = payload.get("snapshots") or []
    return {
        "fixture_id": str(fid),
        "snapshots_count": int(payload.get("raw_count") or 0),
        "snapshots_source": payload.get("source") or "missing",
        "snapshots_used": len(snaps),
        "first_stage_id": snaps[0].get("stage_id") if snaps else None,
        "latest_stage_id": snaps[-1].get("stage_id") if snaps else None,
        "first_captured_at": snaps[0].get("captured_at") if snaps else None,
        "latest_captured_at": snaps[-1].get("captured_at") if snaps else None,
        "snapshots": snaps,
    }
