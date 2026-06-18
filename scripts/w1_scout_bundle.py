#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 Scout — assemble per-match pre-match data bundles (local bootstrap).

Reads ONLY pre-match local data (dashboard market read + lineup/formation status +
match-card context status) and emits a scout_bundle per match. Real factor fields
(form / rolling xG / h2h / standings values / rest days) are marked `missing` until
the user's api-football pipeline fetches them — we never fabricate values.

Leakage-safe: never reads actual_score / any post-match statistic. Output gitignored.
The user's pipeline may overwrite/augment data/scout/<fixture>.json with richer fetched
data; this bootstrap just guarantees a valid, honest bundle exists for every match.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
SCOPE_JSON = ROOT / "config/w1_competition_scope.json"
LEGACY_CARDS = ROOT / "data/processed/match_cards/group_stage_round1"
SCOUT_DIR = ROOT / "data/scout"   # user pipeline may drop richer bundles here
ODDS_RAW = ROOT / "data/odds_snapshots/raw"
OUT = ROOT / "state/w1_scout_bundles.json"
POLICY = ROOT / "config/w1_scout_policy.json"


def _root_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def _card_dirs() -> list[Path]:
    dirs: list[Path] = []
    if SCOPE_JSON.is_file():
        scope = json.loads(SCOPE_JSON.read_text(encoding="utf-8"))
        dirs.extend(_root_path(path) for path in scope.get("card_dirs", []) or [])
    if LEGACY_CARDS not in dirs:
        dirs.append(LEGACY_CARDS)
    return dirs


def _card_paths() -> list[Path]:
    out: list[Path] = []
    for directory in _card_dirs():
        if directory.is_dir():
            out.extend(sorted(directory.glob("*.json")))
    return out


def _default_league() -> tuple[str, int | None]:
    if POLICY.is_file():
        leagues = json.loads(POLICY.read_text(encoding="utf-8")).get("leagues") or []
        if leagues:
            row = leagues[0]
            return str(row.get("name") or "FIFA World Cup"), row.get("season")
    return "FIFA World Cup", 2026


def _card_context(fid: str) -> dict:
    for p in _card_paths():
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        mid = str(c.get("match", {}).get("match_id", ""))
        if mid.endswith(fid):
            return c.get("context", {}) or {}
    return {}


def _avail(v) -> str:
    return "available" if v not in (None, "", [], {}) else "missing"


def _as_float(value) -> float | None:
    if value in (None, "", [], {}):
        return None
    try:
        return float(str(value).replace("+", ""))
    except (TypeError, ValueError):
        return None


def _line_sort_key(line: str | None, count: int) -> tuple[int, float, float]:
    number = _as_float(line)
    if number is None:
        number = 99.0
    preferred_distance = abs(abs(number) - 1.0)
    return (-count, preferred_distance, abs(number))


def _latest_odds_rows(fid: str) -> list[dict]:
    if not ODDS_RAW.is_dir():
        return []
    matched: list[dict] = []
    for path in sorted(ODDS_RAW.glob("*/*.jsonl")):
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
            if row.get("stale") is True or row.get("suspended") is True:
                continue
            matched.append(row)
    if not matched:
        return []
    latest = max(str(row.get("captured_at_utc") or "") for row in matched)
    return [row for row in matched if str(row.get("captured_at_utc") or "") == latest]


def _median_or_none(values: list[float]) -> float | None:
    values = [value for value in values if value is not None]
    if not values:
        return None
    return round(float(median(values)), 3)


def _collect_line_pair(rows: list[dict], market: str) -> dict:
    by_line: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row.get("market") != market:
            continue
        raw = row.get("raw_odds") or {}
        label = str(raw.get("label") or "")
        price = _as_float(raw.get("odds"))
        line = str(row.get("line") or "").strip()
        if not line or price is None:
            continue
        label_lower = label.lower()
        if market == "AH":
            if label_lower.startswith("home"):
                by_line[line]["home"].append(price)
            elif label_lower.startswith("away"):
                by_line[line]["away"].append(price)
        elif market == "OU":
            if label_lower.startswith("over"):
                by_line[line]["over"].append(price)
            elif label_lower.startswith("under"):
                by_line[line]["under"].append(price)
    complete = []
    for line, sides in by_line.items():
        if market == "AH" and sides.get("home") and sides.get("away"):
            complete.append((line, len(sides["home"]) + len(sides["away"]), sides))
        if market == "OU" and sides.get("over") and sides.get("under"):
            complete.append((line, len(sides["over"]) + len(sides["under"]), sides))
    if not complete:
        return {}
    line, _count, sides = sorted(complete, key=lambda item: _line_sort_key(item[0], item[1]))[0]
    if market == "AH":
        return {
            "ah_line": line,
            "ah_home_price": _median_or_none(sides["home"]),
            "ah_away_price": _median_or_none(sides["away"]),
        }
    return {
        "ou_line": line,
        "over_price": _median_or_none(sides["over"]),
        "under_price": _median_or_none(sides["under"]),
    }


def _odds_snapshot_market(fid: str) -> dict:
    rows = _latest_odds_rows(fid)
    if not rows:
        return {}
    out: dict = {}
    out.update(_collect_line_pair(rows, "AH"))
    out.update(_collect_line_pair(rows, "OU"))
    market_counts: list[int] = []
    bookmakers = {str(row.get("bookmaker") or "") for row in rows if row.get("bookmaker")}
    for row in rows:
        counts = row.get("book_count_by_market") or {}
        for key in ("1X2", "AH", "OU"):
            value = counts.get(key)
            if isinstance(value, int):
                market_counts.append(value)
    out["bookmaker_count"] = max(market_counts) if market_counts else len(bookmakers) or None
    out["market_source"] = "api-football odds snapshots"
    out["odds_updated_at"] = max(str(row.get("captured_at_utc") or "") for row in rows) or None
    return {key: value for key, value in out.items() if value not in (None, "", [], {})}


