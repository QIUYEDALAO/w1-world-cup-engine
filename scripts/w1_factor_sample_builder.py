#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 FiveDim Historical Validation (Stage C) — leakage-safe factor sample builder.

Read-only, offline. Assembles one row per historical match with:
  - market-implied 1X2 probabilities (devig closing odds), and
  - PRE-MATCH-ONLY rolling factors (ELO, form, goal diff, shot-on-target rate, xG, rest days),
    each computed from a team's matches STRICTLY BEFORE the current kickoff,
  - the actual result as label y (never used as a feature).

No API, no model/lambda change, no factor coefficients. Output is gitignored.
Layers (league / wc_qualifier / wc_finals) are kept separate; never pooled or extrapolated.
"""
from __future__ import annotations

import glob
import json
import math
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "config/w1_factor_sample_policy.json").read_text(encoding="utf-8"))
N = POLICY["windows"]["primary_n"]
ELO = POLICY["elo"]
OUT_CSV = ROOT / POLICY["output"]
OUT_SUM = ROOT / POLICY["output_summary"]


def devig3(oh, od, oa):
    try:
        ih, idr, ia = 1.0 / float(oh), 1.0 / float(od), 1.0 / float(oa)
    except (TypeError, ValueError, ZeroDivisionError):
        return (None, None, None)
    s = ih + idr + ia
    if not (s > 0) or any(map(lambda x: not np.isfinite(x), (ih, idr, ia))):
        return (None, None, None)
    return (ih / s, idr / s, ia / s)


def devig2(oo, ou):
    try:
        io, iu = 1.0 / float(oo), 1.0 / float(ou)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    s = io + iu
    return io / s if s > 0 else None


def expected_home(elo_h, elo_a, hfa):
    return 1.0 / (1.0 + 10 ** ((elo_a - (elo_h + hfa)) / 400.0))


class Pool:
    """Per-pool team state: ELO, rolling history, last match date."""

    def __init__(self):
        self.elo = defaultdict(lambda: float(ELO["init"]))
        self.hist = defaultdict(lambda: deque(maxlen=N))  # each item: dict(pts,gd,sotr,xg)
        self.last_date = {}

    def roll(self, team):
        h = self.hist[team]
        n = len(h)
        if n == 0:
            return {"ppg": np.nan, "gd": np.nan, "sotr": np.nan, "xg": np.nan, "n": 0}
        ppg = np.mean([x["pts"] for x in h])
        gd = np.mean([x["gd"] for x in h])
        sotr_vals = [x["sotr"] for x in h if x["sotr"] is not None and np.isfinite(x["sotr"])]
        xg_vals = [x["xg"] for x in h if x["xg"] is not None and np.isfinite(x["xg"])]
        return {
            "ppg": ppg, "gd": gd,
            "sotr": np.mean(sotr_vals) if sotr_vals else np.nan,
            "xg": np.mean(xg_vals) if xg_vals else np.nan,
            "n": n,
        }

    def rest(self, team, date):
        prev = self.last_date.get(team)
        return (date - prev).days if prev is not None else np.nan

    def update(self, home, away, hg, ag, date, hfa, sotr_h=None, sotr_a=None, xg_h=None, xg_a=None):
        eh, ea = self.elo[home], self.elo[away]
        exp_h = expected_home(eh, ea, hfa)
        sh = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
        self.elo[home] = eh + ELO["k"] * (sh - exp_h)
        self.elo[away] = ea + ELO["k"] * ((1.0 - sh) - (1.0 - exp_h))
        self.hist[home].append({"pts": 3 if hg > ag else 1 if hg == ag else 0, "gd": hg - ag, "sotr": sotr_h, "xg": xg_h})
        self.hist[away].append({"pts": 3 if ag > hg else 1 if ag == hg else 0, "gd": ag - hg, "sotr": sotr_a, "xg": xg_a})
        self.last_date[home] = date
        self.last_date[away] = date


def _row(layer, league, season, date, home, away, neutral, market, p_over, pool, hg, ag):
    pH, pD, pA = market
    rh, ra = pool.roll(home), pool.roll(away)
    eh, ea = pool.elo[home], pool.elo[away]
    rest_h, rest_a = pool.rest(home, date), pool.rest(away, date)
    y = "H" if hg > ag else "D" if hg == ag else "A"

    def diff(a, b):
        return (a - b) if (a is not None and b is not None and np.isfinite(a) and np.isfinite(b)) else np.nan

    return {
        "layer": layer, "league": league, "season": season,
        "match_date": date.strftime("%Y-%m-%d"), "feature_asof": date.strftime("%Y-%m-%d"),
        "home": home, "away": away, "neutral": int(bool(neutral)),
        "pH": pH, "pD": pD, "pA": pA, "p_over25": p_over,
        "elo_home": round(eh, 2), "elo_away": round(ea, 2), "elo_diff": round(eh - ea, 2),
        "ppg_home": rh["ppg"], "ppg_away": ra["ppg"], "ppg_diff": diff(rh["ppg"], ra["ppg"]),
        "gd_home": rh["gd"], "gd_away": ra["gd"], "gd_diff": diff(rh["gd"], ra["gd"]),
        "sotr_home": rh["sotr"], "sotr_away": ra["sotr"], "sotr_diff": diff(rh["sotr"], ra["sotr"]),
        "xg_home": rh["xg"], "xg_away": ra["xg"], "xg_diff": diff(rh["xg"], ra["xg"]),
        "rest_home": rest_h, "rest_away": rest_a, "rest_diff": diff(rest_h, rest_a),
        "n_hist_home": rh["n"], "n_hist_away": ra["n"],
        "low_history": int(rh["n"] < POLICY["windows"]["min_history"] or ra["n"] < POLICY["windows"]["min_history"]),
        "y": y, "total_goals": int(hg + ag), "independent_edge": False,
    }


def build_league():
    rows = []
    pools = defaultdict(Pool)  # per Div
    frames = []
    for fp in sorted(glob.glob(str(ROOT / "data/historical/raw/football-data/*.csv"))):
        name = Path(fp).stem  # e.g. E0_2526
        div, season = name.split("_", 1)
        df = pd.read_csv(fp)
        df["__div"], df["__season"], df["__date"] = div, season, pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
        frames.append(df)
    allm = pd.concat(frames, ignore_index=True)
    allm = allm.dropna(subset=["__date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]).sort_values("__date")
    for _, r in allm.iterrows():
        div = r["__div"]
        pool = pools[div]
        home, away = str(r["HomeTeam"]), str(r["AwayTeam"])
        hg, ag = int(r["FTHG"]), int(r["FTAG"])
        market = devig3(r.get("AvgH"), r.get("AvgD"), r.get("AvgA"))
        if market[0] is None:
            market = devig3(r.get("B365H"), r.get("B365D"), r.get("B365A"))
        p_over = devig2(r.get("Avg>2.5"), r.get("Avg<2.5"))
        rows.append(_row("league", div, r["__season"], r["__date"], home, away, False, market, p_over, pool, hg, ag))
        # update AFTER emit (current match never in its own features)
        hs, as_, hst, ast = r.get("HS"), r.get("AS"), r.get("HST"), r.get("AST")
        sotr_h = (hst / hs) if (pd.notna(hs) and pd.notna(hst) and hs > 0) else None
        sotr_a = (ast / as_) if (pd.notna(as_) and pd.notna(ast) and as_ > 0) else None
        pool.update(home, away, hg, ag, r["__date"], ELO["home_field_advantage_elo"], sotr_h, sotr_a)
    return rows


def build_international():
    fp = ROOT / "data/processed/international/w1_international_dataset_extended.csv"
    df = pd.read_csv(fp)
    df["__date"] = pd.to_datetime(df["match_date"], errors="coerce")
    df = df.dropna(subset=["__date", "home_goals_90", "away_goals_90"]).sort_values("__date")
    pool = Pool()  # single international pool
    rows = []
    for _, r in df.iterrows():
        comp = str(r.get("competition", ""))
        phase = str(r.get("phase", ""))
        layer = "wc_finals" if phase == "finals" else "wc_qualifier" if "Qualifier" in comp else "international_other"
        home = str(r.get("home_team_id") or r.get("home_name_raw"))
        away = str(r.get("away_team_id") or r.get("away_name_raw"))
        try:
            hg, ag = int(r["home_goals_90"]), int(r["away_goals_90"])
        except (TypeError, ValueError):
            continue
        neutral = bool(r.get("neutral_site")) and str(r.get("neutral_site")).lower() not in ("false", "0", "")
        hfa = ELO["neutral_hfa"] if neutral else ELO["home_field_advantage_elo"]
        market = devig3(r.get("odds_1x2_home"), r.get("odds_1x2_draw"), r.get("odds_1x2_away"))
        p_over = devig2(r.get("ou_O25"), r.get("ou_U25"))
        rows.append(_row(layer, "international", "", r["__date"], home, away, neutral, market, p_over, pool, hg, ag))
        xg_ok = str(r.get("xg_available")).lower() == "true"
        xg_h = float(r["home_xg"]) if xg_ok and pd.notna(r.get("home_xg")) else None
        xg_a = float(r["away_xg"]) if xg_ok and pd.notna(r.get("away_xg")) else None
        hs, as_, hst, ast = r.get("home_shots"), r.get("away_shots"), r.get("home_sot"), r.get("away_sot")
        sotr_h = (hst / hs) if (pd.notna(hs) and pd.notna(hst) and hs > 0) else None
        sotr_a = (ast / as_) if (pd.notna(as_) and pd.notna(ast) and as_ > 0) else None
        pool.update(home, away, hg, ag, r["__date"], hfa, sotr_h, sotr_a, xg_h, xg_a)
    return rows


def main() -> int:
    rows = build_league() + build_international()
    df = pd.DataFrame(rows)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    summary = {
        "stage": "W1_FIVEDIM_HISTORICAL_VALIDATION_C",
        "research_only": True, "production_wired": False, "external_fetch_performed": False,
        "independent_edge_claimed": False,
        "n_rows": int(len(df)),
        "by_layer": {k: int(v) for k, v in df["layer"].value_counts().to_dict().items()},
        "market_coverage": {
            "rows_with_market": int(df["pH"].notna().sum()),
            "rows_with_xg_diff": int(df["xg_diff"].notna().sum()),
        },
        "feature_columns": ["elo_diff", "ppg_diff", "gd_diff", "sotr_diff", "xg_diff", "rest_diff"],
        "output": str(OUT_CSV.relative_to(ROOT)),
    }
    OUT_SUM.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"factor sample built: rows={len(df)} by_layer={summary['by_layer']} -> {OUT_CSV.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
