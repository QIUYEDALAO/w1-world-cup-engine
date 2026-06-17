#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 FiveDim Historical Validation (Stage C) — does a factor add info BEYOND the market?

Research only. For each layer, fit a multinomial-logistic model on a TRAIN split and
evaluate on a held-out split:
  M0 baseline = intercepts + market log-odds (recovers the market)
  M1          = M0 + one candidate factor (standardized on train)
Negative holdout Δlog-loss / ΔRPS means the factor carries incremental signal the
market had not already priced. Layers are never pooled; finals (n=192) is flagged low-power.

No model/lambda change, no API, no coefficients written to production.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "state/w1_factor_validation_sample.csv"
OUT = ROOT / "state/w1_factor_validation_results.json"
MINH = 3
FACTORS = ["elo_diff", "ppg_diff", "gd_diff", "sotr_diff", "xg_diff", "rest_diff"]
RNG = np.random.default_rng(0)


def fit_softmax(X, y, l2=1.0, lr=0.5, iters=4000):
    n, d = X.shape
    W = np.zeros((d, 3))
    Y = np.eye(3)[y]
    for _ in range(iters):
        Z = X @ W
        Z -= Z.max(1, keepdims=True)
        P = np.exp(Z)
        P /= P.sum(1, keepdims=True)
        grad = X.T @ (P - Y) / n + l2 * W / n
        grad[0] -= l2 * W[0] / n  # do not regularize intercept
        W -= lr * grad
    return W


def predict(W, X):
    Z = X @ W
    Z -= Z.max(1, keepdims=True)
    P = np.exp(Z)
    return P / P.sum(1, keepdims=True)


def logloss(P, y):
    return float(-np.mean(np.log(np.clip(P[np.arange(len(y)), y], 1e-9, 1))))


def rps(P, y):
    Y = np.eye(3)[y]
    return float(np.mean(np.sum((np.cumsum(P, 1) - np.cumsum(Y, 1)) ** 2, 1) / 2))


def standardize(train, full):
    mu, sd = np.nanmean(train, 0), np.nanstd(train, 0)
    sd = np.where(sd < 1e-9, 1.0, sd)
    return (full - mu) / sd


def split_mask(g):
    layer = g["layer"].iloc[0]
    if layer == "league":
        sn = pd.to_numeric(g["season"], errors="coerce")
        return sn.isin([2021, 2122, 2223, 2324]).values
    # international: chronological 70/30 by date
    order = g["match_date"].rank(method="first")
    return (order <= 0.7 * len(g)).values


def market_logits(g):
    pH = np.clip(g["pH"].values, 1e-6, 1)
    pD = np.clip(g["pD"].values, 1e-6, 1)
    pA = np.clip(g["pA"].values, 1e-6, 1)
    return np.column_stack([np.log(pH / pD), np.log(pA / pD)])


def eval_layer(g):
    g = g.dropna(subset=["pH", "pD", "pA", "y"]).copy()
    g = g[g["n_hist_home"].fillna(0) >= MINH]
    g = g[g["n_hist_away"].fillna(0) >= MINH]
    ymap = {"H": 0, "D": 1, "A": 2}
    y = g["y"].map(ymap).values
    tr = split_mask(g)
    base = market_logits(g)
    out = {"n": int(len(g)), "n_train": int(tr.sum()), "n_test": int((~tr).sum()),
           "market_holdout_logloss": None, "factors": {}}
    if (~tr).sum() < 25 or tr.sum() < 50:
        out["note"] = "insufficient split"
        return out

    def design(extra_cols):
        cols = [base]
        if extra_cols is not None:
            cols.append(extra_cols)
        Z = np.column_stack(cols)
        Zs = standardize(Z[tr], Z)
        return np.column_stack([np.ones(len(Z)), Zs])

    # M0 baseline (market only)
    X0 = design(None)
    W0 = fit_softmax(X0[tr], y[tr])
    P0 = predict(W0, X0[~tr])
    out["market_holdout_logloss"] = round(logloss(P0, y[~tr]), 4)
    out["market_holdout_rps"] = round(rps(P0, y[~tr]), 4)

    for f in FACTORS:
        col = g[f].values.astype(float)
        ok = np.isfinite(col)
        if ok.sum() < 60 or (ok & ~tr).sum() < 20 or (ok & tr).sum() < 40:
            out["factors"][f] = {"status": "insufficient_data", "n_usable": int(ok.sum())}
            continue
        sub = ok
        ytr_s, yte_s = y[sub & tr], y[sub & ~tr]
        b_sub = market_logits(g.iloc[np.where(sub)[0]])  # not used; keep simple below
        # build designs on the sub rows, standardized on sub-train
        baseS = base[sub]
        colS = col[sub]
        trS = tr[sub]
        Zb = standardize(baseS[trS], baseS)
        Xb = np.column_stack([np.ones(sub.sum()), Zb])
        Zf = standardize(np.column_stack([baseS, colS])[trS], np.column_stack([baseS, colS]))
        Xf = np.column_stack([np.ones(sub.sum()), Zf])
        W0s = fit_softmax(Xb[trS], ytr_s)
        W1s = fit_softmax(Xf[trS], ytr_s)
        ll0 = logloss(predict(W0s, Xb[~trS]), yte_s)
        ll1 = logloss(predict(W1s, Xf[~trS]), yte_s)
        r0 = rps(predict(W0s, Xb[~trS]), yte_s)
        r1 = rps(predict(W1s, Xf[~trS]), yte_s)
        out["factors"][f] = {
            "n_usable": int(ok.sum()), "n_test": int((sub & ~tr).sum()),
            "baseline_logloss": round(ll0, 4), "with_factor_logloss": round(ll1, 4),
            "delta_logloss": round(ll1 - ll0, 4),
            "delta_rps": round(r1 - r0, 4),
            "improves": bool(ll1 < ll0 - 1e-4),
        }
    return out


def main() -> int:
    df = pd.read_csv(SAMPLE)
    results = {"stage": "W1_FIVEDIM_HISTORICAL_VALIDATION_C", "research_only": True,
               "production_wired": False, "independent_edge_claimed": False,
               "method": "multinomial logistic, holdout Δlog-loss vs market baseline; layers separate",
               "layers": {}}
    for layer in ["league", "wc_qualifier", "wc_finals"]:
        g = df[df["layer"] == layer]
        if len(g):
            results["layers"][layer] = eval_layer(g)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # console table
    for layer, r in results["layers"].items():
        print(f"\n== {layer}  n={r.get('n')} test={r.get('n_test')}  market_holdout_logloss={r.get('market_holdout_logloss')} ==")
        if "note" in r:
            print("   ", r["note"]); continue
        for f, fr in r["factors"].items():
            if fr.get("status") == "insufficient_data":
                print(f"   {f:10} insufficient (n_usable={fr['n_usable']})")
            else:
                flag = "IMPROVES" if fr["improves"] else "no gain"
                print(f"   {f:10} Δlogloss={fr['delta_logloss']:+.4f} Δrps={fr['delta_rps']:+.4f}  [{flag}]  (test n={fr['n_test']})")
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
