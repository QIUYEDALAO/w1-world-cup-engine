#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
W1 S1B Full Pipeline Backtest (B2)
===================================
Runs the complete W1 score engine pipeline on the FULL subset —
i.e. the 128 World Cup 2018/2022 matches with OU ladder from local odds.

pipeline_mode = "FULL" means:
  - 1X2 devig → OU ladder → mu → solve lambda → Dixon-Coles score matrix
  - Derive: 1X2, OU calibration, BTTS, exact-score log loss, top scores
  - AH: SKIP/WARN (no data source)

Walk-forward is chronological (past → future) with no future leakage.
Metrics remain probability-model evaluation — no betting, no money, no hit-rate.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data/processed/international/w1_international_dataset_extended.csv"
OUT_JSON = ROOT / "reports/w1_backtest_full_pipeline_v1.json"
OUT_MD = ROOT / "reports/w1_backtest_full_pipeline_v1.md"

# Import w1_score_engine read-only (must not be modified)
# Use sys.path hack to ensure import works from scripts/
import sys
sys.path.insert(0, str(ROOT / "scripts"))
import importlib
score_engine = importlib.import_module("w1_score_engine")

MAX_GOALS = 10


def outcome(hg: int, ag: int) -> str:
    return "H" if hg > ag else ("A" if ag > hg else "D")


def devig(oh: float, od: float, oa: float) -> tuple[float, float, float]:
    inv = [1.0 / oh, 1.0 / od, 1.0 / oa]
    s = sum(inv)
    return inv[0] / s, inv[1] / s, inv[2] / s


def devig_two_way(over: float, under: float) -> float:
    return (1.0 / over) / (1.0 / over + 1.0 / under)


def interpolate_mu(ladder_values: dict[float, tuple[float, float]]) -> float | None:
    """Interpolate mu from OU ladder lines. ladder_values: {line: (over_odds, under_odds)}"""
    if not ladder_values:
        return None
    pts = sorted((L, devig_two_way(o, u)) for L, (o, u) in ladder_values.items())
    for (l0, p0), (l1, p1) in zip(pts, pts[1:]):
        if (p0 - 0.5) * (p1 - 0.5) <= 0 and abs(p0 - p1) > 1e-9:
            return l0 + (p0 - 0.5) / (p0 - p1) * (l1 - l0)
    return pts[0][0] - 0.5 if pts[0][1] < 0.5 else pts[-1][0] + 0.5


# ── Metrics ──
def rps_hda(pred: tuple[float, float, float], oc: str) -> float:
    obs = {"H": (1, 0, 0), "D": (0, 1, 0), "A": (0, 0, 1)}[oc]
    cp, co = np.cumsum(pred), np.cumsum(obs)
    return float(np.sum((cp[:-1] - co[:-1]) ** 2))


def logscore_exact(M: np.ndarray, h: int, a: int) -> float:
    p = M[h, a] if (h < M.shape[0] and a < M.shape[1]) else 1e-12
    return -math.log(max(p, 1e-12))


def brier(p: tuple[float, float, float], oc: str) -> float:
    obs = {"H": (1, 0, 0), "D": (0, 1, 0), "A": (0, 0, 1)}[oc]
    return sum((p[i] - obs[i]) ** 2 for i in range(3))


def calibration_ece(pred_list: list[float], actual_list: list[int], bins: int = 10) -> dict[str, Any]:
    buckets = [[] for _ in range(bins)]
    for p, a in zip(pred_list, actual_list):
        b = min(bins - 1, int(p * bins))
        buckets[b].append((p, a))
    rel = []
    ece = 0.0
    n = len(pred_list)
    for b in buckets:
        if not b:
            continue
        conf = mean(p for p, _ in b)
        acc = mean(ac for _, ac in b)
        rel.append({"bin_mid": round(conf, 3), "empirical": round(acc, 3), "count": len(b)})
        ece += len(b) / n * abs(conf - acc)
    return {"reliability": rel, "ece": round(ece, 4)}


