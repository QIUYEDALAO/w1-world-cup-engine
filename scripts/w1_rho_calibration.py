#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
W1 Dixon-Coles rho 校准(市场条件 rho / market-conditioned MLE)
===============================================================
与生产同管线: lambda 仍由市场反解(收盘 1X2 + 收盘 OU -> mu -> delta -> lambda),
rho 用极大似然拟合【实际比分】。产出: 全局 rho_hat + CI + 可靠性诊断 + 市场基线对照。

【关键纪律】
- 只拟合【一个】全局 rho(二阶稳定参数), 不分桶拟合。
- 不用世界杯进行中的数据估 rho; 用大样本历史(几百~两千+场)。
- 拟合结果只用来替换 w1_score_engine.DEFAULT_RHO 这一个常数, 不改其它逻辑。

CSV 字段在 REQUIRED_COLUMNS / OPTIONAL_COLUMNS 中【定死】并强制校验。
依赖: numpy / scipy(必需), matplotlib(可选, 仅画图), w1_score_engine(同目录)。
边界: 研究/校准工具, 不构成投注或资金操作意见。
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import struct
import sys
import zlib
from pathlib import Path
from typing import Any

import numpy as np

try:
    from scipy.optimize import brentq, minimize_scalar
    from scipy.stats import poisson
except ModuleNotFoundError:
    class _PoissonFallback:
        @staticmethod
        def cdf(k: int, mu: float) -> float:
            term = math.exp(-mu)
            total = term
            for n in range(1, k + 1):
                term *= mu / n
                total += term
            return total

    class _MinimizeResult:
        def __init__(self, x: float, fun: float):
            self.x = x
            self.fun = fun

    def brentq(func, lo: float, hi: float, xtol: float = 1e-4, maxiter: int = 100):
        flo, fhi = func(lo), func(hi)
        if flo == 0:
            return lo
        if fhi == 0:
            return hi
        if flo * fhi > 0:
            raise ValueError("fallback brentq requires a sign change")
        for _ in range(maxiter):
            mid = (lo + hi) / 2.0
            fmid = func(mid)
            if abs(fmid) <= xtol or (hi - lo) / 2.0 <= xtol:
                return mid
            if flo * fmid <= 0:
                hi, fhi = mid, fmid
            else:
                lo, flo = mid, fmid
        return (lo + hi) / 2.0

    def minimize_scalar(func, args=(), bounds=None, method=None, options=None):
        if bounds is None:
            raise ValueError("fallback minimize_scalar requires bounds")
        lo, hi = bounds
        tol = (options or {}).get("xatol", 1e-4)
        invphi = (math.sqrt(5) - 1) / 2
        invphi2 = (3 - math.sqrt(5)) / 2
        a, b = float(lo), float(hi)
        h = b - a
        c = a + invphi2 * h
        d = a + invphi * h
        yc = func(c, *args)
        yd = func(d, *args)
        while h > tol:
            if yc < yd:
                b, d, yd = d, c, yc
                h = invphi * h
                c = a + invphi2 * h
                yc = func(c, *args)
            else:
                a, c, yc = c, d, yd
                h = invphi * h
                d = a + invphi * h
                yd = func(d, *args)
        x = (a + b) / 2.0
        return _MinimizeResult(x, func(x, *args))

    poisson = _PoissonFallback()

sys.path.insert(0, str(Path(__file__).resolve().parent))
import w1_score_engine as E  # noqa: E402