def _market_availability(market: dict) -> dict:
    has_1x2 = all(isinstance(market.get(key), (int, float)) for key in ("p_home", "p_draw", "p_away"))
    has_ah = market.get("ah_line") not in (None, "") and all(
        isinstance(market.get(key), (int, float)) for key in ("ah_home_price", "ah_away_price")
    )
    has_ou = market.get("ou_line") not in (None, "") and all(
        isinstance(market.get(key), (int, float)) for key in ("over_price", "under_price")
    )
    if has_1x2 and has_ah and has_ou:
        overall = "available"
    elif has_1x2 or has_ah or has_ou:
        overall = "partial"
    else:
        overall = "missing"
    return {
        "market": overall,
        "market_1x2": "available" if has_1x2 else "missing",
        "market_ah": "available" if has_ah else "missing",
        "market_ou": "available" if has_ou else "missing",
    }


def _form_block(_ctx) -> dict:
    # recent_form is "not refreshed" locally -> honest missing until pipeline fetches
    return {"last5_wdl": None, "gf_avg": None, "ga_avg": None, "ppg": None,
            "home_away_split": None, "availability": "missing"}


def _xg_block() -> dict:
    return {"xg_for": None, "xg_against": None, "shots": None, "sot": None,
            "window_n": None, "availability": "missing"}


def build_bundle(rec: dict) -> dict:
    fid = str(rec.get("fixture_id"))
    ctx = _card_context(fid)
    oxt = (rec.get("market_probability_panel") or {}).get("one_x_two") or {}
    inj_status = (ctx.get("injuries") or {}).get("status")
    has_formation = bool(rec.get("home_formation") or rec.get("away_formation"))
    default_league, default_season = _default_league()
    market = {"p_home": oxt.get("home_win"), "p_draw": oxt.get("draw"),
              "p_away": oxt.get("away_win"), "ah_line": None, "ah_home_price": None,
              "ah_away_price": None, "ou_line": None, "over_price": None,
              "under_price": None, "bookmaker_count": None, "market_source": None,
              "odds_updated_at": None}
    market.update(_odds_snapshot_market(fid))

    bundle = {
        "schema_version": "W1_SCOUT_BUNDLE_V1",
        "fixture_id": fid,
        "kickoff_utc": rec.get("kickoff"),
        "home": rec.get("home_team_cn") or rec.get("match", "").split(" vs ")[0],
        "away": rec.get("away_team_cn") or "",
        "league": rec.get("league") or rec.get("competition") or default_league,
        "season": rec.get("season") or default_season,
        "asof_pre_kickoff": True, "fetched_at_utc": None,
        "market": market,
        "form_home": _form_block(ctx), "form_away": _form_block(ctx),
        "xg_roll_home": _xg_block(), "xg_roll_away": _xg_block(),
        "lineup": {"confirmed": bool(rec.get("confirmed_lineup_available")),
                   "formation_home": rec.get("home_formation"),
                   "formation_away": rec.get("away_formation"), "key_absences": []},
        "injuries_home": [], "injuries_away": [],
        "standings": {"rank_home": None, "rank_away": None, "pts_gap": None},
        "h2h": {"last_n": None, "home_wins": None, "draws": None, "away_wins": None},
        "rest_days": {"home": None, "away": None, "diff": None},
        "api_pred": None,
        "availability": {
            "form": "missing", "xg_roll": "missing",
            "lineup": "partial" if has_formation else ("partial" if rec.get("confirmed_lineup_available") is not None else "missing"),
            "injuries": "partial" if inj_status else "missing",
            "standings": "missing", "h2h": "missing", "rest_days": "missing",
        },
    }
    bundle["availability"].update(_market_availability(market))
    bundle["missing_fields"] = [k for k, v in bundle["availability"].items() if v == "missing"]
    return bundle


def _merge_user_bundle(fid: str, base: dict) -> dict:
    """If the user's pipeline dropped a richer bundle, prefer its fetched fields."""
    p = SCOUT_DIR / f"{fid}.json"
    if not p.is_file():
        return base
    try:
        rich = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return base
    # User-fetched non-null values win, but nested maps merge so fetched factors
    # cannot erase W1 base market availability/source fields.
    for k, v in rich.items():
        if v not in (None, "", [], {}):
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                merged = dict(base[k])
                merged.update({nk: nv for nk, nv in v.items() if nv not in (None, "", [], {})})
                base[k] = merged
            else:
                base[k] = v
    if isinstance(base.get("market"), dict):
        base.setdefault("availability", {}).update(_market_availability(base["market"]))
    base["missing_fields"] = [k for k, a in (base.get("availability") or {}).items() if a == "missing"]
    return base


def build_all() -> dict:
    recs = json.loads(DASH.read_text(encoding="utf-8")).get("match_records", []) if DASH.is_file() else []
    bundles = [_merge_user_bundle(str(r.get("fixture_id")), build_bundle(r)) for r in recs]
    return {"stage": "W1_SCOUT", "schema_version": "W1_SCOUT_BUNDLE_V1",
            "asof_pre_kickoff": True, "n": len(bundles), "bundles": bundles}


def main() -> int:
    payload = build_all()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    from collections import Counter
    cov = Counter()
    for b in payload["bundles"]:
        for k, v in b["availability"].items():
            if v != "missing":
                cov[k] += 1
    print(f"scout bundles: n={payload['n']} | 非missing维度覆盖: {dict(cov)} -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
