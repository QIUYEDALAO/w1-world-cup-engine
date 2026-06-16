#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1_OPPORTUNITY_SELECTOR_PHASE_A: read-only candidate unification.

Phase A deliberately does not rank a single selection, calibrate a new layer, or
alter the score engine. It only exposes several market-view candidates derived
from the same market-implied Dixon-Coles score matrix.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import w1_score_engine as W1ENGINE  # noqa: E402

BASIS = "market_implied_score_matrix"


def _prob(value: float | None) -> float | None:
    return round(float(value), 6) if value is not None else None


def _score(value: float | None) -> float | None:
    return round(float(value), 6) if value is not None else None


def _candidate(
    market: str,
    selection: str,
    raw_probability: float,
    expected_result_score: float | None,
    line: float | None = None,
    **extra: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "market": market,
        "selection": selection,
        "line": line,
        "raw_probability": _prob(raw_probability),
        "expected_result_score": _score(expected_result_score),
        "basis": BASIS,
        "independent_edge": False,
        "calibrated": False,
    }
    for key, value in extra.items():
        if value is not None:
            row[key] = value
    return row


def split_quarter_line(line: float) -> list[float]:
    doubled = line * 2
    if abs(doubled - round(doubled)) < 1e-9:
        return [float(line)]
    return [float(line) - 0.25, float(line) + 0.25]


def _settle_leg(diff: float) -> float:
    if diff > 1e-9:
        return 1.0
    if diff < -1e-9:
        return -1.0
    return 0.0


def _binary_side(matrix: Any, diff_fn: Any) -> dict[str, float]:
    win = push = lose = exp = 0.0
    for h in range(matrix.shape[0]):
        for a in range(matrix.shape[1]):
            p = float(matrix[h, a])
            score = _settle_leg(float(diff_fn(h, a)))
            exp += p * score
            if score > 0:
                win += p
            elif score < 0:
                lose += p
            else:
                push += p
    return {"win": win, "push": push, "lose": lose, "expected": exp}


def _avg_legs(rows: list[dict[str, float]]) -> dict[str, float]:
    n = float(len(rows) or 1)
    return {key: sum(row[key] for row in rows) / n for key in ("win", "push", "lose", "expected")}


def matrix_from_params(lambda_home: float, lambda_away: float, rho: float | None = None, max_goals: int | None = None) -> Any:
    kwargs: dict[str, Any] = {"rho": W1ENGINE.DEFAULT_RHO if rho is None else float(rho)}
    if max_goals is not None:
        kwargs["max_goals"] = int(max_goals)
    return W1ENGINE.score_matrix(float(lambda_home), float(lambda_away), **kwargs)


def matrix_from_dashboard_record(record: dict[str, Any]) -> Any | None:
    dist = record.get("score_distribution", {}) or {}
    model = dist.get("matrix_model", {}) or {}
    summary = record.get("score_matrix_summary", {}) or {}
    try:
        lh = float(model.get("lambda_home", summary.get("lambda_home")))
        la = float(model.get("lambda_away", summary.get("lambda_away")))
        rho = float(model.get("rho", summary.get("dixon_coles_rho", W1ENGINE.DEFAULT_RHO)))
        max_goals = int(model.get("max_goals", W1ENGINE.MAX_GOALS))
    except (TypeError, ValueError):
        return None
    return matrix_from_params(lh, la, rho=rho, max_goals=max_goals)


def candidate_1x2(matrix: Any) -> list[dict[str, Any]]:
    home = draw = away = 0.0
    for h in range(matrix.shape[0]):
        for a in range(matrix.shape[1]):
            p = float(matrix[h, a])
            if h > a:
                home += p
            elif h == a:
                draw += p
            else:
                away += p
    return [
        _candidate("1X2", "home_win", home, home),
        _candidate("1X2", "draw", draw, draw),
        _candidate("1X2", "away_win", away, away),
    ]