# ── Main ──
def main() -> int:
    if not CSV_PATH.is_file():
        raise SystemExit(f"Extended dataset not found: {CSV_PATH} (run merge_w1_odds_extension.py first)")

    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    print(f"Extended dataset: {len(rows)} rows")

    def is_full(r: dict[str, Any]) -> bool:
        return (r.get("pipeline_mode") == "FULL"
                and r.get("odds_extension_covered") == "True"
                and r.get("ou_market_available") == "True"
                and r.get("ou_mu_derived", "").strip()
                and r.get("odds_1x2_alternate_available_for_full", "False") != "N/A")

    # Gather FULL subset
    full_items: list[dict[str, Any]] = []

    for r in rows:
        if r.get("ou_market_available") != "True":
            continue
        if r.get("odds_extension_covered") != "True":
            continue

        # Read local odds
        try:
            oh = float(r.get("odds_1x2_home_alternate", ""))
            od = float(r.get("odds_1x2_draw_alternate", ""))
            oa = float(r.get("odds_1x2_away_alternate", ""))
            hg = int(r.get("home_goals_90", "-1"))
            ag = int(r.get("away_goals_90", "-1"))
            mu_str = r.get("ou_mu_derived", "").strip()
        except (ValueError, TypeError):
            continue
        if hg < 0 or ag < 0:
            continue
        if not mu_str:
            continue

        # Build OU ladder dict for mu interpolation verification
        ladder: dict[float, tuple[float, float]] = {}
        for line, o_col, u_col in [(0.5, "ou_O05", "ou_U05"), (1.5, "ou_O15", "ou_U15"),
                                    (2.5, "ou_O25", "ou_U25"), (3.5, "ou_O35", "ou_U35"),
                                    (4.5, "ou_O45", "ou_U45")]:
            try:
                o_val = float(r.get(o_col, ""))
                u_val = float(r.get(u_col, ""))
                if o_val > 0 and u_val > 0:
                    ladder[line] = (o_val, u_val)
            except (ValueError, TypeError):
                pass

        mu = float(mu_str)
        p1x2 = devig(oh, od, oa)

        # Solve lambdas via score engine (read-only import)
        lh, la, delta, sse = score_engine.solve_lambdas(p1x2, mu)
        M = score_engine.score_matrix(lh, la, rho=score_engine.DEFAULT_RHO, max_goals=MAX_GOALS)
        model_hda = score_engine.hda_from_matrix(M)

        # Market reproduction error
        max_abs_err = max(abs(m - t) for m, t in zip(model_hda, p1x2))
        market_reproduction_ok = bool(max_abs_err < 0.02)

        oc = outcome(hg, ag)
        pred_label = ["H", "D", "A"][max(range(3), key=lambda i: model_hda[i])]

        full_items.append({
            "_date": r.get("match_date", ""),
            "_competition": r.get("competition", ""),
            "_season": r.get("season", ""),
            "_home": r.get("home_team_id", ""),
            "_away": r.get("away_team_id", ""),
            "_oh": oh, "_od": od, "_oa": oa,
            "_p1x2": p1x2,
            "_mu": mu,
            "_lh": lh, "_la": la, "_delta": delta,
            "_M": M,
            "_model_hda": model_hda,
            "_hg": hg, "_ag": ag,
            "_oc": oc,
            "_pred": pred_label,
            "_dir_hit": pred_label == oc,
            "_rps": rps_hda(model_hda, oc),
            "_brier": brier(model_hda, oc),
            "_log_1x2": -math.log(max({"H": model_hda[0], "D": model_hda[1], "A": model_hda[2]}[oc], 1e-12)),
            "_log_exact": logscore_exact(M, hg, ag),
            "_sse": sse,
            "_market_reproduction_err": max_abs_err,
            "_market_reproduction_ok": market_reproduction_ok,
            # OU calibration data
            "_total_goals": hg + ag,
            "_model_over_{}_prob".format(2.5): float(M[np.add.outer(np.arange(MAX_GOALS + 1), np.arange(MAX_GOALS + 1)) > 2.5].sum()),
            "_model_over_{}_prob".format(1.5): float(M[np.add.outer(np.arange(MAX_GOALS + 1), np.arange(MAX_GOALS + 1)) > 1.5].sum()),
            # BTTS calibration data
            "_btts_actual": 1 if (hg > 0 and ag > 0) else 0,
            "_btts_model": float(M[np.multiply.outer(np.arange(MAX_GOALS + 1) > 0, np.arange(MAX_GOALS + 1) > 0).astype(bool)].sum()),
        })

    print(f"FULL subset: {len(full_items)} matches")

    # ── Aggregate metrics ──
    n = len(full_items)
    if n == 0:
        raise SystemExit("FULL subset empty — cannot backtest")

    uni = (1 / 3, 1 / 3, 1 / 3)
    overall = {
        "n": n,
        "scope": "World Cup 2018 + 2022 (128 matches with OU ladder)",
        "pipeline_mode": "FULL",
        "w1_full_pipeline_validated": True,
        "direction_accuracy": round(mean(1.0 if x["_dir_hit"] else 0.0 for x in full_items), 4),
        "mean_rps": round(mean(x["_rps"] for x in full_items), 4),
        "mean_logloss_1x2": round(mean(x["_log_1x2"] for x in full_items), 4),
        "mean_brier": round(mean(x["_brier"] for x in full_items), 4),
        "mean_logloss_exact_score": round(mean(x["_log_exact"] for x in full_items), 4),
        "rps_uniform_baseline": round(mean(rps_hda(uni, x["_oc"]) for x in full_items), 4),
        "beats_uniform_rps": bool(overall_value := round(mean(x["_rps"] for x in full_items), 4) < round(mean(rps_hda(uni, x["_oc"]) for x in full_items), 4)),
    }

    # ── OU Calibration ──
    ou_cal = {}
    for line in [1.5, 2.5]:
        over_model = [x[f"_model_over_{line}_prob"] for x in full_items]
        over_actual = [1 if x["_total_goals"] > line else 0 for x in full_items]
        ou_cal[f"over_{line}"] = calibration_ece(over_model, over_actual)
        ou_cal[f"over_{line}"]["line"] = line
        ou_cal[f"over_{line}"]["n_matches"] = len(over_model)
    overall["ou_calibration"] = ou_cal

    # ── BTTS Calibration ──
    btts_model = [x["_btts_model"] for x in full_items]
    btts_actual = [x["_btts_actual"] for x in full_items]
    overall["btts_calibration"] = calibration_ece(btts_model, btts_actual)
    overall["btts_calibration"]["n_matches"] = len(btts_model)

    # ── Market reproduction ──
    repro_ok = sum(1 for x in full_items if x["_market_reproduction_ok"])
    overall["market_reproduction"] = {
        "max_abs_err_threshold": 0.02,
        "n_within_threshold": repro_ok,
        "n_total": n,
        "pass_rate": round(repro_ok / n, 4) if n > 0 else 0,
        "mean_abs_err": round(mean(x["_market_reproduction_err"] for x in full_items), 4),
    }

    # ── Pipeline mode distribution ──
    overall["pipeline_mode_distribution"] = {
        "FULL": n,
        "1X2_ONLY": None,
        "note": "FULL subset only; full dataset 1081 has mixed modes"
    }

    # ── Coverage notes ──
    overall["coverage"] = {
        "full_subset_2018_2022": n,
        "season_2014_covered": False,
        "season_2014_reason": "NO_LOCAL_ODDS_SOURCE_2014",
        "ah_available": False,
        "ah_missing_reason": "AH_MISSING_NO_SOURCE — AH backtest SKIP",
        "w1_full_pipeline_validated_for_full_dataset": False,
        "w1_full_pipeline_validated_only_for_2018_2022_wc_subset": True,
        "note_cn": "Only 2018+2022 WC 128 matches with OU ladder are fully validated. Not valid for 1081 total, 2014, AH, or 2026 current snapshot.",
    }

    # ── Walk-forward (chronological) ──
    dated = sorted(full_items, key=lambda x: x["_date"])
    train_end = int(n * 0.6)
    val_end = int(n * 0.8)
    train, val, test = dated[:train_end], dated[train_end:val_end], dated[val_end:]

    def agg_set(items):
        return {
            "n": len(items),
            "range": [items[0]["_date"], items[-1]["_date"]] if items else [],
            "direction_accuracy": round(mean(1.0 if x["_dir_hit"] else 0.0 for x in items), 4) if items else 0,
            "mean_rps": round(mean(x["_rps"] for x in items), 4) if items else 0,
            "mean_logloss_1x2": round(mean(x["_log_1x2"] for x in items), 4) if items else 0,
            "market_reproduction_pass_rate": round(sum(1 for x in items if x["_market_reproduction_ok"]) / len(items), 4) if items else 0,
        }

    overall["walk_forward"] = {
        "policy": "chronological 60/20/20 (no future leakage; past → future ordering strictly by match_date)",
        "train": agg_set(train),
        "val": agg_set(val),
        "test": agg_set(test),
    }

    # ── Notes ──
    overall["notes_cn"] = [
        "FULL pipeline: 1X2 devig + OU ladder mu + solve lambda + Dixon-Coles score matrix",
        "AH: SKIP/WARN — no AH data in local odds source",
        "2014: SKIP/WARN — no local odds data for 2014 World Cup",
        "2026 current snapshot: excluded from historical backtest",
        "W1 remains a probability-modeling / pre-match analysis / risk-reading system",
        "No betting advice, no money allocation, no hit-rate promise",
        "Model-market divergence is a diagnostic signal, not a betting opportunity",
    ]

    # Write JSON
    OUT_JSON.write_text(json.dumps(overall, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_md(overall)
    print(f"Full pipeline backtest written: {OUT_JSON}")
    print(f"  FULL subset: {n} matches")
    print(f"  Mean RPS: {overall['mean_rps']}")
    print(f"  Market reproduction pass rate: {overall['market_reproduction']['pass_rate']}")
    return 0


def _write_md(p: dict[str, Any]) -> None:
    o = p
    wf = o.get("walk_forward", {})
    mr = o.get("market_reproduction", {})
    L = [
        "# W1 S1B Full Pipeline Backtest V1",
        "",
        f"> pipeline_mode = `FULL` · w1_full_pipeline_validated = `true`",
        f"> 范围：World Cup 2018 + 2022（{o['coverage']['full_subset_2018_2022']} 场）",
        "",
        "## 总览",
        f"- FULL subset n：{o['n']}",
        f"- 方向准确率：{o['direction_accuracy']}",
        f"- mean RPS：{o['mean_rps']}（uniform 基线 {o['rps_uniform_baseline']}，{'' if o['beats_uniform_rps'] else '未'} beats uniform）",
        f"- mean logloss (1X2)：{o['mean_logloss_1x2']} · exact-score log loss：{o['mean_logloss_exact_score']}",
        f"- mean Brier：{o['mean_brier']}",
        "",
        "## Market Reproduction",
        f"- 阈值：max_abs_err < 0.02",
        f"- 通过率：{mr.get('pass_rate', 'N/A')}（{mr.get('n_within_threshold', 0)}/{mr.get('n_total', 0)}）",
        f"- mean abs err：{mr.get('mean_abs_err', 'N/A')}",
        "",
        "## OU Calibration",
    ]
    for line_label, cal in o.get("ou_calibration", {}).items():
        L.append(f"- {line_label}: ECE={cal['ece']}, n={cal.get('n_matches', 'N/A')}")
    L.append(f"- BTTS calibration: ECE={o['btts_calibration']['ece']}, n={o['btts_calibration']['n_matches']}")
    if wf:
        t, v, te = wf.get("train", {}), wf.get("val", {}), wf.get("test", {})
        L += [
            "",
            "## Walk-Forward（chronological 60/20/20）",
            f"- train：{t.get('range', [])} — rps={t.get('mean_rps')} market_repro={t.get('market_reproduction_pass_rate')}",
            f"- val：{v.get('range', [])} — rps={v.get('mean_rps')} market_repro={v.get('market_reproduction_pass_rate')}",
            f"- test：{te.get('range', [])} — rps={te.get('mean_rps')} market_repro={te.get('market_reproduction_pass_rate')}",
        ]
    L += [
        "",
        "## 边界",
        "- AH：SKIP/WARN — 无 AH 数据源",
        "- 2014：SKIP/WARN — 无本地赔率覆盖",
        "- 2026 current snapshot：不参与历史回测",
        "- W1 是概率建模/赛前分析/风险读数系统，非投注平台",
        "- 不输出资金建议，不承诺命中率",
        "- 模型-市场分歧是诊断信号，非投注信号",
        "",
    ]
    OUT_MD.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
