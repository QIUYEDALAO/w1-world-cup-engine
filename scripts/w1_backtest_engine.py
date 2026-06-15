#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 S1B 1X2-only market-baseline backtest (data spine).

Reads the normalized international dataset and evaluates the MARKET 1X2 baseline
(devigged closing odds) against actual 90-minute outcomes. This is the minimal
backtest framework (S1A folded in): metrics, calibration, walk-forward split,
slice report, leakage guard.

HARD LABEL: pipeline_mode = "1X2_ONLY", w1_full_pipeline_validated = false.
Without OU odds there is NO score matrix here, so this validates only the market's
1X2 outcome calibration — NOT the full W1 OU->mu->lambda pipeline. Exact-score /
total-goals / AH calibration are intentionally out of scope until OU is sourced.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data/processed/international/w1_international_dataset.csv"
OUT_JSON = ROOT / "reports/w1_backtest_1x2_only_baseline_v1.json"
OUT_MD = ROOT / "reports/w1_backtest_1x2_only_baseline_v1.md"

# Features the baseline is allowed to use (pre-match only). Anything derived from
# the final score is a label and must never enter prediction -> leakage guard.
ALLOWED_FEATURES = {"odds_1x2_home", "odds_1x2_draw", "odds_1x2_away"}
LABEL_FIELDS = {"home_goals_90", "away_goals_90", "finish_type", "home_goals_et", "home_penalties"}


def devig(oh: float, od: float, oa: float) -> tuple[float, float, float]:
    inv = [1.0 / oh, 1.0 / od, 1.0 / oa]
    s = sum(inv)
    return inv[0] / s, inv[1] / s, inv[2] / s


def outcome(hg: int, ag: int) -> str:
    return "H" if hg > ag else ("A" if ag > hg else "D")


def rps(p: tuple[float, float, float], oc: str) -> float:
    obs = {"H": (1, 0, 0), "D": (0, 1, 0), "A": (0, 0, 1)}[oc]
    cp = [p[0], p[0] + p[1]]
    co = [obs[0], obs[0] + obs[1]]
    return sum((cp[i] - co[i]) ** 2 for i in range(2))


def logloss(p: tuple[float, float, float], oc: str) -> float:
    pv = {"H": p[0], "D": p[1], "A": p[2]}[oc]
    return -math.log(max(pv, 1e-12))


def brier(p: tuple[float, float, float], oc: str) -> float:
    obs = {"H": (1, 0, 0), "D": (0, 1, 0), "A": (0, 0, 1)}[oc]
    return sum((p[i] - obs[i]) ** 2 for i in range(3))


def load_rows() -> list[dict[str, Any]]:
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    out = []
    for r in rows:
        if r.get("odds_1x2_available") != "True":
            continue
        if r.get("result_available") != "True":
            continue
        try:
            oh, od, oa = float(r["odds_1x2_home"]), float(r["odds_1x2_draw"]), float(r["odds_1x2_away"])
            hg, ag = int(r["home_goals_90"]), int(r["away_goals_90"])
        except (ValueError, KeyError, TypeError):
            continue
        p = devig(oh, od, oa)
        oc = outcome(hg, ag)
        pred = ["H", "D", "A"][max(range(3), key=lambda i: p[i])]
        out.append({**r, "_p": p, "_oc": oc, "_pred": pred,
                    "_rps": rps(p, oc), "_log": logloss(p, oc), "_brier": brier(p, oc),
                    "_dir_hit": pred == oc})
    return out