def candidate_ou(matrix: Any, lines: list[float] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in lines or [1.5, 2.5, 3.5]:
        over_legs = [_binary_side(matrix, lambda h, a, leg=leg: h + a - leg) for leg in split_quarter_line(float(line))]
        over = _avg_legs(over_legs)
        under = {"win": over["lose"], "push": over["push"], "lose": over["win"], "expected": -over["expected"]}
        rows.append(_candidate("OU", "over", over["win"], over["expected"], float(line), push_probability=_prob(over["push"])))
        rows.append(_candidate("OU", "under", under["win"], under["expected"], float(line), push_probability=_prob(under["push"])))
    return rows


def candidate_ah(matrix: Any, handicaps: list[float] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for hcap in handicaps or [-0.5, 0.0, 0.5]:
        home_legs = [_binary_side(matrix, lambda h, a, leg=leg: h - a + leg) for leg in split_quarter_line(float(hcap))]
        home = _avg_legs(home_legs)
        away = {"win": home["lose"], "push": home["push"], "lose": home["win"], "expected": -home["expected"]}
        rows.append(_candidate("AH", "home_cover", home["win"], home["expected"], float(hcap), push_probability=_prob(home["push"])))
        rows.append(_candidate("AH", "away_cover", away["win"], away["expected"], float(-hcap), push_probability=_prob(away["push"])))
    return rows


def candidate_btts(matrix: Any) -> list[dict[str, Any]]:
    yes = 0.0
    for h in range(matrix.shape[0]):
        for a in range(matrix.shape[1]):
            if h > 0 and a > 0:
                yes += float(matrix[h, a])
    no = max(0.0, 1.0 - yes)
    return [
        _candidate("BTTS", "yes", yes, yes),
        _candidate("BTTS", "no", no, no),
    ]


def candidate_score_pool(score_distribution: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in (score_distribution or {}).get("score_pool", [])[:8]:
        p = item.get("probability", item.get("weight"))
        if p is None or not item.get("score"):
            continue
        rows.append(_candidate("score_pool", str(item["score"]), float(p), float(p)))
    return rows


def _line_numbers_from_card(card: dict[str, Any], market_key: str, pattern: str) -> list[float]:
    out: set[float] = set()
    markets = card.get("markets", {}) if isinstance(card, dict) else {}
    for item in markets.get(market_key, []) or []:
        text = str(item.get("line") or item.get("selection") or "") if isinstance(item, dict) else str(item)
        match = re.search(pattern, text, re.I)
        if match:
            out.add(float(match.group(1)))
    return sorted(out)


def ou_lines_from_card(card: dict[str, Any]) -> list[float]:
    return _line_numbers_from_card(card, "odds_OU", r"(?:Over|Under)\s*([0-9]+(?:\.[0-9]+)?)") or [1.5, 2.5, 3.5]


def ah_lines_from_card(card: dict[str, Any]) -> list[float]:
    out: set[float] = set()
    markets = card.get("markets", {}) if isinstance(card, dict) else {}
    for item in markets.get("odds_AH", []) or []:
        text = str(item.get("line") or item.get("selection") or "") if isinstance(item, dict) else str(item)
        match = re.search(r"(Home|Away)\s*([+-]?[0-9]+(?:\.[0-9]+)?)", text, re.I)
        if not match:
            continue
        value = float(match.group(2))
        out.add(value if match.group(1).lower() == "home" else -value)
    return sorted(out) or [-0.5, 0.0, 0.5]


def build_candidates(
    *,
    matrix: Any | None = None,
    card: dict[str, Any] | None = None,
    score_distribution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if matrix is None:
        return {
            "schema_version": "W1_OPPORTUNITY_SELECTOR_PHASE_A",
            "status": "skipped",
            "skip_reason": "score_matrix_unavailable",
            "basis": BASIS,
            "independent_edge": False,
            "calibrated": False,
            "items": [],
        }
    items = []
    items.extend(candidate_1x2(matrix))
    items.extend(candidate_ou(matrix, ou_lines_from_card(card or {})))
    items.extend(candidate_ah(matrix, ah_lines_from_card(card or {})))
    items.extend(candidate_btts(matrix))
    items.extend(candidate_score_pool(score_distribution or {}))
    return {
        "schema_version": "W1_OPPORTUNITY_SELECTOR_PHASE_A",
        "status": "ready",
        "basis": BASIS,
        "independent_edge": False,
        "calibrated": False,
        "items": items,
        "notes_cn": [
            "候选项均来自同一市场隐含比分矩阵。",
            "阶段A不做校准、不做单一主推、不声明独立优势。",
        ],
    }


def validate_candidates(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("basis") != BASIS:
        errors.append("payload basis mismatch")
    if payload.get("independent_edge") is not False or payload.get("calibrated") is not False:
        errors.append("payload must keep independent_edge=false and calibrated=false")
    for idx, item in enumerate(payload.get("items", [])):
        for key in ("market", "selection", "raw_probability", "basis", "independent_edge", "calibrated"):
            if key not in item:
                errors.append(f"item {idx} missing {key}")
        if item.get("basis") != BASIS:
            errors.append(f"item {idx} basis mismatch")
        if item.get("independent_edge") is not False or item.get("calibrated") is not False:
            errors.append(f"item {idx} must keep flags false")
        p = item.get("raw_probability")
        if not isinstance(p, (int, float)) or not (0.0 <= float(p) <= 1.0):
            errors.append(f"item {idx} raw_probability out of range")
    return errors
