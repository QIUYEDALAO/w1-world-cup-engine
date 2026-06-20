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
from typing import Any

import w1_ah_cover as W1AH
import w1_recommendation_policy as W1REC

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
SCOPE_JSON = ROOT / "config/w1_competition_scope.json"
LEGACY_CARDS = ROOT / "data/processed/match_cards/group_stage_round1"
SCOUT_DIR = ROOT / "data/scout"   # user pipeline may drop richer bundles here
ODDS_RAW = ROOT / "data/odds_snapshots/raw"
OUT = ROOT / "state/w1_scout_bundles.json"
POLICY = ROOT / "config/w1_scout_policy.json"
RECOMMENDATION_POLICY = ROOT / "config/w1_recommendation_policy.json"


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
    out["odds_snapshots_count"] = len(rows)
    out["odds_snapshots_source"] = "data/odds_snapshots/raw"
    return {key: value for key, value in out.items() if value not in (None, "", [], {})}


def _market_availability(market: dict) -> dict:
    one_x_two = market.get("one_x_two") if isinstance(market.get("one_x_two"), dict) else {}
    ah = market.get("ah") if isinstance(market.get("ah"), dict) else {}
    ou = market.get("ou") if isinstance(market.get("ou"), dict) else {}
    has_1x2 = all(isinstance(market.get(key), (int, float)) for key in ("p_home", "p_draw", "p_away")) or all(
        isinstance(one_x_two.get(key), (int, float)) for key in ("p_home", "p_draw", "p_away")
    )
    has_model_1x2 = all(isinstance(market.get(key), (int, float)) for key in ("model_p_home", "model_p_draw", "model_p_away"))
    has_ah = market.get("ah_line") not in (None, "") and all(
        isinstance(market.get(key), (int, float)) for key in ("ah_home_price", "ah_away_price")
    ) or ah.get("home_handicap") not in (None, "") and all(
        isinstance(ah.get(key), (int, float)) for key in ("home_price", "away_price")
    )
    has_ou = market.get("ou_line") not in (None, "") and all(
        isinstance(market.get(key), (int, float)) for key in ("over_price", "under_price")
    ) or ou.get("line") not in (None, "") and all(
        isinstance(ou.get(key), (int, float)) for key in ("over_price", "under_price")
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
        "model_1x2": "available" if has_model_1x2 else "missing",
        "market_ah": "available" if has_ah else "missing",
        "market_ou": "available" if has_ou else "missing",
    }


def _sync_market_nested(market: dict) -> dict:
    one_x_two = dict(market.get("one_x_two") or {})
    if all(isinstance(market.get(key), (int, float)) for key in ("p_home", "p_draw", "p_away")):
        one_x_two.update({
            "p_home": market.get("p_home"),
            "p_draw": market.get("p_draw"),
            "p_away": market.get("p_away"),
            "source": one_x_two.get("source") or market.get("market_source") or "market",
        })
    market["one_x_two"] = {k: v for k, v in one_x_two.items() if v not in (None, "", [], {})}

    ah = dict(market.get("ah") or {})
    if market.get("ah_line") not in (None, ""):
        ah.setdefault("line", market.get("ah_line"))
        ah.setdefault("home_handicap", _as_float(market.get("ah_line")))
        if ah.get("home_handicap") is not None:
            ah.setdefault("away_handicap", -float(ah["home_handicap"]))
        ah.setdefault("home_price", market.get("ah_home_price"))
        ah.setdefault("away_price", market.get("ah_away_price"))
        ah.setdefault("bookmaker_count", market.get("bookmaker_count"))
        ah.setdefault("median_line", market.get("ah_line"))
        ah.setdefault("median_home_price", market.get("ah_home_price"))
        ah.setdefault("median_away_price", market.get("ah_away_price"))
        ah.setdefault("current_line", market.get("ah_line"))
        ah.setdefault("opening_line", market.get("ah_line"))
        ah.setdefault("line_movement", _movement_label(ah.get("current_line"), ah.get("opening_line")))
        ah.setdefault("water_movement", _water_label(ah.get("home_price"), ah.get("away_price"), ah.get("selected_side")))
        ah.setdefault("source", market.get("market_source") or "odds")
        ah.setdefault("odds_updated_at", market.get("odds_updated_at"))
        ah.setdefault("snapshots_count", market.get("odds_snapshots_count"))
        ah.setdefault("snapshots_source", market.get("odds_snapshots_source"))
    market["ah"] = {k: v for k, v in ah.items() if v not in (None, "", [], {})}

    ou = dict(market.get("ou") or {})
    if market.get("ou_line") not in (None, ""):
        ou.setdefault("line", market.get("ou_line"))
        ou.setdefault("over_price", market.get("over_price"))
        ou.setdefault("under_price", market.get("under_price"))
        ou.setdefault("current_line", market.get("ou_line"))
        ou.setdefault("opening_line", market.get("ou_line"))
        ou.setdefault("movement", _movement_label(ou.get("current_line"), ou.get("opening_line")))
        ou.setdefault("source", market.get("market_source") or "odds")
    market["ou"] = {k: v for k, v in ou.items() if v not in (None, "", [], {})}
    return market


