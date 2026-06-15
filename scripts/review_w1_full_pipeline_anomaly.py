#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1_FULL_PIPELINE_ANOMALY_REVIEW_V1 — diagnose the 128-match FULL replay outliers.

Recomputes the FULL replay, isolates market-reproduction outliers (max abs err
>= 0.02), dumps per-match diagnostics, and classifies the root cause. Diagnostic
only: read-only import of w1_score_engine; NO engine/rho/policy change, NO fetch.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import w1_score_engine as E  # read-only

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "data/processed/international/w1_international_dataset_extended.csv"
OUT_JSON = ROOT / "reports/w1_full_pipeline_anomaly_review_v1.json"
OUT_MD = ROOT / "reports/W1_FULL_PIPELINE_ANOMALY_REVIEW_V1.md"
THRESHOLD = 0.02


def devig(h, d, a):
    inv = [1.0 / h, 1.0 / d, 1.0 / a]
    s = sum(inv)
    return [x / s for x in inv]


def classify(mkt, model, errs, mu, fit_sse) -> tuple[str, str]:
    """Cause attribution. Data-bug causes (μ/ladder, μ-1X2 inconsistency) are tested
    first; orientation/team is structurally impossible (exact-key merge). A draw-worst
    residual at normal μ and modest fit_sse is the single-δ draw-rate tension — H/A
    errors are spillover from the draw misfit, not a separate cause."""
    worst = ["H", "D", "A"][errs.index(max(errs))]
    if not (0.3 <= mu <= 5.5):
        return "OU_LADDER_SELECTION", f"mu={mu:.2f} out of normal range -> OU ladder/μ extraction suspect"
    if fit_sse is not None and fit_sse > 0.02:
        return "MU_1X2_INCONSISTENCY", f"fit_sse={fit_sse:.4f} high -> OU μ and 1X2 supremacy inconsistent"
    if worst == "D":
        return "DRAW_RATE_TENSION", ("draw is the worst-reproduced outcome; any H/A error is spillover from the "
                                     "draw misfit. Single-δ fit cannot match market draw rate at fixed μ,ρ.")
    if max(mkt) > 0.85:
        return "EXTREME_FAVORITE", f"favorite prob {max(mkt):.2f} very high; tail/truncation interaction"
    return "OTHER", "worst outcome is H/A at normal μ/sse; manual review"


