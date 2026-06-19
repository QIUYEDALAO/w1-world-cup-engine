#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Asian handicap cover probabilities from an existing score matrix.

This helper is display/research only. It does not change W1 lambda, rho, score
matrix construction, or any production decision policy. It only settles a given
handicap line against a supplied matrix or against already-built matrix params.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import w1_score_engine as W1ENGINE


def split_quarter_line(line: float) -> list[float]:
    doubled = round(line * 2) / 2
    if abs(line - doubled) < 1e-9:
        return [doubled]
    lower = int(line * 2) / 2
    upper = lower + 0.5
    return [lower, upper]


def settle_side(matrix: Any, home_handicap: float, side: str) -> dict[str, float]:
    """Return win/push/lose style probabilities for one AH side.

    side is "home" for home handicap, "away" for the opposite away handicap.
    Quarter lines are represented as half-push mass in push_prob; this keeps the
    output compact while preserving half-win / half-loss settlement mass.
    """
    legs = split_quarter_line(home_handicap)
    win = push = lose = half_win = half_loss = 0.0
    for leg in legs:
        leg_win = leg_push = leg_lose = 0.0
        for h in range(matrix.shape[0]):
            for a in range(matrix.shape[1]):
                p = float(matrix[h, a])
                margin = h - a + leg if side == "home" else a - h - leg
                if margin > 0:
                    leg_win += p
                elif margin == 0:
                    leg_push += p
                else:
                    leg_lose += p
        if len(legs) == 1:
            win += leg_win
            push += leg_push
            lose += leg_lose
        else:
            win += leg_win / 2
            push += leg_push / 2
            lose += leg_lose / 2
            half_win += leg_push / 2
            half_loss += leg_push / 2
    return {
        "win_prob": round(win, 4),
        "push_prob": round(push, 4),
        "lose_prob": round(lose, 4),
        "half_win_prob": round(half_win, 4),
        "half_loss_prob": round(half_loss, 4),
    }


def ev_proxy(win_prob: float, push_prob: float, price: float | None) -> float | None:
    if not price:
        return None
    # Push mass is neutral; this is a rough read, not a staking recommendation.
    return round(win_prob * (price - 1.0) - (1.0 - win_prob - push_prob), 4)


def cover_from_matrix(matrix: Any, home_handicap: float, home_price: float | None = None, away_price: float | None = None) -> dict[str, Any]:
    home = settle_side(matrix, home_handicap, "home")
    away = settle_side(matrix, home_handicap, "away")
    return {
        "home_handicap": home_handicap,
        "away_handicap": -home_handicap,
        "home_cover_prob": home["win_prob"],
        "away_cover_prob": away["win_prob"],
        "push_prob": round(max(home["push_prob"], away["push_prob"]), 4),
        "home_half_win_prob": home["half_win_prob"],
        "home_half_loss_prob": home["half_loss_prob"],
        "away_half_win_prob": away["half_win_prob"],
        "away_half_loss_prob": away["half_loss_prob"],
        "home_ev_proxy": ev_proxy(home["win_prob"], home["push_prob"], home_price),
        "away_ev_proxy": ev_proxy(away["win_prob"], away["push_prob"], away_price),
    }


def matrix_from_payload(payload: dict[str, Any]) -> Any:
    model = payload.get("matrix_model") or payload.get("score_distribution", {}).get("matrix_model") or payload
    lh = model.get("lambda_home")
    la = model.get("lambda_away")
    rho = model.get("rho", W1ENGINE.DEFAULT_RHO)
    max_goals = int(model.get("max_goals") or W1ENGINE.MAX_GOALS)
    if lh is None or la is None:
        raise ValueError("payload missing lambda_home/lambda_away")
    return W1ENGINE.score_matrix(float(lh), float(la), float(rho), max_goals)


def main() -> int:
    parser = argparse.ArgumentParser(description="Settle Asian handicap cover probabilities from W1 matrix params.")
    parser.add_argument("--payload", type=Path, help="JSON with matrix_model/lambda params")
    parser.add_argument("--home-handicap", type=float, required=True)
    parser.add_argument("--home-price", type=float)
    parser.add_argument("--away-price", type=float)
    args = parser.parse_args()

    payload = json.loads(args.payload.read_text(encoding="utf-8")) if args.payload else {}
    matrix = matrix_from_payload(payload)
    print(json.dumps(cover_from_matrix(matrix, args.home_handicap, args.home_price, args.away_price), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
