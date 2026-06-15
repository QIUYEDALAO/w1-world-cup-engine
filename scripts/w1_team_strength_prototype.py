#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 S2 national-team strength PROTOTYPE (research-only, not production).

Fits a time-decayed Poisson attack/defense model with L2 shrinkage on the S1B
international dataset, then compares it to the 1X2 market baseline on a held-out,
chronologically-later test set (no future leakage).

HARD LABELS: prototype=true, production_validated=false, production_wired=false.
Does NOT touch w1_score_engine / DEFAULT_RHO / decision_policy / odds thresholds,
and is NOT wired into the live prediction pipeline.
"""
from __future__ import annotations

import csv
import json
import math
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data/processed/international/w1_international_dataset.csv"
OUT_JSON = ROOT / "reports/w1_team_strength_prototype_v1.json"
OUT_MD = ROOT / "reports/w1_team_strength_prototype_v1.md"

HALF_LIFE_DAYS = 400.0
REG = 2.0           # L2 shrinkage (partial pooling toward global prior)
LR = 0.4
ITERS = 600
MAXG = 10
HOSTS = {"usa", "mexico", "canada"}


def _d(s: str) -> date | None:
    try:
        y, m, dd = (int(x) for x in s.split("-")[:3])
        return date(y, m, dd)
    except Exception:
        return None


def load() -> list[dict[str, Any]]:
    rows = []
    for r in csv.DictReader(CSV_PATH.open(encoding="utf-8")):
        if r.get("result_available") != "True":
            continue
        dt = _d(r.get("match_date", ""))
        if not dt:
            continue
        try:
            hg, ag = int(r["home_goals_90"]), int(r["away_goals_90"])
        except (ValueError, KeyError):
            continue
        r["_dt"], r["_hg"], r["_ag"] = dt, hg, ag
        rows.append(r)
    rows.sort(key=lambda x: x["_dt"])
    return rows


def poisson_1x2(lh: float, la: float) -> tuple[float, float, float]:
    ph = [math.exp(-lh) * lh**k / math.factorial(k) for k in range(MAXG + 1)]
    pa = [math.exp(-la) * la**k / math.factorial(k) for k in range(MAXG + 1)]
    h = d = a = 0.0
    for i in range(MAXG + 1):
        for j in range(MAXG + 1):
            p = ph[i] * pa[j]
            if i > j:
                h += p
            elif i == j:
                d += p
            else:
                a += p
    s = h + d + a
    return h / s, d / s, a / s


def devig(oh, od, oa):
    inv = [1 / oh, 1 / od, 1 / oa]
    s = sum(inv)
    return inv[0] / s, inv[1] / s, inv[2] / s


def rps(p, oc):
    obs = {"H": (1, 0, 0), "D": (0, 1, 0), "A": (0, 0, 1)}[oc]
    cp, co = [p[0], p[0] + p[1]], [obs[0], obs[0] + obs[1]]
    return sum((cp[i] - co[i]) ** 2 for i in range(2))


def logloss(p, oc):
    return -math.log(max({"H": p[0], "D": p[1], "A": p[2]}[oc], 1e-12))


def brier(p, oc):
    obs = {"H": (1, 0, 0), "D": (0, 1, 0), "A": (0, 0, 1)}[oc]
    return sum((p[i] - obs[i]) ** 2 for i in range(3))


def outcome(hg, ag):
    return "H" if hg > ag else ("A" if ag > hg else "D")


def fit(train: list[dict[str, Any]], teams: dict[str, int]) -> dict[str, Any]:
    n_t = len(teams)
    hi = np.array([teams[r["home_team_id"]] for r in train])
    ai = np.array([teams[r["away_team_id"]] for r in train])
    kh = np.array([r["_hg"] for r in train], dtype=float)
    ka = np.array([r["_ag"] for r in train], dtype=float)
    nh = np.array([0.0 if r["neutral_site"] == "True" else 1.0 for r in train])
    last = max(r["_dt"] for r in train)
    lam_decay = math.log(2) / HALF_LIFE_DAYS
    w = np.array([math.exp(-lam_decay * (last - r["_dt"]).days) for r in train])
    N = len(train)

    atk = np.zeros(n_t)
    dfn = np.zeros(n_t)
    c = math.log(max(mean([*(kh), *(ka)]), 0.3))
    h = 0.2
    for _ in range(ITERS):
        eta_h = np.clip(c + h * nh + atk[hi] - dfn[ai], -2.5, 2.5)
        eta_a = np.clip(c + atk[ai] - dfn[hi], -2.5, 2.5)
        lh, la = np.exp(eta_h), np.exp(eta_a)
        rh = w * (lh - kh)
        ra = w * (la - ka)
        g_c = (rh.sum() + ra.sum()) / N
        g_h = (rh * nh).sum() / N
        g_atk = np.zeros(n_t)
        g_dfn = np.zeros(n_t)
        np.add.at(g_atk, hi, rh)
        np.add.at(g_atk, ai, ra)
        np.add.at(g_dfn, ai, -rh)
        np.add.at(g_dfn, hi, -ra)
        g_atk = g_atk / N + REG * atk / N
        g_dfn = g_dfn / N + REG * dfn / N
        c -= LR * g_c
        h -= LR * g_h
        atk -= LR * g_atk
        dfn -= LR * g_dfn
    return {"c": c, "h": h, "atk": atk, "dfn": dfn, "last": last}


def agg(items, key):
    return round(mean(x[key] for x in items), 4) if items else None


def main() -> int:
    if not CSV_PATH.is_file():
        raise SystemExit(f"dataset not found: {CSV_PATH} (run normalize_w1_international_dataset.py)")
    rows = load()
    n = len(rows)
    cut = int(n * 0.8)
    train, test = rows[:cut], rows[cut:]
    train_end = train[-1]["_dt"]
    test_start = test[0]["_dt"]
    teams = {t: i for i, t in enumerate(sorted({r["home_team_id"] for r in train} | {r["away_team_id"] for r in train}))}
    m = fit(train, teams)
    atk, dfn = m["atk"], m["dfn"]

    evals = []
    cold = 0
    for r in test:
        ht, at_ = r["home_team_id"], r["away_team_id"]
        if ht not in teams or at_ not in teams:
            cold += 1
            continue
        nh = 0.0 if r["neutral_site"] == "True" else 1.0
        lh = math.exp(min(2.5, m["c"] + m["h"] * nh + atk[teams[ht]] - dfn[teams[at_]]))
        la = math.exp(min(2.5, m["c"] + atk[teams[at_]] - dfn[teams[ht]]))
        pm = poisson_1x2(lh, la)
        oc = outcome(r["_hg"], r["_ag"])
        e = {"oc": oc, "model_rps": rps(pm, oc), "model_log": logloss(pm, oc), "model_brier": brier(pm, oc),
             "model_dir": ["H", "D", "A"][int(np.argmax(pm))] == oc, "uni_rps": rps((1/3, 1/3, 1/3), oc)}
        if r.get("odds_1x2_available") == "True":
            try:
                pk = devig(float(r["odds_1x2_home"]), float(r["odds_1x2_draw"]), float(r["odds_1x2_away"]))
                e.update({"mkt_rps": rps(pk, oc), "mkt_log": logloss(pk, oc),
                          "mkt_dir": ["H", "D", "A"][int(np.argmax(pk))] == oc, "has_mkt": True})
            except (ValueError, TypeError):
                e["has_mkt"] = False
        else:
            e["has_mkt"] = False
        evals.append(e)

    mk = [e for e in evals if e.get("has_mkt")]
    ratings = sorted(((t, float(atk[i] - dfn[i])) for t, i in teams.items()), key=lambda kv: kv[1], reverse=True)
    payload = {
        "schema_version": "W1_TEAM_STRENGTH_PROTOTYPE_V1",
        "prototype": True,
        "production_validated": False,
        "production_wired": False,
        "model": "time-decayed Poisson attack/defense + L2 shrinkage (independent Poisson 1X2)",
        "hyperparams": {"half_life_days": HALF_LIFE_DAYS, "l2_shrinkage": REG, "lr": LR, "iters": ITERS},
        "walk_forward": {
            "policy": "chronological 80/20; fit on train (all earlier than test), evaluate on later test (no future leakage)",
            "train_range": [str(train[0]["_dt"]), str(train_end)], "train_n": len(train),
            "test_range": [str(test_start), str(test[-1]["_dt"])], "test_n": len(test),
            "no_future_leakage": bool(train_end <= test_start),
            "cold_start_test_skipped": cold,
        },
        "test_metrics": {
            "n_evaluated": len(evals),
            "model": {"rps": agg(evals, "model_rps"), "logloss": agg(evals, "model_log"),
                      "brier": agg(evals, "model_brier"),
                      "direction_accuracy": round(mean(1.0 if e["model_dir"] else 0.0 for e in evals), 4) if evals else None,
                      "beats_uniform_rps": bool(agg(evals, "model_rps") < agg(evals, "uni_rps")) if evals else None},
            "market_on_same_subset": {"n": len(mk),
                                      "model_rps": round(mean(e["model_rps"] for e in mk), 4) if mk else None,
                                      "market_rps": round(mean(e["mkt_rps"] for e in mk), 4) if mk else None,
                                      "model_dir": round(mean(1.0 if e["model_dir"] else 0.0 for e in mk), 4) if mk else None,
                                      "market_dir": round(mean(1.0 if e["mkt_dir"] else 0.0 for e in mk), 4) if mk else None},
        },
        "host_fallback": {
            "hosts": sorted(HOSTS),
            "note_cn": "东道主无预选历史，评分仅来自少量正赛/友谊，置信低；不可当可靠强度，需后续补友谊赛/Elo。",
            "host_in_train": {h: (h in teams) for h in sorted(HOSTS)},
        },
        "ratings_top10": [{"team_id": t, "net_strength": round(v, 3)} for t, v in ratings[:10]],
        "ratings_bottom10": [{"team_id": t, "net_strength": round(v, 3)} for t, v in ratings[-10:]],
        "notes_cn": [
            "prototype：仅研究对照，不接入线上 λ，不改任何生产配置。",
            "结论看能否优于 uniform、能否接近市场；不得宣称跑赢市场或可生产。",
            "正式 S2 验收须等 S1B 数据增强(连续国际赛 + OU/AH)。",
            "不构成投注/资金建议，不承诺命中率。",
        ],
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _md(payload)
    tm = payload["test_metrics"]
    print(f"W1 strength prototype: train={len(train)} test={len(test)} "
          f"model_rps={tm['model']['rps']} (uniform beat={tm['model']['beats_uniform_rps']}) "
          f"market_rps={tm['market_on_same_subset']['market_rps']} model_rps_same={tm['market_on_same_subset']['model_rps']} "
          f"[prototype, not production]")
    return 0


def _md(p: dict[str, Any]) -> None:
    tm = p["test_metrics"]; ms = tm["market_on_same_subset"]; wf = p["walk_forward"]
    L = [
        "# W1 国家队强度模型 PROTOTYPE V1",
        "",
        "> prototype=`true` · production_validated=`false` · production_wired=`false`",
        "> 仅研究对照，不接入线上 λ，不改任何生产配置。",
        "",
        "## 模型",
        f"- {p['model']}；half_life={p['hyperparams']['half_life_days']}d，L2={p['hyperparams']['l2_shrinkage']}。",
        f"- walk-forward：train {wf['train_range']} (n={wf['train_n']}) → test {wf['test_range']} (n={wf['test_n']})，无未来泄漏={wf['no_future_leakage']}，cold-start 跳过 {wf['cold_start_test_skipped']}。",
        "",
        "## 测试集对照",
        f"- 强度模型：RPS {tm['model']['rps']}，方向 {tm['model']['direction_accuracy']}，优于 uniform={tm['model']['beats_uniform_rps']}。",
        f"- 同子集对照：模型 RPS {ms['model_rps']} vs 市场 RPS {ms['market_rps']}（n={ms['n']}）；方向 模型 {ms['model_dir']} vs 市场 {ms['market_dir']}。",
        "",
        "## 东道主 fallback",
        f"- {p['host_fallback']['note_cn']}",
        f"- 是否在训练集出现：{p['host_fallback']['host_in_train']}",
        "",
        "## 评分（净强度 atk−def，节选）",
        "Top：" + ", ".join(f"{r['team_id']} {r['net_strength']}" for r in p["ratings_top10"][:6]),
        "Bottom：" + ", ".join(f"{r['team_id']} {r['net_strength']}" for r in p["ratings_bottom10"][:6]),
        "",
        "## 边界",
        "- 不接线上预测；模型-市场差异仅作研究复核，不表述为投注机会。",
        "- 不构成投注/资金建议，不承诺命中率。正式 S2 验收须等 S1B 数据增强。",
        "",
    ]
    OUT_MD.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