def agg(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        return {"n": 0}
    uni = (1 / 3, 1 / 3, 1 / 3)
    return {
        "n": len(items),
        "direction_accuracy": round(mean(1.0 if x["_dir_hit"] else 0.0 for x in items), 4),
        "mean_rps": round(mean(x["_rps"] for x in items), 4),
        "mean_logloss": round(mean(x["_log"] for x in items), 4),
        "mean_brier": round(mean(x["_brier"] for x in items), 4),
        "rps_uniform_baseline": round(mean(rps(uni, x["_oc"]) for x in items), 4),
        "beats_uniform_rps": bool(mean(x["_rps"] for x in items) < mean(rps(uni, x["_oc"]) for x in items)),
    }


def calibration(items: list[dict[str, Any]], bins: int = 10) -> dict[str, Any]:
    """Reliability of the home-win probability + ECE."""
    buckets = [[] for _ in range(bins)]
    for x in items:
        ph = x["_p"][0]
        b = min(bins - 1, int(ph * bins))
        buckets[b].append((ph, 1.0 if x["_oc"] == "H" else 0.0))
    rel = []
    ece = 0.0
    n = len(items)
    for b in buckets:
        if not b:
            continue
        conf = mean(p for p, _ in b)
        acc = mean(o for _, o in b)
        rel.append({"bin_mid": round(conf, 3), "empirical": round(acc, 3), "count": len(b)})
        ece += len(b) / n * abs(conf - acc)
    return {"home_win_reliability": rel, "ece_home_win": round(ece, 4)}


def slices(items: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    def by(keyfn):
        g: dict[str, list] = {}
        for x in items:
            g.setdefault(keyfn(x), []).append(x)
        return {k: agg(v) for k, v in sorted(g.items())}
    out["by_phase"] = by(lambda x: x["phase"])
    out["by_competition"] = by(lambda x: x["competition"])
    out["by_neutral_site"] = by(lambda x: f"neutral={x['neutral_site']}")
    def fav_bucket(x):
        m = max(x["_p"])
        return "fav>=0.70" if m >= 0.70 else ("fav 0.50-0.70" if m >= 0.50 else "fav<0.50 (close)")
    out["by_favorite_strength"] = by(fav_bucket)
    return out


def walk_forward(items: list[dict[str, Any]]) -> dict[str, Any]:
    dated = sorted([x for x in items if x.get("match_date")], key=lambda x: x["match_date"])
    n = len(dated)
    if n < 10:
        return {"note": "insufficient dated rows for split"}
    a, b = int(n * 0.6), int(n * 0.8)
    train, val, test = dated[:a], dated[a:b], dated[b:]
    return {
        "policy": "chronological 60/20/20 (train past -> test future); market baseline has no fit params, split is for S2 reuse + honest test-set reporting",
        "train": {"range": [train[0]["match_date"], train[-1]["match_date"]], **agg(train)},
        "val": {"range": [val[0]["match_date"], val[-1]["match_date"]], **agg(val)},
        "test": {"range": [test[0]["match_date"], test[-1]["match_date"]], **agg(test)},
    }


def main() -> int:
    if not CSV_PATH.is_file():
        raise SystemExit(f"dataset not found: {CSV_PATH} (run normalize_w1_international_dataset.py first)")
    items = load_rows()
    payload = {
        "schema_version": "W1_BACKTEST_1X2_ONLY_V1",
        "pipeline_mode": "1X2_ONLY",
        "w1_full_pipeline_validated": False,
        "leakage_guard": {
            "allowed_features": sorted(ALLOWED_FEATURES),
            "label_fields_excluded_from_prediction": sorted(LABEL_FIELDS),
            "status": "ok (prediction uses devigged closing 1X2 only; outcome read only for scoring)",
        },
        "scope_note_cn": "仅市场 1X2 校准基准；无 OU 故无比分矩阵，不验证完整 W1 管线、总进球或 AH。",
        "overall": agg(items),
        "calibration": calibration(items),
        "slices": slices(items),
        "walk_forward": walk_forward(items),
        "notes_cn": [
            "市场基准=收盘 1X2 去水概率；方向准确率/RPS/log/Brier 衡量市场本身，不是 W1 独立模型。",
            "国家队强度模型(S2)的增量必须相对此基准、用 walk-forward 样本外证明。",
            "不构成投注/资金建议，不承诺命中率。",
        ],
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_md(payload)
    o = payload["overall"]
    print(f"W1 1X2-only baseline: n={o['n']} dir_acc={o['direction_accuracy']} mean_rps={o['mean_rps']} "
          f"ece_home={payload['calibration']['ece_home_win']} (pipeline_mode=1X2_ONLY)")
    return 0


def _write_md(p: dict[str, Any]) -> None:
    o = p["overall"]
    L = [
        "# W1 1X2-only 市场基准回测 V1",
        "",
        "> pipeline_mode = `1X2_ONLY` · w1_full_pipeline_validated = `false`",
        "> 仅市场 1X2 校准基准；无 OU → 无比分矩阵，**不验证完整 W1 管线 / 总进球 / AH**。",
        "",
        "## 总览",
        f"- 样本 n：{o['n']}",
        f"- 方向准确率：{o['direction_accuracy']}",
        f"- mean RPS：{o['mean_rps']}（uniform 基线 {o['rps_uniform_baseline']}，beats_uniform={o['beats_uniform_rps']}）",
        f"- mean logloss：{o['mean_logloss']} · mean Brier：{o['mean_brier']}",
        f"- 主胜概率校准 ECE：{p['calibration']['ece_home_win']}",
        "",
        "## 分层（节选）",
    ]
    for k, v in p["slices"]["by_phase"].items():
        L.append(f"- phase={k}: n={v['n']} dir={v['direction_accuracy']} rps={v['mean_rps']}")
    for k, v in p["slices"]["by_favorite_strength"].items():
        L.append(f"- {k}: n={v['n']} dir={v['direction_accuracy']} rps={v['mean_rps']}")
    wf = p["walk_forward"]
    if "test" in wf:
        L += ["", "## Walk-forward（时间切分）",
              f"- train {wf['train']['range']} n={wf['train']['n']} rps={wf['train']['mean_rps']}",
              f"- test {wf['test']['range']} n={wf['test']['n']} rps={wf['test']['mean_rps']}"]
    L += ["", "## 边界", "- 市场基准衡量市场本身，非 W1 独立模型；S2 增量须相对此基准用样本外证明。",
          "- 不构成投注/资金建议，不承诺命中率。", ""]
    OUT_MD.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
