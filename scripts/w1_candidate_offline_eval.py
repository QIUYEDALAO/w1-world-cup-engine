#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase A offline diagnostic for read-only W1 candidates.

Uses only the existing 128-match FULL subset. This is a descriptive diagnostic:
no calibration, no model change, no production wiring.
"""
from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data/processed/international/w1_international_dataset_extended.csv"
OUT_JSON = ROOT / "reports/w1_candidate_offline_eval_v1.json"
OUT_MD = ROOT / "reports/w1_candidate_offline_eval_v1.md"
sys.path.insert(0, str(ROOT / "scripts"))
import w1_score_engine as W1ENGINE  # noqa: E402
import w1_candidate_builder as CAND  # noqa: E402


def devig3(oh: float, od: float, oa: float) -> tuple[float, float, float]:
    inv = [1.0 / oh, 1.0 / od, 1.0 / oa]
    s = sum(inv)
    return inv[0] / s, inv[1] / s, inv[2] / s


def outcome(h: int, a: int) -> str:
    return "home_win" if h > a else ("away_win" if a > h else "draw")


def settle(candidate: dict[str, Any], h: int, a: int) -> float | None:
    market = candidate.get("market")
    selection = candidate.get("selection")
    line = candidate.get("line")
    if market == "1X2":
        return 1.0 if selection == outcome(h, a) else 0.0
    if market == "BTTS":
        yes = h > 0 and a > 0
        return 1.0 if (selection == "yes") == yes else 0.0
    if market == "score_pool":
        return 1.0 if selection == f"{h}-{a}" else 0.0
    if market == "OU" and line is not None:
        legs = CAND.split_quarter_line(float(line))
        score = 0.0
        for leg in legs:
            diff = h + a - leg
            if selection == "under":
                diff = -diff
            score += 1.0 if diff > 1e-9 else (-1.0 if diff < -1e-9 else 0.0)
        return score / len(legs)
    if market == "AH" and line is not None:
        legs = CAND.split_quarter_line(float(line))
        score = 0.0
        for leg in legs:
            diff = h - a + leg
            if selection == "away_cover":
                diff = -diff
            score += 1.0 if diff > 1e-9 else (-1.0 if diff < -1e-9 else 0.0)
        return score / len(legs)
    return None


def full_rows() -> list[dict[str, Any]]:
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    out = []
    for row in rows:
        if row.get("pipeline_mode") != "FULL":
            continue
        if row.get("odds_extension_covered") != "True":
            continue
        if row.get("ou_market_available") != "True":
            continue
        if not row.get("ou_mu_derived", "").strip():
            continue
        out.append(row)
    return out


def mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 6) if values else None


def main() -> int:
    if not CSV_PATH.is_file():
        raise SystemExit(f"missing dataset: {CSV_PATH}")

    grouped: dict[str, list[dict[str, float]]] = {}
    sample_count = 0
    for row in full_rows():
        try:
            p1x2 = devig3(
                float(row["odds_1x2_home_alternate"]),
                float(row["odds_1x2_draw_alternate"]),
                float(row["odds_1x2_away_alternate"]),
            )
            mu = float(row["ou_mu_derived"])
            h = int(row["home_goals_90"])
            a = int(row["away_goals_90"])
        except (KeyError, TypeError, ValueError):
            continue
        lh, la, _, _ = W1ENGINE.solve_lambdas(p1x2, mu)
        matrix = W1ENGINE.score_matrix(lh, la, rho=W1ENGINE.DEFAULT_RHO, max_goals=10)
        payload = CAND.build_candidates(matrix=matrix, score_distribution={"score_pool": []})
        errors = CAND.validate_candidates(payload)
        if errors:
            raise SystemExit(f"candidate validation failed: {errors}")
        sample_count += 1
        for item in payload["items"]:
            realized = settle(item, h, a)
            if realized is None:
                continue
            key = f"{item['market']}::{item['selection']}::{item.get('line')}"
            grouped.setdefault(key, []).append(
                {
                    "raw_probability": float(item["raw_probability"]),
                    "expected_result_score": float(item.get("expected_result_score") or 0.0),
                    "realized_result_score": float(realized),
                }
            )

    rows = []
    for key, values in sorted(grouped.items()):
        market, selection, line = key.split("::", 2)
        rows.append(
            {
                "market": market,
                "selection": selection,
                "line": None if line == "None" else float(line),
                "n": len(values),
                "mean_raw_probability": mean([x["raw_probability"] for x in values]),
                "mean_expected_result_score": mean([x["expected_result_score"] for x in values]),
                "mean_realized_result_score": mean([x["realized_result_score"] for x in values]),
            }
        )

    report = {
        "schema_version": "W1_CANDIDATE_OFFLINE_EVAL_V1",
        "stage": "W1_OPPORTUNITY_SELECTOR_PHASE_A",
        "research_only": True,
        "production_wired": False,
        "calibrated": False,
        "basis": CAND.BASIS,
        "scope": "World Cup 2018 + 2022 FULL subset only",
        "n_matches": sample_count,
        "candidate_groups": rows,
        "redline_confirmation": {
            "score_engine_changed": False,
            "default_rho_changed": False,
            "policy_changed": False,
            "thresholds_changed": False,
            "no_phase_b_c_d": True,
        },
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md = [
        "# W1 Candidate Offline Eval V1",
        "",
        "本报告只描述阶段 A 的同源候选集在既有 FULL 子集上的离线表现。它不是校准层，不接生产，不改变推荐比分算法。",
        "",
        f"- scope: {report['scope']}",
        f"- n_matches: {sample_count}",
        f"- basis: `{CAND.BASIS}`",
        "- calibrated: `false`",
        "- independent_edge: `false` for every candidate item",
        "",
        "## Aggregate Candidate Groups",
        "",
        "| market | selection | line | n | mean_raw_probability | mean_expected_result_score | mean_realized_result_score |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        md.append(
            f"| {row['market']} | {row['selection']} | {row['line'] if row['line'] is not None else ''} | "
            f"{row['n']} | {row['mean_raw_probability']} | {row['mean_expected_result_score']} | {row['mean_realized_result_score']} |"
        )
    md.extend(
        [
            "",
            "## Boundary",
            "",
            "- Phase A only: candidate unification and view separation.",
            "- No new calibration, no selector promotion, no score-engine edit.",
            "- All candidate probabilities trace to the same market-implied score matrix.",
        ]
    )
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"W1 candidate offline eval PASS n={sample_count}; wrote {OUT_JSON.relative_to(ROOT)} and {OUT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
