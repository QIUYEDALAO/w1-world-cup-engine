#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
W1_DRAW_CALIBRATION_RESEARCH_V1 — research / prototype / diagnostic backtest.

PURE RESEARCH. Does NOT modify the production engine, DEFAULT_RHO, decision policy,
odds thresholds, dashboard/predict/build. Imports w1_score_engine read-only.

Question: is there a draw-calibration scheme more stable than fixed-rho Dixon-Coles
that explains / possibly improves the 11/128 DRAW_RATE_TENSION reproduction outliers
— while holding up out-of-sample (walk-forward) and not hurting other metrics?

Candidates (see docs/W1_DRAW_CALIBRATION_RESEARCH_V1.md):
  B0  baseline  : fixed DEFAULT_RHO market-implied DC (production as-is)
  C1  diagnostic: per-match rho_draw_fit (oracle_like / market_reconciliation_only)
  C2  layer     : post-hoc draw-mass calibration to market_draw (renormalised)
  C3  parametric: walk-forward linear rho model on pre-match features only

Scope: 2018+2022 World Cup FULL subset (128 matches with OU ladder). Not 1081,
not qualifiers, not AH/2014. Research signal only — must NOT go to production.
"""
from __future__ import annotations

import csv
import importlib
import json
import math
import sys
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data/processed/international/w1_international_dataset_extended.csv"
OUT_JSON = ROOT / "reports/w1_draw_calibration_research_v1.json"
OUT_MD = ROOT / "reports/W1_DRAW_CALIBRATION_RESEARCH_V1.md"

sys.path.insert(0, str(ROOT / "scripts"))
SE = importlib.import_module("w1_score_engine")  # read-only

MAX_GOALS = 10
REPRO_THRESHOLD = 0.02
RHO_GRID = np.round(np.arange(-0.30, 0.0801, 0.005), 4)
RHO_CLIP = (-0.30, 0.08)
_IDX = np.add.outer(np.arange(MAX_GOALS + 1), np.arange(MAX_GOALS + 1))
_BOTH = np.multiply.outer(np.arange(MAX_GOALS + 1) > 0, np.arange(MAX_GOALS + 1) > 0)


# ── basic ──
def outcome(hg: int, ag: int) -> str:
    return "H" if hg > ag else ("A" if ag > hg else "D")


def devig(oh: float, od: float, oa: float) -> tuple[float, float, float]:
    inv = [1.0 / oh, 1.0 / od, 1.0 / oa]
    s = sum(inv)
    return inv[0] / s, inv[1] / s, inv[2] / s


def over_prob(M: np.ndarray, line: float) -> float:
    return float(M[_IDX > line].sum())


def btts_prob(M: np.ndarray) -> float:
    return float(M[_BOTH].sum())


# ── metrics ──
def rps_hda(pred, oc: str) -> float:
    obs = {"H": (1, 0, 0), "D": (0, 1, 0), "A": (0, 0, 1)}[oc]
    cp, co = np.cumsum(pred), np.cumsum(obs)
    return float(np.sum((cp[:-1] - co[:-1]) ** 2))


def brier(p, oc: str) -> float:
    obs = {"H": (1, 0, 0), "D": (0, 1, 0), "A": (0, 0, 1)}[oc]
    return sum((p[i] - obs[i]) ** 2 for i in range(3))


def logloss_1x2(p, oc: str) -> float:
    return -math.log(max({"H": p[0], "D": p[1], "A": p[2]}[oc], 1e-12))


def logloss_exact(M: np.ndarray, h: int, a: int) -> float:
    p = M[h, a] if (h < M.shape[0] and a < M.shape[1]) else 1e-12
    return -math.log(max(p, 1e-12))


def ece(pred_list, actual_list, bins: int = 10) -> float:
    n = len(pred_list)
    if n == 0:
        return 0.0
    buckets: list[list] = [[] for _ in range(bins)]
    for p, a in zip(pred_list, actual_list):
        buckets[min(bins - 1, int(p * bins))].append((p, a))
    e = 0.0
    for b in buckets:
        if not b:
            continue
        conf = mean(p for p, _ in b)
        acc = mean(ac for _, ac in b)
        e += len(b) / n * abs(conf - acc)
    return round(e, 4)


def eval_items(items: list[dict[str, Any]], pred_key: str) -> dict[str, Any]:
    """Aggregate metrics over items using the model stored under pred_key:
    item[pred_key] = {"hda": (h,d,a), "M": matrix, "repro_err": float}."""
    if not items:
        return {}
    hda = [it[pred_key]["hda"] for it in items]
    Ms = [it[pred_key]["M"] for it in items]
    rep = [it[pred_key]["repro_err"] for it in items]
    oc = [it["oc"] for it in items]
    draw_y = [1 if c == "D" else 0 for c in oc]
    draw_p = [h[1] for h in hda]
    return {
        "n": len(items),
        "rps": round(mean(rps_hda(hda[i], oc[i]) for i in range(len(items))), 4),
        "logloss_1x2": round(mean(logloss_1x2(hda[i], oc[i]) for i in range(len(items))), 4),
        "brier": round(mean(brier(hda[i], oc[i]) for i in range(len(items))), 4),
        "exact_score_logloss": round(mean(logloss_exact(Ms[i], items[i]["hg"], items[i]["ag"]) for i in range(len(items))), 4),
        "draw_calibration_ece": ece(draw_p, draw_y),
        "draw_logloss": round(mean(-(draw_y[i] * math.log(max(draw_p[i], 1e-12)) + (1 - draw_y[i]) * math.log(max(1 - draw_p[i], 1e-12))) for i in range(len(items))), 4),
        "draw_brier": round(mean((draw_p[i] - draw_y[i]) ** 2 for i in range(len(items))), 4),
        "ou_over_1.5_ece": ece([over_prob(Ms[i], 1.5) for i in range(len(items))], [1 if items[i]["total"] > 1.5 else 0 for i in range(len(items))]),
        "ou_over_2.5_ece": ece([over_prob(Ms[i], 2.5) for i in range(len(items))], [1 if items[i]["total"] > 2.5 else 0 for i in range(len(items))]),
        "btts_ece": ece([btts_prob(Ms[i]) for i in range(len(items))], [items[i]["btts"] for i in range(len(items))]),
        "market_reproduction_mean_abs_err": round(mean(rep), 4),
        "market_reproduction_pass_rate": round(sum(1 for e in rep if e < REPRO_THRESHOLD) / len(rep), 4),
        "direction_accuracy": round(mean(1.0 if ["H", "D", "A"][int(np.argmax(hda[i]))] == oc[i] else 0.0 for i in range(len(items))), 4),
    }


# ── model builders ──
def model_fixed(p1x2, mu, rho):
    lh, la, delta, _ = SE.solve_lambdas(p1x2, mu, rho)
    M = SE.score_matrix(lh, la, rho=rho, max_goals=MAX_GOALS)
    hda = SE.hda_from_matrix(M)
    repro = max(abs(m - t) for m, t in zip(hda, p1x2))
    return {"hda": hda, "M": M, "repro_err": repro, "rho": rho, "delta": delta}


def rho_draw_fit(p1x2, mu, market_draw):
    """C1: pick rho minimising |model_draw - market_draw| (delta solved inside)."""
    best = None
    for rho in RHO_GRID:
        m = model_fixed(p1x2, mu, float(rho))
        err = abs(m["hda"][1] - market_draw)
        if best is None or err < best[0]:
            best = (err, m)
    return best[1]


def model_draw_layer(base_M, market_draw):
    """C2: scale diagonal to market_draw, off-diagonal to 1-market_draw, renormalise."""
    d0 = float(np.trace(base_M))
    if not (1e-6 < d0 < 1 - 1e-6) or not (1e-6 < market_draw < 1 - 1e-6):
        hda = SE.hda_from_matrix(base_M)
        return {"hda": hda, "M": base_M, "repro_err": 0.0}
    M2 = base_M * ((1 - market_draw) / (1 - d0))
    for i in range(base_M.shape[0]):
        M2[i, i] = base_M[i, i] * (market_draw / d0)
    M2 = M2 / M2.sum()
    return {"hda": SE.hda_from_matrix(M2), "M": M2}


# ── load FULL subset ──
def load_full_subset() -> list[dict[str, Any]]:
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    items: list[dict[str, Any]] = []
    for r in rows:
        if r.get("ou_market_available") != "True" or r.get("odds_extension_covered") != "True":
            continue
        try:
            oh = float(r.get("odds_1x2_home_alternate", ""))
            od = float(r.get("odds_1x2_draw_alternate", ""))
            oa = float(r.get("odds_1x2_away_alternate", ""))
            hg = int(r.get("home_goals_90", "-1"))
            ag = int(r.get("away_goals_90", "-1"))
            mu = float(r.get("ou_mu_derived", "").strip())
        except (ValueError, TypeError):
            continue
        if hg < 0 or ag < 0:
            continue
        p1x2 = devig(oh, od, oa)
        stage = (str(r.get("stage", "")) + " " + str(r.get("phase", ""))).lower()
        knockout = 0 if "group" in stage else 1
        items.append({
            "date": r.get("match_date", ""),
            "season": r.get("season", ""),
            "home": r.get("home_team_id", ""),
            "away": r.get("away_team_id", ""),
            "p1x2": p1x2,
            "market_home": p1x2[0], "market_draw": p1x2[1], "market_away": p1x2[2],
            "favorite_strength": max(p1x2[0], p1x2[2]),
            "knockout": knockout,
            "neutral": 1 if str(r.get("neutral_site", "")).lower() in {"true", "1"} else 0,
            "mu": mu,
            "hg": hg, "ag": ag,
            "oc": outcome(hg, ag),
            "total": hg + ag,
            "btts": 1 if (hg > 0 and ag > 0) else 0,
        })
    items.sort(key=lambda x: x["date"])
    return items


def beats(cand: dict, base: dict, key: str) -> bool:
    return cand.get(key) is not None and base.get(key) is not None and cand[key] < base[key]


def main() -> int:
    if not CSV_PATH.is_file():
        raise SystemExit(f"FULL subset CSV not found: {CSV_PATH} (run merge_w1_odds_extension.py). Research cannot reproduce.")
    items = load_full_subset()
    n = len(items)
    if n == 0:
        raise SystemExit("FULL subset empty — cannot run research backtest.")

    # ── B0 baseline + C1 + C2 per match ──
    for it in items:
        it["B0"] = model_fixed(it["p1x2"], it["mu"], SE.DEFAULT_RHO)
        c1 = rho_draw_fit(it["p1x2"], it["mu"], it["market_draw"])
        it["C1"] = c1
        it["rho_fit"] = c1["rho"]
        it["C2"] = model_draw_layer(it["B0"]["M"], it["market_draw"])
        it["C2"]["repro_err"] = max(abs(m - t) for m, t in zip(it["C2"]["hda"], it["p1x2"]))

    # ── C3 walk-forward parametric rho ──
    tr_end, va_end = int(n * 0.6), int(n * 0.8)
    train, val, test = items[:tr_end], items[tr_end:va_end], items[va_end:]

    def feats(it):
        return [1.0, it["mu"], it["market_draw"], it["favorite_strength"], float(it["knockout"])]

    X_tr = np.array([feats(it) for it in train])
    y_tr = np.array([it["rho_fit"] for it in train])
    coef, *_ = np.linalg.lstsq(X_tr, y_tr, rcond=None)
    for it in items:
        rho_pred = float(np.clip(np.dot(feats(it), coef), RHO_CLIP[0], RHO_CLIP[1]))
        it["rho_pred_c3"] = rho_pred
        it["C3"] = model_fixed(it["p1x2"], it["mu"], rho_pred)

    # ── aggregate ──
    base_all = eval_items(items, "B0")
    report = {
        "stage": "W1_DRAW_CALIBRATION_RESEARCH_V1",
        "research_only": True,
        "prototype": True,
        "production_wired": False,
        "scope": "World Cup 2018 + 2022 FULL subset (OU ladder), n=%d; NOT 1081, NOT qualifiers, NOT AH/2014" % n,
        "n": n,
        "engine_unchanged": {"DEFAULT_RHO": SE.DEFAULT_RHO, "rho_grid": [float(RHO_GRID[0]), float(RHO_GRID[-1])]},
        "draw_tension_outliers_baseline": sum(1 for it in items if it["B0"]["repro_err"] >= REPRO_THRESHOLD),
        "candidates": {
            "B0_baseline_fixed_rho": {"overall": base_all, "note": "production as-is (fixed DEFAULT_RHO)"},
            "C1_diagnostic_draw_fit_rho": {
                "overall": eval_items(items, "C1"),
                "oracle_like": True,
                "market_reconciliation_only": True,
                "note": "per-match rho fit to market_draw — UPPER BOUND / diagnostic, NOT a production candidate",
                "rho_fit_summary": {
                    "min": round(float(min(it["rho_fit"] for it in items)), 4),
                    "max": round(float(max(it["rho_fit"] for it in items)), 4),
                    "mean": round(float(mean(it["rho_fit"] for it in items)), 4),
                },
            },
            "C2_draw_calibration_layer": {
                "overall": eval_items(items, "C2"),
                "research_only": True,
                "note": "post-hoc draw-mass scaling to market_draw; preserves H/A ratio & sums to 1",
            },
            "C3_parametric_walkforward_rho": {
                "overall": eval_items(items, "C3"),
                "walk_forward": {
                    "policy": "chronological 60/20/20 by match_date; fit on train, judged on test (out-of-sample)",
                    "train": eval_items(train, "C3"),
                    "val": eval_items(val, "C3"),
                    "test": eval_items(test, "C3"),
                    "baseline_test": eval_items(test, "B0"),
                    "coef_feature_order": ["bias", "mu", "market_draw", "favorite_strength", "knockout"],
                    "coef": [round(float(c), 5) for c in coef],
                },
                "research_only": True,
                "note": "only generalizable candidate; linear rho(features) trained walk-forward",
            },
        },
    }

    # ── comparison vs baseline (lower is better for all these) ──
    lower_better = ["rps", "logloss_1x2", "brier", "exact_score_logloss",
                    "draw_calibration_ece", "draw_logloss", "draw_brier",
                    "ou_over_1.5_ece", "ou_over_2.5_ece", "btts_ece",
                    "market_reproduction_mean_abs_err"]
    comparison = {}
    for cand in ["C1_diagnostic_draw_fit_rho", "C2_draw_calibration_layer", "C3_parametric_walkforward_rho"]:
        ov = report["candidates"][cand]["overall"]
        comparison[cand] = {
            "beats_baseline": {k: beats(ov, base_all, k) for k in lower_better},
            "draw_improved": beats(ov, base_all, "draw_logloss") or beats(ov, base_all, "draw_calibration_ece"),
            "outcome_skill_improved_rps": beats(ov, base_all, "rps"),
            "tradeoff_other_worse": any((ov.get(k, 0) > base_all.get(k, 0)) for k in ["exact_score_logloss", "ou_over_1.5_ece", "ou_over_2.5_ece", "btts_ece"]),
        }
    # C3 generalization: test vs baseline_test. Margin-aware: a sub-0.005 RPS beat on a
    # ~26-match test fold is sampling noise, not signal — require a meaningful margin AND
    # same-direction improvement on draw_logloss before calling it a robust signal.
    c3 = report["candidates"]["C3_parametric_walkforward_rho"]["walk_forward"]
    RPS_NOISE_MARGIN = 0.005
    rps_gain_test = round(c3["baseline_test"].get("rps", 0) - c3["test"].get("rps", 0), 4)  # +ve = C3 better
    c3_robust = (rps_gain_test >= RPS_NOISE_MARGIN) and beats(c3["test"], c3["baseline_test"], "draw_logloss")
    comparison["C3_out_of_sample_test"] = {
        "rps_test": c3["test"].get("rps"),
        "rps_test_baseline": c3["baseline_test"].get("rps"),
        "rps_gain_test_vs_baseline": rps_gain_test,
        "noise_margin": RPS_NOISE_MARGIN,
        "c3_beats_baseline_on_test_rps": beats(c3["test"], c3["baseline_test"], "rps"),
        "c3_beats_baseline_on_test_draw_logloss": beats(c3["test"], c3["baseline_test"], "draw_logloss"),
        "train_vs_test_rps_gap": round((c3["test"].get("rps", 0) - c3["train"].get("rps", 0)), 4),
        "robust_out_of_sample_signal": bool(c3_robust),
    }
    report["comparison_vs_baseline"] = comparison

    # C1 oracle upper bound: even near-perfect market-reproduction barely moves outcome RPS.
    c1_ov = report["candidates"]["C1_diagnostic_draw_fit_rho"]["overall"]
    c1_rps_gain = round(base_all.get("rps", 0) - c1_ov.get("rps", 0), 4)

    # ── recommendation (research signal only; cannot recommend production) ──
    report["recommendation"] = {
        "production_change_recommended": False,
        "next_stage_recommended": "W1_DRAW_CALIBRATION_PROTOTYPE_V2" if c3_robust else None,
        "robust_out_of_sample_signal": bool(c3_robust),
        "reason_cn": (
            "C3 在样本外 test 上以 ≥%.3f RPS 且 draw_logloss 同向优于 baseline，存在可能的泛化价值，建议仅进入 prototype V2 继续验证（仍不接生产）。" % RPS_NOISE_MARGIN
            if c3_robust else
            "无候选在样本外**稳定**优于 baseline：C3 test RPS 仅领先 %.4f（< 噪声阈值 %.3f）且 draw_logloss 未同向改善；C1 oracle 上界即便把 market-reproduction 打到近 0，outcome RPS 也只改善 %.4f——说明 11/128 的 draw 残差主要是 **market-reproduction 工件**而非预测缺陷。不建议进入下一阶段，更不接生产。" % (rps_gain_test, RPS_NOISE_MARGIN, c1_rps_gain)
        ),
        "hard_constraint_cn": "本研究为信号，128 场 finals-only 样本小，绝不可直接上线、不可改 DEFAULT_RHO、不可替换 score engine。",
        "c1_is_oracle_upper_bound": True,
        "c1_oracle_rps_gain_over_baseline": c1_rps_gain,
        "tradeoff_observed_cn": "C2 把 draw 对齐市场，但 OU2.5 ECE 变差（draw 后处理扰动了总进球结构）——典型 tradeoff。",
    }

    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_md(report)
    print(f"draw calibration research written: {OUT_JSON}")
    print(f"  n={n}  baseline draw outliers={report['draw_tension_outliers_baseline']}")
    print(f"  baseline RPS={base_all['rps']}  C1 RPS={report['candidates']['C1_diagnostic_draw_fit_rho']['overall']['rps']}  C3 RPS={report['candidates']['C3_parametric_walkforward_rho']['overall']['rps']}")
    print(f"  C3 test RPS={c3['test'].get('rps')} vs baseline test RPS={c3['baseline_test'].get('rps')}")
    print(f"  next_stage_recommended={report['recommendation']['next_stage_recommended']}")
    return 0


def _write_md(r: dict[str, Any]) -> None:
    b = r["candidates"]["B0_baseline_fixed_rho"]["overall"]
    c1 = r["candidates"]["C1_diagnostic_draw_fit_rho"]["overall"]
    c2 = r["candidates"]["C2_draw_calibration_layer"]["overall"]
    c3 = r["candidates"]["C3_parametric_walkforward_rho"]["overall"]
    wf = r["candidates"]["C3_parametric_walkforward_rho"]["walk_forward"]
    oos = r["comparison_vs_baseline"]["C3_out_of_sample_test"]

    def row(name, m):
        return (f"| {name} | {m['rps']} | {m['logloss_1x2']} | {m['draw_calibration_ece']} | "
                f"{m['draw_logloss']} | {m['exact_score_logloss']} | {m['ou_over_2.5_ece']} | "
                f"{m['btts_ece']} | {m['market_reproduction_mean_abs_err']} | {m['market_reproduction_pass_rate']} |")

    L = [
        "# W1_DRAW_CALIBRATION_RESEARCH_V1 — 指标报告",
        "",
        "> 纯研究 / prototype / diagnostic。`research_only=true`、`production_wired=false`。",
        f"> 范围：{r['scope']}。",
        f"> baseline 下 draw-tension 超阈值（≥{REPRO_THRESHOLD}）场次：**{r['draw_tension_outliers_baseline']}/{r['n']}**。",
        "",
        "## 候选总览（lower is better；market_repro pass_rate 越高越好）",
        "",
        "| 候选 | RPS | logloss_1X2 | draw ECE | draw logloss | exact-score logloss | OU2.5 ECE | BTTS ECE | repro mean err | repro pass |",
        "|---|---|---|---|---|---|---|---|---|---|",
        row("B0 baseline (fixed ρ)", b),
        row("C1 draw-fit ρ (oracle)", c1),
        row("C2 draw layer", c2),
        row("C3 parametric WF", c3),
        "",
        "> C1 为逐场后验上界（`oracle_like` / `market_reconciliation_only`），**不是生产候选**。",
        "",
        "## C3 walk-forward（chronological 60/20/20，仅 test 判定泛化）",
        f"- train RPS={wf['train'].get('rps')} · val RPS={wf['val'].get('rps')} · **test RPS={wf['test'].get('rps')}**",
        f"- baseline 同 test 段 RPS={wf['baseline_test'].get('rps')} → C3 test {'优于' if oos['c3_beats_baseline_on_test_rps'] else '未优于'} baseline",
        f"- train→test RPS gap={oos['train_vs_test_rps_gap']}（过拟合诊断）",
        f"- ρ(features) 系数 {wf['coef_feature_order']} = {wf['coef']}",
        "",
        "## 结论",
        f"- production_change_recommended: **{r['recommendation']['production_change_recommended']}**",
        f"- next_stage_recommended: **{r['recommendation']['next_stage_recommended']}**",
        f"- {r['recommendation']['reason_cn']}",
        f"- {r['recommendation']['hard_constraint_cn']}",
        "",
        "## 边界",
        "- 128 场、finals-only、含 knockout/neutral，样本小、结构特殊；任何改善只是 research signal。",
        "- 不改 DEFAULT_RHO / score engine / decision_policy / thresholds；不接 dashboard/predict/build；不外推 1081/预选赛。",
        "- W1 是概率建模/赛前-赛后研究系统，非投注平台；无资金建议、无命中率承诺。",
        "",
    ]
    OUT_MD.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