def _attach_ah_cover_from_rec(market: dict, rec: dict) -> dict:
    ah = market.get("ah") if isinstance(market.get("ah"), dict) else {}
    line = ah.get("home_handicap", ah.get("line", market.get("ah_line")))
    if line in (None, ""):
        return market
    payload = _model_matrix_payload(rec)
    if not payload:
        return market
    home_price = ah.get("home_price", market.get("ah_home_price"))
    away_price = ah.get("away_price", market.get("ah_away_price"))
    try:
        matrix = W1AH.matrix_from_payload(payload)
        cover = W1AH.cover_from_matrix(matrix, float(line), _as_float(home_price), _as_float(away_price))
    except Exception:
        return market
    ah.update(cover)
    hp = _as_float(home_price)
    ap = _as_float(away_price)
    if hp and ap:
        ih = 1.0 / hp
        ia = 1.0 / ap
        total = ih + ia
        if total > 0:
            ah["home_market_cover_prob"] = round(ih / total, 4)
            ah["away_market_cover_prob"] = round(ia / total, 4)
    market_home = ah.get("home_market_cover_prob")
    market_away = ah.get("away_market_cover_prob")
    home_edge = None if not isinstance(market_home, (int, float)) else round(cover["home_cover_prob"] - float(market_home), 4)
    away_edge = None if not isinstance(market_away, (int, float)) else round(cover["away_cover_prob"] - float(market_away), 4)
    if away_edge is not None and (home_edge is None or away_edge >= home_edge):
        ah["selected_side"] = "away"
        ah["cover_probability_model"] = cover["away_cover_prob"]
        ah["cover_probability_market"] = market_away
        ah["cover_edge"] = away_edge
    elif home_edge is not None:
        ah["selected_side"] = "home"
        ah["cover_probability_model"] = cover["home_cover_prob"]
        ah["cover_probability_market"] = market_home
        ah["cover_edge"] = home_edge
    ah["water_movement"] = _water_label(ah.get("home_price"), ah.get("away_price"), ah.get("selected_side"))
    market["ah"] = {k: v for k, v in ah.items() if v not in (None, "", [], {})}
    return market


