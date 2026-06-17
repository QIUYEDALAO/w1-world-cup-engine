#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 FiveDim Confidence Adjustment (Stage D) — SOFT signals only.

Per Stage C (W1_FIVEDIM_HISTORICAL_VALIDATION): the candidate factors carry no
independent edge over the market. So this layer NEVER changes any probability. It
reads FiveDim cards + market direction and emits only:
  market_vs_factor / confidence_grade / risk_flags / data_quality_note / explanation.

Hard guarantees: no probability/lambda field is ever produced; agreement with the
market never raises confidence; only divergence (caution flag) or missing factor
data (downgrade) move anything. Read-only, offline, not wired into production.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "config/w1_confidence_adjustment_policy.json").read_text(encoding="utf-8"))
CARDS = ROOT / "state/w1_fivedim_lite_cards.json"
OUT = ROOT / "state/w1_confidence_adjustment.json"


def _sign(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return 0
    return 1 if x > 1e-9 else -1 if x < -1e-9 else 0


def adjust(market_fav_side, factor_signals):
    """Pure soft-signal rule. market_fav_side in {'home','away',None}.
    factor_signals: {'available': bool, 'elo_diff':?, 'ppg_diff':?, 'gd_diff':?} (home-away).
    Returns dict WITHOUT any probability field."""
    out = {"market_vs_factor": None, "confidence_grade": "C_weak", "risk_flags": [],
           "data_quality_note": "", "explanation_cn": "", "independent_edge": False, "prob_unchanged": True}

    if market_fav_side is None:
        out.update(market_vs_factor="factor_missing", confidence_grade="D_insufficient",
                   data_quality_note="市场读数不可用", explanation_cn="市场概率不可用，无法形成研究读数。")
        return out

    if not factor_signals or not factor_signals.get("available"):
        out.update(market_vs_factor="insufficient", confidence_grade="C_weak",
                   data_quality_note="实力/战术维数据不足，独立支撑不足",
                   explanation_cn="市场读数可用；独立历史因子本地不足，不上调可信度，维持市场复述定位。")
        return out

    score = _sign(factor_signals.get("elo_diff")) + _sign(factor_signals.get("ppg_diff")) + _sign(factor_signals.get("gd_diff"))
    factor_side = "home" if score > 0 else "away" if score < 0 else "none"

    if factor_side == "none":
        out.update(market_vs_factor="insufficient", confidence_grade="C_weak",
                   data_quality_note="因子方向不明确",
                   explanation_cn="历史因子方向不明确，不调整可信度。")
    elif factor_side == market_fav_side:
        # Stage C: agreement carries no edge -> do NOT raise confidence.
        out.update(market_vs_factor="aligned", confidence_grade="C_weak",
                   data_quality_note="与市场方向一致（注：一致无独立增量，不加分）",
                   explanation_cn="历史因子与市场同向；按阶段C结论，一致不构成额外可信度，不上调。")
    else:
        out.update(market_vs_factor="divergent", confidence_grade="C_weak",
                   risk_flags=["RISK_MARKET_FACTOR_DIVERGENCE"],
                   data_quality_note="市场与历史因子背离（仅提示，不改概率）",
                   explanation_cn="市场偏向与历史因子方向背离，提示谨慎；不改变任何概率。")
    return out


def _market_fav(card):
    items = (((card.get("market_view") or {}).get("candidate_payload") or {}).get("items")) or []
    d = {it.get("selection"): it.get("raw_probability") for it in items if it.get("market") == "1X2"}
    ph, pa = d.get("home_win"), d.get("away_win")
    if ph is None or pa is None:
        return None
    return "home" if ph >= pa else "away"  # label only; no probability returned


def _factor_signals(card):
    flags = card.get("availability_flags") or {}
    # current WC cards: strength missing, tactical degraded -> not available
    # Current WC cards carry no numeric strength/tactical values (strength missing).
    # When a future stage ingests them, populate elo_diff/ppg_diff/gd_diff here.
    available = flags.get("strength_view") == "available"
    return {"available": available}


def build_all():
    data = json.loads(CARDS.read_text(encoding="utf-8")) if CARDS.is_file() else {"cards": []}
    rows = []
    for card in data.get("cards", []):
        meta = card.get("metadata") or {}
        adj = adjust(_market_fav(card), _factor_signals(card))
        rows.append({"fixture_id": meta.get("fixture_id"), "match": meta.get("match"), **adj})
    return {
        "stage": "W1_FIVEDIM_CONFIDENCE_ADJUSTMENT_D",
        "basis_stage_c": "W1_FIVEDIM_HISTORICAL_VALIDATION",
        "research_only": True, "production_wired": False, "prob_unchanged": True,
        "independent_edge_claimed": False,
        "n": len(rows), "adjustments": rows,
    }


def main() -> int:
    payload = build_all()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    from collections import Counter
    states = Counter(r["market_vs_factor"] for r in payload["adjustments"])
    print(f"confidence adjustment built: n={payload['n']} states={dict(states)} -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
