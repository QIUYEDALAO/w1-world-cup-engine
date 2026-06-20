#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Asian Handicap settlement helpers for W1 Scout backtests."""
from __future__ import annotations

import argparse
import json
import math
from typing import Any

SETTLEMENT_VALUES = {
    "full_win": 1.0,
    "half_win": 0.5,
    "push": 0.0,
    "half_loss": -0.5,
    "full_loss": -1.0,
}


def _line(value: Any) -> float:
    out = float(str(value).replace("+", ""))
    if not math.isfinite(out):
        raise ValueError(f"invalid handicap line: {value}")
    return round(out * 4) / 4


def split_quarter_line(handicap: float) -> list[float]:
    """Split quarter AH lines into two half-stakes; keep whole/half lines whole."""
    line = _line(handicap)
    quarters = round(line * 4)
    if quarters % 2 == 0:
        return [round(line, 2)]
    return [round(line - 0.25, 2), round(line + 0.25, 2)]


def settle_single_line(selected_goals: int, opponent_goals: int, handicap: float) -> float:
    adjusted_margin = float(selected_goals) + _line(handicap) - float(opponent_goals)
    if adjusted_margin > 1e-9:
        return SETTLEMENT_VALUES["full_win"]
    if adjusted_margin < -1e-9:
        return SETTLEMENT_VALUES["full_loss"]
    return SETTLEMENT_VALUES["push"]


def _settlement_name(value: float) -> str:
    for name, points in SETTLEMENT_VALUES.items():
        if abs(points - value) < 1e-9:
            return name
    raise ValueError(f"unsupported settlement value: {value}")


def settle_ah_pick(selected_goals: int, opponent_goals: int, handicap: float) -> dict[str, Any]:
    legs = split_quarter_line(handicap)
    leg_values = [settle_single_line(selected_goals, opponent_goals, leg) for leg in legs]
    value = round(sum(leg_values) / len(leg_values), 3)
    return {
        "settlement_result": _settlement_name(value),
        "settlement_value": value,
        "legs": [{"handicap": leg, "value": leg_value, "result": _settlement_name(leg_value)} for leg, leg_value in zip(legs, leg_values)],
    }


def line_bucket(handicap: float, buckets: list[float] | None = None) -> str:
    buckets = buckets or [0, 0.25, 0.5, 0.75, 1.0, 1.25]
    abs_line = abs(_line(handicap))
    nearest = min((float(item) for item in buckets), key=lambda item: abs(item - abs_line))
    return f"{nearest:g}"


def side_role(handicap: float) -> str:
    line = _line(handicap)
    if line < 0:
        return "favorite"
    if line > 0:
        return "underdog"
    return "pickem"


def _assert_case(name: str, selected: int, opponent: int, handicap: float, expected: str) -> None:
    result = settle_ah_pick(selected, opponent, handicap)
    if result["settlement_result"] != expected:
        raise AssertionError(f"{name}: {result['settlement_result']} != {expected} ({result})")


def self_test() -> None:
    _assert_case("-0.5 win by 1", 1, 0, -0.5, "full_win")
    _assert_case("-0.5 draw", 0, 0, -0.5, "full_loss")
    _assert_case("+0.5 draw", 0, 0, 0.5, "full_win")
    _assert_case("+0.5 lose by 1", 0, 1, 0.5, "full_loss")
    _assert_case("-0.25 draw", 0, 0, -0.25, "half_loss")
    _assert_case("+0.25 draw", 0, 0, 0.25, "half_win")
    _assert_case("-0.75 win by 1", 1, 0, -0.75, "half_win")
    _assert_case("+0.75 lose by 1", 0, 1, 0.75, "half_loss")
    _assert_case("0 draw", 0, 0, 0, "push")
    _assert_case("+1 lose by 1", 0, 1, 1, "push")
    _assert_case("-1 win by 1", 1, 0, -1, "push")
    if split_quarter_line(0.25) != [0.0, 0.5]:
        raise AssertionError("+0.25 split failed")
    if split_quarter_line(-0.75) != [-1.0, -0.5]:
        raise AssertionError("-0.75 split failed")
    print("W1 AH settlement self-test PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description="Settle one Asian Handicap pick.")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--selected-goals", type=int)
    parser.add_argument("--opponent-goals", type=int)
    parser.add_argument("--handicap", type=float)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.selected_goals is None or args.opponent_goals is None or args.handicap is None:
        parser.error("--selected-goals, --opponent-goals, and --handicap are required unless --self-test")
    print(json.dumps(settle_ah_pick(args.selected_goals, args.opponent_goals, args.handicap), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