def _prob_triplet_from_rec(rec: dict) -> dict:
    panel = rec.get("market_probability_panel") or {}
    comparison = panel.get("market_comparison") or {}
    market_oxt = comparison.get("one_x_two_market") or {}
    model_oxt = panel.get("one_x_two") or {}
    summary = rec.get("score_matrix_summary") or {}
    distribution = rec.get("score_distribution") or {}
    model = distribution.get("matrix_model") or {}
    model_hda = model.get("model_hda") or []

    out = {
        "p_home": market_oxt.get("home_win"),
        "p_draw": market_oxt.get("draw"),
        "p_away": market_oxt.get("away_win"),
        "model_p_home": model_oxt.get("home_win"),
        "model_p_draw": model_oxt.get("draw"),
        "model_p_away": model_oxt.get("away_win"),
        "model_1x2_source": None,
    }
    if not all(isinstance(out.get(key), (int, float)) for key in ("model_p_home", "model_p_draw", "model_p_away")):
        out["model_p_home"] = summary.get("home_win_prob")
        out["model_p_draw"] = summary.get("draw_prob")
        out["model_p_away"] = summary.get("away_win_prob")
    if not all(isinstance(out.get(key), (int, float)) for key in ("model_p_home", "model_p_draw", "model_p_away")) and len(model_hda) >= 3:
        out["model_p_home"], out["model_p_draw"], out["model_p_away"] = model_hda[:3]
    if all(isinstance(out.get(key), (int, float)) for key in ("model_p_home", "model_p_draw", "model_p_away")):
        out["model_1x2_source"] = "W1模型"
    return out


def _price_from_prob(prob: Any) -> float | None:
    value = _as_float(prob)
    if not value or value <= 0:
        return None
    return round(1.0 / value, 3)


def _movement_label(current: Any, opening: Any) -> str | None:
    cur = _as_float(current)
    opn = _as_float(opening)
    if cur is None or opn is None:
        return None
    if abs(cur - opn) < 0.01:
        return "盘口基本稳定"
    return "升盘" if abs(cur) > abs(opn) else "退盘"


def _water_label(home_price: Any, away_price: Any, selected_side: str | None = None) -> str | None:
    hp = _as_float(home_price)
    ap = _as_float(away_price)
    if hp is None or ap is None:
        return None
    if abs(hp - ap) < 0.04:
        return "两侧水位接近"
    if selected_side == "home":
        return "主让方向低水" if hp < ap else "主让方向高水"
    if selected_side == "away":
        return "受让方向低水" if ap < hp else "受让方向高水"
    return "主队低水" if hp < ap else "客队低水"


def _model_matrix_payload(rec: dict) -> dict[str, Any] | None:
    model = ((rec.get("score_distribution") or {}).get("matrix_model") or {})
    if model.get("lambda_home") is None or model.get("lambda_away") is None:
        summary = rec.get("score_matrix_summary") or {}
        model = {
            "lambda_home": summary.get("lambda_home"),
            "lambda_away": summary.get("lambda_away"),
            "rho": summary.get("dixon_coles_rho"),
            "max_goals": 10,
        }
    if model.get("lambda_home") is None or model.get("lambda_away") is None:
        return None
    return model


