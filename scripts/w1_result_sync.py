#!/usr/bin/env python3
"""Batch sync finished fixture results into the W1 results overlay.

This is post-match only. It never mutates match cards, Scout bundles, Scout
locks, score engine code, lambda/probability settings, or pre-match reads.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from w1_scout_fetch_api_football import ApiFootball, load_api_key, response_rows


ROOT = Path(__file__).resolve().parents[1]
SCOPE_JSON = ROOT / "config/w1_competition_scope.json"
FINISHED_STATUS_SHORT = {"FT", "AET", "PEN"}


def warn(message: str) -> None:
    print(f"WARN: {message}")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def root_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def competition_scope() -> dict[str, Any]:
    if not SCOPE_JSON.is_file():
        raise FileNotFoundError(f"missing competition scope: {SCOPE_JSON.relative_to(ROOT)}")
    return read_json(SCOPE_JSON)


def parse_utc(value: Any) -> datetime | None:
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


def fixture_id_from_card(card: dict[str, Any]) -> str:
    return str(card.get("match", {}).get("match_id") or "").split(":")[-1]


def configured_cards(scope: dict[str, Any]) -> list[tuple[Path, dict[str, Any]]]:
    cards: list[tuple[Path, dict[str, Any]]] = []
    for raw_dir in scope.get("card_dirs", []) or []:
        directory = root_path(raw_dir)
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            cards.append((path, read_json(path)))
    return cards


def due_for_result_sync(card: dict[str, Any], now: datetime) -> bool:
    kickoff = parse_utc(card.get("match", {}).get("kickoff_utc"))
    return bool(kickoff and now >= kickoff + timedelta(hours=2))


def load_overlay(path: Path) -> dict[str, Any]:
    if path.is_file():
        payload = read_json(path)
        payload.setdefault("results", {})
        return payload
    return {
        "schema_version": "W1_WORLD_CUP_2026_RESULTS_OVERLAY_V1",
        "updated_at_utc": None,
        "results": {},
    }


def finished_score(row: dict[str, Any]) -> tuple[dict[str, int], str] | None:
    status = ((row.get("fixture") or {}).get("status") or {}).get("short")
    if status not in FINISHED_STATUS_SHORT:
        return None
    goals = row.get("goals") or {}
    home = goals.get("home")
    away = goals.get("away")
    if home is None or away is None:
        fulltime = ((row.get("score") or {}).get("fulltime") or {})
        home = fulltime.get("home")
        away = fulltime.get("away")
    if home is None or away is None:
        return None
    return {"home": int(home), "away": int(away)}, str(status)


def result_row(card: dict[str, Any], fixture_row: dict[str, Any], synced_at: str) -> dict[str, Any] | None:
    parsed = finished_score(fixture_row)
    if not parsed:
        return None
    score, status_short = parsed
    teams = card.get("teams", {})
    match = card.get("match", {})
    return {
        "status": "finished",
        "status_short": status_short,
        "actual_score": score,
        "home_team": teams.get("home", {}).get("name"),
        "away_team": teams.get("away", {}).get("name"),
        "kickoff_utc": match.get("kickoff_utc"),
        "result_source": "api_football_fixture_result",
        "result_note": "赛果已由后台批量 result sync 写入统一结果覆盖。",
        "result_synced_at_utc": synced_at,
        "used_in_pre_match_decision": False,
        "used_in_audit_review_calibration_only": True,
        "alias_fixture_ids": [],
    }


def sync_results(*, dry_run: bool) -> int:
    scope = competition_scope()
    overlay_path = root_path(scope["results_overlay"])
    cards = configured_cards(scope)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    due_cards = [(path, card) for path, card in cards if due_for_result_sync(card, now)]
    print(f"result_sync scope={scope.get('tournament')} cards={len(cards)} due={len(due_cards)} dry_run={str(dry_run).lower()}")
    if dry_run:
        print("result_sync dry-run: api_called_count=0 written_results=0")
        return 0

    key = load_api_key()
    if not key:
        warn("APIFOOTBALL_KEY unavailable; result sync skipped WARN_ONLY")
        return 0

    api = ApiFootball(key)
    overlay = load_overlay(overlay_path)
    changed = 0
    for _path, card in due_cards:
        fid = fixture_id_from_card(card)
        if not fid:
            warn("match card without fixture id skipped")
            continue
        try:
            rows = response_rows(api.get("/fixtures", id=fid))
        except Exception as exc:  # noqa: BLE001 - WARN_ONLY operational sync
            warn(f"fixture {fid} API lookup failed WARN_ONLY: {exc}")
            continue
        if not rows:
            warn(f"fixture {fid} API returned no row WARN_ONLY")
            continue
        row = result_row(card, rows[0], now.isoformat().replace("+00:00", "Z"))
        if row is None:
            status = (((rows[0].get("fixture") or {}).get("status") or {}).get("short")) or "UNKNOWN"
            warn(f"fixture {fid} not finished/status unavailable ({status}) WARN_ONLY")
            continue
        old = overlay.setdefault("results", {}).get(fid)
        if old != row:
            overlay["results"][fid] = row
            changed += 1
    if changed:
        overlay["updated_at_utc"] = now.isoformat().replace("+00:00", "Z")
        write_json(overlay_path, overlay)
    print(f"result_sync api_called_count={len(due_cards)} written_results={changed} overlay={overlay_path.relative_to(ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        return sync_results(dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001 - bad local config should be visible
        print(f"FAIL: result sync local configuration error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