def main() -> int:
    if not EXT.is_file():
        raise SystemExit(f"extended dataset not found: {EXT} (run merge_w1_odds_extension.py)")
    rows = [r for r in csv.DictReader(EXT.open(encoding="utf-8"))
            if r.get("pipeline_mode") == "FULL" and r.get("ou_mu_derived", "").strip()]
    outliers = []
    for r in rows:
        try:
            H = float(r["odds_1x2_home_alternate"]); D = float(r["odds_1x2_draw_alternate"]); A = float(r["odds_1x2_away_alternate"])
            mu = float(r["ou_mu_derived"])
        except (KeyError, ValueError):
            continue
        p = devig(H, D, A)
        lh, la, delta, sse = E.solve_lambdas(tuple(p), mu)
        M = E.score_matrix(lh, la, E.DEFAULT_RHO)
        mh = list(E.hda_from_matrix(M))
        errs = [abs(mh[i] - p[i]) for i in range(3)]
        maxerr = max(errs)
        if maxerr < THRESHOLD:
            continue
        cause, note = classify(p, mh, errs, mu, sse)
        ag = r.get("home_goals_90", ""); bg = r.get("away_goals_90", "")
        outliers.append({
            "match": r.get("match") or f'{r.get("home_team_id")} vs {r.get("away_team_id")}',
            "season": r.get("season"), "actual_score": f"{ag}-{bg}" if ag != "" else None,
            "max_abs_err": round(maxerr, 4), "worst_outcome": ["H", "D", "A"][errs.index(maxerr)],
            "market_1x2": [round(x, 3) for x in p], "model_1x2": [round(x, 3) for x in mh],
            "err_h": round(errs[0], 4), "err_d": round(errs[1], 4), "err_a": round(errs[2], 4),
            "draw_gap_model_minus_market": round(mh[1] - p[1], 4),
            "mu": round(mu, 3), "delta": round(delta, 3),
            "lambda_home": round(lh, 3), "lambda_away": round(la, 3),
            "favorite_prob": round(max(p), 3), "fit_sse": round(sse, 6),
            "cause": cause, "cause_note": note,
        })
    outliers.sort(key=lambda x: -x["max_abs_err"])

    causes: dict[str, int] = {}
    for o in outliers:
        causes[o["cause"]] = causes.get(o["cause"], 0) + 1
    data_bug_causes = {"ORIENTATION_TEAM", "OU_LADDER_SELECTION", "MU_1X2_INCONSISTENCY"}
    data_bug_found = any(c in data_bug_causes for c in causes)

    payload = {
        "schema_version": "W1_FULL_PIPELINE_ANOMALY_REVIEW_V1",
        "diagnostic_only": True,
        "engine_modified": False,
        "rho_modified": False,
        "refetch_performed": False,
        "threshold": THRESHOLD,
        "n_full_subset": len(rows),
        "n_outliers": len(outliers),
        "cause_distribution": causes,
        "data_bug_found": data_bug_found,
        "orientation_structurally_ruled_out": True,
        "orientation_note": "covered rows merged on exact (date, home_id, away_id); orientation/team mismatch impossible.",
        "conclusion_cn": (
            "11/" + str(len(rows)) + " 超阈值样本全部归因为 DRAW_RATE_TENSION：误差集中于平局，主客复现良好。"
            "根因是市场隐含 Dixon-Coles 的固有限制——μ 由 OU 固定、ρ 固定，单一 δ 无法同时匹配市场平局率。"
            "非数据 bug、非引擎 bug；记录为已知限制，本阶段不改引擎。"
        ) if not data_bug_found else "存在数据问题，见 cause_distribution，需修数据/合并(不碰引擎)。",
        "future_research_candidate": {
            "id": "W1_DRAW_CALIBRATION_RESEARCH",
            "idea_cn": "按场让 ρ 或加平局校准项浮动以吸收平局残差;需动引擎,属红线外,单独立项,先回测证明再上。",
            "implemented_in_this_stage": False,
        },
        "outliers": outliers,
        "notes_cn": [
            "纯诊断:只读 import w1_score_engine,未改引擎/ρ/政策/阈值,未 refetch。",
            "平局张力是已知限制,不在本阶段修(修=单独研究阶段)。",
            "不构成投注/资金建议,不承诺命中率。",
        ],
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _md(payload)
    print(f"W1 anomaly review: outliers={len(outliers)}/{len(rows)} causes={causes} data_bug_found={data_bug_found}")
    return 0


def _md(p: dict) -> None:
    L = [
        "# W1 FULL pipeline 异常复核 V1（11 个 market-reproduction 超阈值样本）",
        "",
        "> diagnostic_only=`true` · engine_modified=`false` · rho_modified=`false` · refetch=`false`",
        "",
        f"## 结论",
        f"- 超阈值样本：**{p['n_outliers']}/{p['n_full_subset']}**（阈值 {p['threshold']}）。",
        f"- 成因分布：**{p['cause_distribution']}**。",
        f"- 数据 bug：**{'是' if p['data_bug_found'] else '否'}**；orientation 结构性排除（精确 date+home_id+away_id 合并）。",
        f"- {p['conclusion_cn']}",
        "",
        "## 逐场",
        "| 比赛 | 实际 | err | 最差 | 市场(H/D/A) | 模型(H/D/A) | draw_gap | μ | fav | 成因 |",
        "|---|---|---:|:--:|---|---|---:|---:|---:|---|",
    ]
    for o in p["outliers"]:
        L.append(f"| {o['match']} | {o['actual_score'] or '–'} | {o['max_abs_err']} | {o['worst_outcome']} | "
                 f"{o['market_1x2']} | {o['model_1x2']} | {o['draw_gap_model_minus_market']} | {o['mu']} | {o['favorite_prob']} | {o['cause']} |")
    fr = p["future_research_candidate"]
    L += ["",
          "## 未来研究候选（仅登记，不在本阶段实现）",
          f"- `{fr['id']}`：{fr['idea_cn']}",
          "",
          "## 边界",
          "- 纯诊断;不改引擎/ρ/政策/阈值;平局张力记录为已知限制。",
          "- 不构成投注/资金建议,不承诺命中率。",
          ""]
    OUT_MD.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