def _panel_market_from_rec(rec: dict) -> dict:
    panel = rec.get("market_probability_panel") or {}
    comparison = panel.get("market_comparison") or {}
    movement = rec.get("odds_movement") or {}
    liquidity = movement.get("liquidity") or {}
    snapshot = {}
    for row in movement.get("snapshots") or []:
        if row.get("phase") == "LATEST":
            snapshot = row
            break
    out: dict[str, Any] = {}

    market_oxt = comparison.get("one_x_two_market") or {}
    oxt = {
        "home_odds": _price_from_prob(market_oxt.get("home_win")),
        "draw_odds": _price_from_prob(market_oxt.get("draw")),
        "away_odds": _price_from_prob(market_oxt.get("away_win")),
        "p_home": market_oxt.get("home_win"),
        "p_draw": market_oxt.get("draw"),
        "p_away": market_oxt.get("away_win"),
        "source": "market_comparison" if market_oxt else None,
    }

    ah_market = comparison.get("ah_main_market") or {}
    ah_default = panel.get("handicap_default") or {}
    home_handicap = ah_market.get("home_handicap", ah_default.get("home_handicap"))
    home_price = _price_from_prob(ah_market.get("home_cover"))
    away_price = _price_from_prob(ah_market.get("away_cover"))
    ah = {
        "line": home_handicap,
        "home_handicap": home_handicap,
        "away_handicap": -float(home_handicap) if home_handicap not in (None, "") else None,
        "home_price": home_price,
        "away_price": away_price,
        "selected_side": None,
        "bookmaker_count": liquidity.get("book_count_latest") or None,
        "median_line": home_handicap,
        "median_home_price": home_price,
        "median_away_price": away_price,
        "opening_line": ((snapshot.get("ah") or {}).get("main_line") if snapshot else None),
        "current_line": home_handicap,
        "line_movement": None,
        "water_movement": None,
        "odds_updated_at": snapshot.get("captured_at_utc") or None,
        "source": "market_probability_panel.ah_main_market" if home_handicap not in (None, "") else None,
    }
    if ah["opening_line"] is None:
        ah["opening_line"] = home_handicap
    ah["line_movement"] = _movement_label(ah["current_line"], ah["opening_line"])

    if home_handicap not in (None, ""):
        payload = _model_matrix_payload(rec)
        if payload:
            try:
                matrix = W1AH.matrix_from_payload(payload)
                cover = W1AH.cover_from_matrix(matrix, float(home_handicap), home_price, away_price)
                ah.update(cover)
                market_home = ah_market.get("home_cover")
                market_away = ah_market.get("away_cover")
                if isinstance(market_home, (int, float)):
                    ah["home_market_cover_prob"] = market_home
                if isinstance(market_away, (int, float)):
                    ah["away_market_cover_prob"] = market_away
                home_edge = None if not isinstance(market_home, (int, float)) else round(cover["home_cover_prob"] - float(market_home), 4)
                away_edge = None if not isinstance(market_away, (int, float)) else round(cover["away_cover_prob"] - float(market_away), 4)
                if away_edge is not None and (home_edge is None or away_edge >= home_edge):
                    ah["selected_side"] = "away"
                    ah["cover_probability_model"] = cover["away_cover_prob"]
                    ah["cover_probability_market"] = market_away
                    ah["cover_edge"] = away_edge
                elif home_edge is not None:
                    ah["selected_side"] = "home"
                    ah["cover_probability_model"] = cover["home_cover_prob"]
                    ah["cover_probability_market"] = market_home
                    ah["cover_edge"] = home_edge
            except Exception:
                pass
    ah["water_movement"] = _water_label(ah.get("home_price"), ah.get("away_price"), ah.get("selected_side"))

    ou_market = comparison.get("ou_2_5_market") or {}
    totals_default = panel.get("totals_default") or {}
    ou_line = totals_default.get("line")
    ou = {
        "line": ou_line,
        "over_price": _price_from_prob(ou_market.get("over")),
        "under_price": _price_from_prob(ou_market.get("under")),
        "opening_line": ((snapshot.get("ou") or {}).get("main_line") if snapshot else None) or ou_line,
        "current_line": ou_line,
        "movement": None,
        "source": "market_probability_panel.ou_2_5_market" if ou_line not in (None, "") else None,
    }
    ou["movement"] = _movement_label(ou["current_line"], ou["opening_line"])

    out["one_x_two"] = {k: v for k, v in oxt.items() if v not in (None, "", [], {})}
    out["ah"] = {k: v for k, v in ah.items() if v not in (None, "", [], {})}
    out["ou"] = {k: v for k, v in ou.items() if v not in (None, "", [], {})}
    if out["ah"]:
        out["ah_line"] = out["ah"].get("home_handicap")
        out["ah_home_price"] = out["ah"].get("home_price")
        out["ah_away_price"] = out["ah"].get("away_price")
    if out["ou"]:
        out["ou_line"] = out["ou"].get("line")
        out["over_price"] = out["ou"].get("over_price")
        out["under_price"] = out["ou"].get("under_price")
    if out["one_x_two"]:
        out["p_home"] = out["one_x_two"].get("p_home")
        out["p_draw"] = out["one_x_two"].get("p_draw")
        out["p_away"] = out["one_x_two"].get("p_away")
    if liquidity.get("book_count_latest") is not None:
        out["bookmaker_count"] = liquidity.get("book_count_latest")
    return out