# ===========================================================================
# 0. CSV SCHEMA —— 字段定死
# ===========================================================================
# 拟合 rho 严格【必需】的列。缺任一列 -> 直接报错退出。
REQUIRED_COLUMNS: dict[str, str] = {
    "match_date":          "比赛日期 YYYY-MM-DD(排序/溯源)",
    "home_team":           "主队名(连接/去重)",
    "away_team":           "客队名",
    "closing_home_odds":   "收盘 1X2 主胜 小数赔率 (>1)",
    "closing_draw_odds":   "收盘 1X2 平 小数赔率 (>1)",
    "closing_away_odds":   "收盘 1X2 客胜 小数赔率 (>1)",
    "closing_ou_main_line":"收盘 大小球主盘口线, 半盘(如 2.5)",
    "closing_over_odds":   "收盘 大球 小数赔率 (>1)",
    "closing_under_odds":  "收盘 小球 小数赔率 (>1)",
    "home_goals":          "终场主队进球 整数 (>=0)",
    "away_goals":          "终场客队进球 整数 (>=0)",
}
# 现在【一起记录】、但【不进 rho 拟合】的列。用于日后分桶诊断与战术层实证。
# 缺失只 WARN, 不报错。
OPTIONAL_COLUMNS: dict[str, str] = {
    "market_snapshot_lead_minutes": "收盘快照距开球分钟数(早盘/临场分桶, 判战术层是否有立足点)",
    "competition":                  "赛事类型(国际/联赛/杯赛)",
    "neutral_venue":                "是否中立场 0/1",
    "lineup_completeness":          "首发完整度 full/key_missing/unknown(实证战术层的关键桶)",
    "closing_ah_main_line":         "收盘 AH 主盘口线, 主队视角带符号(仅交叉验证, 不入拟合)",
    "closing_fair_total_override":  "若数据方直接给公允总进球, 用它替代从 OU 反解 mu",
    "bookmaker_count":              "盘口 bookmaker 数(线质量)",
}

# rho 搜索区间: 经验上 rho 为小负数; 限制在此区间可保证 Dixon-Coles tau 对常见 lambda 恒正。
RHO_BOUNDS = (-0.20, 0.05)


def is_synthetic(rows: list[dict]) -> bool:
    """检测输入是否为合成数据(生成器写 competition=SYNTH)。防合成 rho 进生产。"""
    return sum(1 for r in rows if r.get("competition", "").upper() == "SYNTH") > len(rows) // 2


# ===========================================================================
# 1. CSV 读取 + 强制校验
# ===========================================================================
class SchemaError(Exception):
    pass


def _to_float(v: str, col: str, row_no: int, gt1: bool = False) -> float:
    x = float(v)
    if gt1 and x <= 1.0:
        raise ValueError(f"row{row_no} {col}={x} 应为 >1 的小数赔率")
    return x


def load_history(csv_path: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """读 CSV, 校验 schema, 返回 (有效行, 统计)。无效行记录原因并丢弃。"""
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        missing = [c for c in REQUIRED_COLUMNS if c not in header]
        if missing:
            raise SchemaError(f"CSV 缺必需列: {missing}\n必需列: {list(REQUIRED_COLUMNS)}")
        missing_opt = [c for c in OPTIONAL_COLUMNS if c not in header]
        rows: list[dict[str, Any]] = []
        dropped: list[tuple[int, str]] = []
        for i, raw in enumerate(reader, start=2):  # 行号含表头
            try:
                h = int(float(raw["home_goals"]))
                a = int(float(raw["away_goals"]))
                if h < 0 or a < 0:
                    raise ValueError(f"row{i} 进球为负")
                ou_line = _to_float(raw["closing_ou_main_line"], "closing_ou_main_line", i)
                rec = {
                    "match_date": raw["match_date"].strip(),
                    "home_team": raw["home_team"].strip(),
                    "away_team": raw["away_team"].strip(),
                    "odds_1x2": (
                        _to_float(raw["closing_home_odds"], "closing_home_odds", i, True),
                        _to_float(raw["closing_draw_odds"], "closing_draw_odds", i, True),
                        _to_float(raw["closing_away_odds"], "closing_away_odds", i, True),
                    ),
                    "ou_line": ou_line,
                    "over": _to_float(raw["closing_over_odds"], "closing_over_odds", i, True),
                    "under": _to_float(raw["closing_under_odds"], "closing_under_odds", i, True),
                    "home_goals": h,
                    "away_goals": a,
                    # 可选字段透传(可能为空)
                    "fair_total_override": raw.get("closing_fair_total_override") or "",
                    "lineup_completeness": (raw.get("lineup_completeness") or "").strip(),
                    "lead_minutes": raw.get("market_snapshot_lead_minutes") or "",
                    "competition": (raw.get("competition") or "").strip(),
                }
                rows.append(rec)
            except (ValueError, KeyError) as exc:
                dropped.append((i, str(exc)))
        stats = {"read": i - 1 if rows or dropped else 0, "valid": len(rows),
                 "dropped": len(dropped), "missing_optional": len(missing_opt)}
        if dropped[:5]:
            for ln, why in dropped[:5]:
                print(f"  [drop] {why}", file=sys.stderr)
        if missing_opt:
            print(f"  [warn] 缺可选列(不影响 rho 拟合, 影响日后分桶): {missing_opt}", file=sys.stderr)
        return rows, stats


# ===========================================================================
# 2. mu 反解: 主盘半线 + 去水大球概率 -> 期望总进球(Poisson 总和反演)
# ===========================================================================
def mu_from_main_ou(line: float, over: float, under: float) -> float:
    """
    给定主盘半线 L=k+0.5 与去水 P(over)=P(total>=k+1), 在 total~Poisson(mu) 假设下反解 mu。
    (DC 低分修正是高阶扰动, 对 2.5 线反解 mu 影响可忽略。)
    """
    p_over = E.devig_two_way(over, under)
    k = math.floor(line)  # 半线 2.5 -> 越过 2, 即 total>=3
    # P(Poisson(mu) >= k+1) = 1 - cdf(k) = p_over; mu 单调增 -> p 单调增
    def f(mu: float) -> float:
        return (1.0 - poisson.cdf(k, mu)) - p_over
    lo, hi = 1e-3, 12.0
    if f(lo) > 0:  # 概率过高, 钳到下界
        return lo
    if f(hi) < 0:
        return hi
    return float(brentq(f, lo, hi, xtol=1e-4))


def row_mu(rec: dict[str, Any]) -> float:
    if rec["fair_total_override"]:
        try:
            return float(rec["fair_total_override"])
        except ValueError:
            pass
    return mu_from_main_ou(rec["ou_line"], rec["over"], rec["under"])


# ===========================================================================
# 3. 每行 lambda(市场反解, 与生产同函数)
# ===========================================================================
# 3. 每行 lambda 缓存(lambda 只依赖市场, 与 rho 解耦; 两遍精修消除耦合偏差)
# ===========================================================================
def cache_lambdas(rows: list[dict[str, Any]], rho: float) -> None:
    for rec in rows:
        p1x2 = E.devig_proportional(list(rec["odds_1x2"]))
        lh, la, _, _ = E.solve_lambdas(tuple(p1x2), rec["_mu"], rho)
        rec["_lh"], rec["_la"] = lh, la


# ===========================================================================
# 4. 全局 rho 的极大似然(用缓存 lambda, 不在似然内重解)
# ===========================================================================
def nll_cached(rho: float, rows: list[dict[str, Any]], max_goals: int) -> float:
    total = 0.0
    for rec in rows:
        M = E.score_matrix(rec["_lh"], rec["_la"], rho, max_goals)
        h, a = rec["home_goals"], rec["away_goals"]
        p = M[h, a] if (h < M.shape[0] and a < M.shape[1]) else 0.0
        total -= math.log(max(p, 1e-15))
    return total


def fit_rho(rows: list[dict[str, Any]], max_goals: int) -> tuple[float, float, float, float]:
    """两遍: 先 lambda@0 拟 rho, 再 lambda@rho1 精修。返回 (rho_hat, nll_hat, nll_zero, se)。"""
    cache_lambdas(rows, 0.0)
    nll_zero = nll_cached(0.0, rows, max_goals)            # 独立 Poisson 基线(lambda@0)
    r1 = minimize_scalar(nll_cached, args=(rows, max_goals),
                         bounds=RHO_BOUNDS, method="bounded", options={"xatol": 1e-4}).x
    cache_lambdas(rows, float(r1))                          # 用 rho1 重解 lambda 精修
    res = minimize_scalar(nll_cached, args=(rows, max_goals),
                          bounds=RHO_BOUNDS, method="bounded", options={"xatol": 1e-4})
    rho_hat, nll_hat = float(res.x), float(res.fun)
    cache_lambdas(rows, rho_hat)                            # 下游统一用 lambda@rho_hat
    h = 0.01
    f_p = nll_cached(min(rho_hat + h, RHO_BOUNDS[1] - 1e-4), rows, max_goals)
    f_m = nll_cached(max(rho_hat - h, RHO_BOUNDS[0] + 1e-4), rows, max_goals)
    curv = (f_p - 2 * nll_hat + f_m) / (h * h)
    se = float(1.0 / math.sqrt(curv)) if curv > 0 else float("nan")
    return rho_hat, nll_hat, nll_zero, se


def bootstrap_rho(rows: list[dict[str, Any]], max_goals: int, B: int, seed: int = 0):
    """条件 bootstrap: lambda 固定(已缓存 @rho_hat), 仅重采样比赛重拟 rho。

    In environments without scipy this needs to stay lightweight for 10k+ rows, so
    bootstrap uses a dense rho grid and weighted likelihood over resampled counts.
    """
    rng = np.random.default_rng(seed)
    n = len(rows)
    grid = np.linspace(RHO_BOUNDS[0], RHO_BOUNDS[1], 101)
    log_probs = np.zeros((len(grid), n), dtype=float)
    for g_idx, rho in enumerate(grid):
        for r_idx, rec in enumerate(rows):
            M = E.score_matrix(rec["_lh"], rec["_la"], float(rho), max_goals)
            h, a = rec["home_goals"], rec["away_goals"]
            p = M[h, a] if (h < M.shape[0] and a < M.shape[1]) else 0.0
            p = float(p) if math.isfinite(float(p)) and float(p) > 0 else 1e-15
            log_probs[g_idx, r_idx] = math.log(max(p, 1e-15))
    floor_log = math.log(1e-15)
    log_probs = np.nan_to_num(log_probs, nan=floor_log, neginf=floor_log, posinf=floor_log)
    est = []
    for _ in range(B):
        idx = rng.integers(0, n, size=n)
        counts = np.bincount(idx, minlength=n).astype(float)
        nll = -np.sum(log_probs * counts[None, :], axis=1)
        est.append(float(grid[int(np.argmin(nll))]))
    return float(np.percentile(est, 2.5)), float(np.percentile(est, 97.5))


# ===========================================================================
# 5. 诊断: 可靠性 + 市场基线(均用缓存 lambda@rho_hat)
# ===========================================================================
def reliability_1x2(rows, rho, max_goals, n_bins=5):
    preds, obs = [], []
    for rec in rows:
        M = E.score_matrix(rec["_lh"], rec["_la"], rho, max_goals)
        ph, _, _ = E.hda_from_matrix(M)
        preds.append(ph)
        obs.append(1.0 if rec["home_goals"] > rec["away_goals"] else 0.0)
    preds, obs = np.array(preds), np.array(obs)
    edges = np.linspace(0, 1, n_bins + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (preds >= lo) & (preds < hi if hi < 1 else preds <= hi)
        if m.sum() > 0:
            out.append((float(preds[m].mean()), float(obs[m].mean()), int(m.sum())))
    return out


def reliability_total(rows, rho, max_goals):
    thresholds = [1.5, 2.5, 3.5, 4.5]
    acc = {t: [] for t in thresholds}; emp = {t: [] for t in thresholds}
    for rec in rows:
        M = E.score_matrix(rec["_lh"], rec["_la"], rho, max_goals)
        tot = np.add.outer(np.arange(M.shape[0]), np.arange(M.shape[1]))
        at = rec["home_goals"] + rec["away_goals"]
        for t in thresholds:
            acc[t].append(float(M[tot > t].sum())); emp[t].append(1.0 if at > t else 0.0)
    return {t: (float(np.mean(acc[t])), float(np.mean(emp[t])), len(acc[t])) for t in thresholds}


def baseline_compare(rows, rho, max_goals):
    rps_model, rps_market, rps_unif, ll_hat, ll_zero = [], [], [], [], []
    for rec in rows:
        oc = E.outcome_of(rec["home_goals"], rec["away_goals"])
        market_p = tuple(E.devig_proportional(list(rec["odds_1x2"])))
        M = E.score_matrix(rec["_lh"], rec["_la"], rho, max_goals)
        model_p = E.hda_from_matrix(M)
        rps_model.append(E.rps_hda(model_p, oc)); rps_market.append(E.rps_hda(market_p, oc))
        rps_unif.append(E.rps_hda((1 / 3, 1 / 3, 1 / 3), oc))
        ll_hat.append(E.log_score_exact(M, rec["home_goals"], rec["away_goals"]))
        lh0, la0, _, _ = E.solve_lambdas(market_p, rec["_mu"], 0.0)
        M0 = E.score_matrix(lh0, la0, 0.0, max_goals)
        ll_zero.append(E.log_score_exact(M0, rec["home_goals"], rec["away_goals"]))
    return {"rps_model": float(np.mean(rps_model)), "rps_market": float(np.mean(rps_market)),
            "rps_uniform": float(np.mean(rps_unif)),
            "logloss_rho_hat": float(np.mean(ll_hat)), "logloss_rho_zero": float(np.mean(ll_zero))}


# ===========================================================================
def write_plot(rho_hat: float, rows: list[dict[str, Any]], rel_tot, max_goals: int, out_png: Path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return write_plot_fallback(rho_hat, rows, rel_tot, max_goals, out_png)
    rhos = np.linspace(RHO_BOUNDS[0], RHO_BOUNDS[1], 25)
    nlls = [nll_cached(r, rows, max_goals) for r in rhos]
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    ax[0].plot(rhos, nlls, lw=2)
    ax[0].axvline(rho_hat, color="crimson", ls="--", label=f"rho_hat={rho_hat:.3f}")
    ax[0].axvline(0, color="gray", ls=":", label="rho=0 (indep)")
    ax[0].set_xlabel("rho"); ax[0].set_ylabel("negative log-likelihood")
    ax[0].set_title("rho MLE curve"); ax[0].legend()
    thr = list(rel_tot.keys())
    pred = [rel_tot[t][0] for t in thr]; emp = [rel_tot[t][1] for t in thr]
    ax[1].plot([0, 1], [0, 1], color="gray", ls=":", label="perfect")
    ax[1].scatter(pred, emp, s=60, color="seagreen")
    for t, p, e in zip(thr, pred, emp):
        ax[1].annotate(f"≥{t+0.5:.0f}", (p, e), textcoords="offset points", xytext=(6, -2), fontsize=8)
    ax[1].set_xlabel("predicted P(total>thr)"); ax[1].set_ylabel("empirical freq")
    ax[1].set_title("total-goals tail reliability"); ax[1].set_xlim(0, 1); ax[1].set_ylim(0, 1)
    ax[1].legend()
    fig.tight_layout(); fig.savefig(out_png, dpi=110); plt.close(fig)
    return True


def write_plot_fallback(rho_hat: float, rows: list[dict[str, Any]], rel_tot, max_goals: int, out_png: Path) -> bool:
    width, height = 1200, 500
    pixels = bytearray([255, 255, 255] * width * height)

    def put(x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < width and 0 <= y < height:
            idx = (y * width + x) * 3
            pixels[idx:idx + 3] = bytes(color)

    def line(x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            put(x0, y0, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def circle(cx: int, cy: int, r: int, color: tuple[int, int, int]) -> None:
        for x in range(cx - r, cx + r + 1):
            for y in range(cy - r, cy + r + 1):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    put(x, y, color)

    left = (70, 40, 560, 440)
    right = (670, 40, 1160, 440)
    black, blue, red, green, gray = (0, 0, 0), (31, 119, 180), (220, 20, 60), (46, 139, 87), (150, 150, 150)
    for box in (left, right):
        x0, y0, x1, y1 = box
        line(x0, y1, x1, y1, black)
        line(x0, y0, x0, y1, black)
    rhos = np.linspace(RHO_BOUNDS[0], RHO_BOUNDS[1], 50)
    nlls = [nll_cached(float(r), rows, max_goals) for r in rhos]
    nmin, nmax = min(nlls), max(nlls)

    def map_left(r: float, nll: float) -> tuple[int, int]:
        x0, y0, x1, y1 = left
        x = x0 + int((r - RHO_BOUNDS[0]) / (RHO_BOUNDS[1] - RHO_BOUNDS[0]) * (x1 - x0))
        y = y1 - int((nll - nmin) / max(nmax - nmin, 1e-9) * (y1 - y0))
        return x, y

    pts = [map_left(float(r), float(n)) for r, n in zip(rhos, nlls)]
    for a, b in zip(pts, pts[1:]):
        line(a[0], a[1], b[0], b[1], blue)
    rx, _ = map_left(rho_hat, nmin)
    line(rx, left[1], rx, left[3], red)
    zx, _ = map_left(0.0, nmin)
    line(zx, left[1], zx, left[3], gray)

    x0, y0, x1, y1 = right
    line(x0, y1, x1, y0, gray)
    for _, (pred, emp, _) in rel_tot.items():
        x = x0 + int(float(pred) * (x1 - x0))
        y = y1 - int(float(emp) * (y1 - y0))
        circle(x, y, 6, green)

    out_png.parent.mkdir(parents=True, exist_ok=True)
    scanlines = bytearray()
    stride = width * 3
    for y in range(height):
        scanlines.append(0)
        start = y * stride
        scanlines.extend(pixels[start:start + stride])

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(scanlines), 9))
        + chunk(b"IEND", b"")
    )
    out_png.write_bytes(png)
    return True


def write_report(path: Path, csv_path: Path, stats, rho_hat, nll_hat, nll_zero, se,
                 ci, rel_1x2, rel_tot, base, max_goals, plot_ok, synthetic_note: str,
                 production_ready: bool, synthetic: bool, rps_gap: float, min_prod_sample: int):
    L: list[str] = []
    w = L.append
    w("# W1 Dixon-Coles rho 校准报告")
    w("")
    w(f"- 生成时间: {dt.datetime.now():%Y-%m-%d %H:%M:%S}")
    w(f"- 输入 CSV: `{csv_path}`")
    w(f"- 样本: 读取 {stats['read']} / 有效 {stats['valid']} / 丢弃 {stats['dropped']}")
    w(f"- 方法: 市场条件 rho(lambda 由收盘 1X2+OU 反解, rho 对实际比分 MLE), max_goals={max_goals}")
    if synthetic_note:
        w(f"- ⚠️ {synthetic_note}")
    w("- 边界: 研究/校准工具, 不构成投注或资金操作意见。")
    w("")
    w("## 0. 生产可用性(机器可读, checker 据此放行)")
    w("")
    w(f"PRODUCTION_READY: {'YES' if production_ready else 'NO'}")
    w(f"INPUT_SYNTHETIC: {'YES' if synthetic else 'NO'}")
    w(f"VALID_SAMPLE: {stats['valid']}")
    w(f"MIN_PROD_SAMPLE: {min_prod_sample}")
    w(f"RPS_GAP_MODEL_MINUS_MARKET: {rps_gap:.4f}")
    w(f"RHO_HAT: {rho_hat:.4f}")
    w("")
    if not production_ready:
        reasons = []
        if synthetic:
            reasons.append("输入为合成数据")
        if stats["valid"] < min_prod_sample:
            reasons.append(f"样本{stats['valid']}<{min_prod_sample}")
        if rps_gap >= 0.01:
            reasons.append(f"模型-市场RPS差{rps_gap:.3f}过大(反解/去水可疑)")
        w(f"> ❌ **不可写入生产 DEFAULT_RHO**, 原因: {', '.join(reasons) or '见下文'}。")
    else:
        w("> ✅ 满足写入生产前置条件; 仍需人工在独立 commit 中【只改 DEFAULT_RHO 一个常数】并附本报告。")
    w("")
    if stats["valid"] < 200:
        w(f"> ⚠️ **样本仅 {stats['valid']} 场, 不足以扎实校准 rho(建议 ≥ 几百场, 1000–2000 更稳)。"
          "本次结果仅作管线验证, 勿写入生产 DEFAULT_RHO。**")
        w("")

    w("## 1. rho 估计")
    w("")
    w(f"- **rho_hat = {rho_hat:.4f}**  (Hessian SE = {se:.4f})")
    if ci:
        w(f"- bootstrap 95% CI: [{ci[0]:.4f}, {ci[1]:.4f}]")
    w(f"- NLL@rho_hat = {nll_hat:.2f} ; NLL@rho=0(独立Poisson) = {nll_zero:.2f}")
    w(f"- 似然提升(越大越说明低分依赖真实存在): ΔNLL = {nll_zero - nll_hat:.2f}")
    w(f"- 经验区间参考: rho 通常落在 [-0.15, -0.03]; rho<0 抬高 0-0/1-1、压低 1-0/0-1。")
    w("")
    w("> 若要写入生产: 把 `w1_score_engine.DEFAULT_RHO` 改为上面的 rho_hat。**只改这一个常数**, 其它逻辑不动。")
    w("")

    w("## 2. 市场基线对照(模型当前应≈市场, 不应跑输)")
    w("")
    w("| 指标 | 值 | 说明 |")
    w("|---|--:|---|")
    w(f"| 模型 1X2 平均 RPS | {base['rps_model']:.4f} | 应≈市场(模型复现市场) |")
    w(f"| 市场去水 1X2 平均 RPS | {base['rps_market']:.4f} | 基线 |")
    w(f"| 均匀(1/3) 平均 RPS | {base['rps_uniform']:.4f} | 下界参照 |")
    w(f"| 模型−市场 RPS 差 | {base['rps_model'] - base['rps_market']:+.4f} | 接近 0 = 健康; 明显>0 = 反解或去水有问题 |")
    w(f"| exact-score log loss @rho_hat | {base['logloss_rho_hat']:.4f} | rho 的价值体现在这里 |")
    w(f"| exact-score log loss @rho=0 | {base['logloss_rho_zero']:.4f} | 对照 |")
    w(f"| log loss 改善 | {base['logloss_rho_zero'] - base['logloss_rho_hat']:+.4f} | >0 = rho 有增益 |")
    w("")
    w("> 关键读法: rho **不应**改善 1X2 RPS(那是市场定的), 它的增益只在**精确比分/低分结构**的 log loss 上。")
    w("")

    w("## 3. 可靠性: 1X2 主胜概率分桶")
    w("")
    w("| 预测 P(主胜) 桶均值 | 实际主胜频率 | 场数 |")
    w("|--:|--:|--:|")
    for pm, ef, n in rel_1x2:
        w(f"| {pm:.3f} | {ef:.3f} | {n} |")
    w("")
    w("> 预测列与实际列应接近(校准良好)。系统性偏离揭示去水偏差或市场反解问题。")
    w("")

    w("## 4. 可靠性: 总进球尾部(直接回答\"尾巴够不够胖\")")
    w("")
    w("| 阈值 | 预测 P(总>阈值) | 实际频率 | 场数 |")
    w("|---|--:|--:|--:|")
    for t, (mp, ef, n) in rel_tot.items():
        w(f"| 总>{t} | {mp:.3f} | {ef:.3f} | {n} |")
    w("")
    w("> **这张表才是判断要不要加 overdispersion 的依据**: 若高阈值(>3.5/>4.5)处"
      "**预测系统性低于实际**, 说明尾部偏薄, 才考虑过散参数; 否则不要加结构。")
    w("")

    if plot_ok:
        w("## 5. 图")
        w("")
        w("见同目录 `W1_RHO_CALIBRATION_RELIABILITY.png`(左: rho 似然曲线; 右: 总进球尾部可靠性)。")
        w("")

    w("## 6. 纪律提醒")
    w("")
    w("- 只拟合一个**全局** rho; 不分桶拟合 rho(分桶只用于可靠性诊断, 需大样本)。")
    w("- **不要**用世界杯进行中的 64 场估 rho; 用大样本历史。")
    w("- rho 是二阶量; 它对不对不如 lambda(来自市场)重要。先把它校到经验区间内即可。")
    w("- 若总进球尾部可靠性显示系统性低估, 下一步**先换去水法(Shin/power)**再考虑过散结构。")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def default_json_path(report_path: Path) -> Path:
    if report_path.name == "W1_RHO_REAL_OU_CALIBRATION_REPORT.md":
        return report_path.with_name("w1_rho_real_ou_calibration.json")
    return report_path.with_suffix(".json")


def write_json_summary(path: Path, csv_path: Path, stats, rho_hat, nll_hat, nll_zero, se,
                       ci, rel_1x2, rel_tot, base, production_ready: bool, synthetic: bool,
                       rps_gap: float, min_prod_sample: int, mode: str, plot_path: Path,
                       report_path: Path) -> None:
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": mode,
        "input_csv": str(csv_path),
        "report": str(report_path),
        "figure": str(plot_path),
        "stats": stats,
        "rho_hat": round(float(rho_hat), 6),
        "nll_rho_hat": round(float(nll_hat), 6),
        "nll_rho_zero": round(float(nll_zero), 6),
        "nll_improvement": round(float(nll_zero - nll_hat), 6),
        "hessian_se": None if math.isnan(se) else round(float(se), 6),
        "bootstrap_ci_95": None if ci is None else [round(float(ci[0]), 6), round(float(ci[1]), 6)],
        "production_ready": bool(production_ready),
        "input_synthetic": bool(synthetic),
        "valid_sample": stats.get("valid"),
        "min_prod_sample": min_prod_sample,
        "rps_gap_model_minus_market": round(float(rps_gap), 6),
        "baseline": {key: round(float(value), 6) for key, value in base.items()},
        "reliability_1x2": [
            {"predicted_home_win_prob": round(float(pred), 6), "actual_home_win_rate": round(float(emp), 6), "n": n}
            for pred, emp, n in rel_1x2
        ],
        "reliability_total": [
            {"threshold": threshold, "predicted_over_prob": round(float(values[0]), 6), "actual_over_rate": round(float(values[1]), 6), "n": values[2]}
            for threshold, values in rel_tot.items()
        ],
        "default_rho_updated": False,
        "notes_cn": [
            "本报告只生成 rho calibration candidate，不自动修改 DEFAULT_RHO。",
            "若 valid_sample < min_prod_sample，production_ready 必须为 false。",
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ===========================================================================
# 7. CLI
# ===========================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="W1 Dixon-Coles rho 校准(市场条件 MLE)")
    ap.add_argument("--csv", type=Path, default=None, help="历史 CSV(字段见 REQUIRED_COLUMNS)")
    ap.add_argument("--report", type=Path, default=Path("reports/W1_RHO_CALIBRATION_REPORT.md"))
    ap.add_argument("--plot", type=Path, default=None)
    ap.add_argument("--figure", type=Path, default=None, help="兼容别名: 同 --plot")
    ap.add_argument("--mode", choices=["ou"], default="ou", help="校准模式; 当前生产候选只允许 ou")
    ap.add_argument("--json-out", type=Path, default=None, help="机器可读报告输出路径")
    ap.add_argument("--bootstrap", type=int, default=0, help="bootstrap 次数(0=跳过); 200 较稳但慢")
    ap.add_argument("--min-prod-sample", type=int, default=500, help="允许写入生产 DEFAULT_RHO 的最小有效样本")
    ap.add_argument("--max-goals", type=int, default=E.MAX_GOALS)
    ap.add_argument("--print-schema", action="store_true", help="打印锁定的 CSV 字段后退出")
    ap.add_argument("--synthetic-note", default="", help="(内部)标注输入为合成数据")
    args = ap.parse_args()

    if args.print_schema:
        print("REQUIRED (rho 拟合必需):")
        for c, d in REQUIRED_COLUMNS.items():
            print(f"  {c:30} {d}")
        print("\nOPTIONAL (现在一起记, 日后分桶用; 缺只 WARN):")
        for c, d in OPTIONAL_COLUMNS.items():
            print(f"  {c:30} {d}")
        return 0

    if args.csv is None:
        print("FAIL: 需要 --csv(或用 --print-schema 查看字段)", file=sys.stderr)
        return 2

    try:
        rows, stats = load_history(args.csv)
    except (SchemaError, FileNotFoundError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    if stats["valid"] == 0:
        print("FAIL: 无有效行", file=sys.stderr)
        return 2

    # 预计算每行 mu(只依赖市场, 与 rho 无关), 缓存
    for rec in rows:
        rec["_mu"] = row_mu(rec)

    rho_hat, nll_hat, nll_zero, se = fit_rho(rows, args.max_goals)
    ci = bootstrap_rho(rows, args.max_goals, args.bootstrap) if args.bootstrap > 0 else None
    rel_1x2 = reliability_1x2(rows, rho_hat, args.max_goals)
    rel_tot = reliability_total(rows, rho_hat, args.max_goals)
    base = baseline_compare(rows, rho_hat, args.max_goals)

    synthetic = is_synthetic(rows)
    rps_gap = abs(base["rps_model"] - base["rps_market"])
    production_ready = ((not synthetic) and stats["valid"] >= args.min_prod_sample
                        and rps_gap < 0.01
                        and RHO_BOUNDS[0] + 1e-3 < rho_hat < RHO_BOUNDS[1] - 1e-3)
    note = args.synthetic_note or ("自动检测: 输入疑似合成数据(competition=SYNTH)。" if synthetic else "")

    plot_path = args.figure or args.plot or args.report.with_name("W1_RHO_CALIBRATION_RELIABILITY.png")
    json_path = args.json_out or default_json_path(args.report)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    plot_ok = write_plot(rho_hat, rows, rel_tot, args.max_goals, plot_path)
    write_report(args.report, args.csv, stats, rho_hat, nll_hat, nll_zero, se, ci,
                 rel_1x2, rel_tot, base, args.max_goals, plot_ok, note,
                 production_ready, synthetic, rps_gap, args.min_prod_sample)
    write_json_summary(json_path, args.csv, stats, rho_hat, nll_hat, nll_zero, se, ci,
                       rel_1x2, rel_tot, base, production_ready, synthetic,
                       rps_gap, args.min_prod_sample, args.mode, plot_path, args.report)

    print(f"PASS: rho_hat={rho_hat:.4f} (SE={se:.4f})  valid={stats['valid']}  "
          f"PRODUCTION_READY={'YES' if production_ready else 'NO'}  report -> {args.report}  json -> {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