def _score_picks_from_rec(rec: dict) -> list[dict]:
    rows = (rec.get("score_matrix_summary") or {}).get("top_scores") or (rec.get("score_distribution") or {}).get("top_scores") or []
    out = []
    for row in rows[:3]:
        score = row.get("score")
        probability = row.get("probability")
        if score:
            out.append({"score": score, "probability": probability, "source": "score matrix"})
    return out


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
    inj_status = (ctx.get("injuries") or {}).get("status")
    has_formation = bool(rec.get("home_formation") or rec.get("away_formation"))
    default_league, default_season = _default_league()
    market = {**_prob_triplet_from_rec(rec),
              "score_picks": _score_picks_from_rec(rec),
              "ah_line": None, "ah_home_price": None,
              "ah_away_price": None, "ou_line": None, "over_price": None,
              "under_price": None, "bookmaker_count": None, "market_source": None,
              "odds_updated_at": None, "odds_snapshots_count": None,
              "odds_snapshots_source": None, "one_x_two": {}, "ah": {}, "ou": {}}
    market.update(_panel_market_from_rec(rec))
    market.update(_odds_snapshot_market(fid))
    market = _sync_market_nested(market)
    market = _attach_ah_cover_from_rec(market, rec)

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


def _merge_nonempty(base: dict, rich: dict) -> dict:
    merged = dict(base)
    for key, value in rich.items():
        if value in (None, "", [], {}):
            continue
        if key == "availability" and value == "missing" and merged.get(key) in {"available", "partial"}:
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_nonempty(merged[key], value)
        else:
            merged[key] = value
    return merged


def _merge_user_bundle(fid: str, base: dict, rec: dict) -> dict:
    """If the user's pipeline dropped a richer bundle, prefer its fetched fields."""
    p = SCOUT_DIR / f"{fid}.json"
    if not p.is_file():
        return base
    try:
        rich = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return base
    # User-fetched non-null values win, but nested maps merge so fetched factors
    # cannot erase W1 base model probabilities / score-picks unless explicitly
    # replaced by richer pre-match data.
    for k, v in rich.items():
        if k in {"home", "away"}:
            # Keep canonical Chinese display names from dashboard/card universe.
            continue
        if v not in (None, "", [], {}):
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                base[k] = _merge_nonempty(base[k], v)
            else:
                base[k] = v
    if isinstance(base.get("market"), dict):
        base["market"] = _sync_market_nested(base["market"])
        base["market"] = _attach_ah_cover_from_rec(base["market"], rec)
        base.setdefault("availability", {}).update(_market_availability(base["market"]))
    if isinstance(rich.get("market"), dict) and isinstance((rich.get("market") or {}).get("availability"), dict):
        base.setdefault("availability", {}).update({
            key: value for key, value in (rich.get("market") or {}).get("availability", {}).items()
            if value in {"available", "partial", "missing"}
        })
        base.setdefault("availability", {}).update(_market_availability(base.get("market") or {}))
    base["missing_fields"] = [k for k, a in (base.get("availability") or {}).items() if a == "missing"]
    return base


def build_all() -> dict:
    recs = json.loads(DASH.read_text(encoding="utf-8")).get("match_records", []) if DASH.is_file() else []
    policy_config = W1REC.load_policy_config(RECOMMENDATION_POLICY)
    bundles = []
    for rec in recs:
        bundle = _merge_user_bundle(str(rec.get("fixture_id")), build_bundle(rec), rec)
        bundle["policy_result"] = W1REC.build_policy_result(bundle, policy_config)
        bundles.append(bundle)
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
