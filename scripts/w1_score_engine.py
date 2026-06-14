#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
W1 Score Engine
===============
市场盘口派生的 Dixon-Coles 比分矩阵。供 w1_score_matrix_batch.py 批量调用。
本文件不接入生产 build_w1_dashboard_data.py;仅作为候选替换内核 + 批量验证。

链路: 1X2(去水) + OU(派生 mu) -> 解 delta -> lambda_home/away
      -> Dixon-Coles 比分矩阵 -> 场景区域(权重=真实概率) -> RPS/log 评估

唯一需历史校准的结构参数是 DEFAULT_RHO,已标注 TODO。无任何硬编码 fixture_id。
依赖: numpy / scipy。
"""
from __future__ import annotations

import math
import re
from typing import Any

import numpy as np

# --- 需历史校准的结构参数(集中此处)-------------------------------------
# Dixon-Coles 低分相关。rho<0 抬高 0-0/1-1、压低 1-0/0-1。
# TODO(校准): 用历史国际比赛终场比分极大似然拟合;勿用 64 场世界杯估。
DEFAULT_RHO = -0.057766  # calibrated 2026-06-14, n=10731, report=reports/W1_RHO_REAL_OU_CALIBRATION_REPORT.md
MAX_GOALS = 10


# ===========================================================================
# 1. 解析赔率(适配 W1 真实结构 markets.odds_*; 优先 entries, 退回 raw)
# ===========================================================================
def _first_line(block: dict[str, Any]) -> dict[str, Any]:
    lines = block.get("lines") or [{}]
    return lines[0] if lines else {}


def fixture_num(card_or_id: Any) -> str:
    """把 'api-football:1489370' / {'match':{'match_id':...}} 归一成 '1489370'。"""
    if isinstance(card_or_id, dict):
        raw = str(card_or_id.get("match", {}).get("match_id", ""))
    else:
        raw = str(card_or_id)
    m = re.search(r"(\d{4,})", raw)
    return m.group(1) if m else raw


def parse_1x2(card: dict[str, Any]) -> tuple[float, float, float] | None:
    blk = card.get("markets", {}).get("odds_1X2", {})
    if not blk.get("available"):
        return None
    line = _first_line(blk)
    h, d, a = line.get("home"), line.get("draw"), line.get("away")
    if h and d and a:
        return float(h), float(d), float(a)
    m = re.search(r"Home=([\d.]+).*?Draw=([\d.]+).*?Away=([\d.]+)", line.get("raw") or "")
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


def _entries(block: dict[str, Any]) -> list[dict[str, Any]]:
    line = _first_line(block)
    if line.get("entries"):
        return line["entries"]
    out = []
    for label, odd in re.findall(r"([A-Za-z][A-Za-z+\-. 0-9]*?)=([\d.]+)", line.get("raw") or ""):
        out.append({"line": label.strip(), "odds": float(odd)})
    return out


def parse_ou_ladder(card: dict[str, Any]) -> dict[float, dict[str, float]]:
    blk = card.get("markets", {}).get("odds_OU", {})
    ladder: dict[float, dict[str, float]] = {}
    for e in _entries(blk):
        m = re.match(r"(Over|Under)\s+([\d.]+)", str(e.get("line", "")))
        if m:
            ladder.setdefault(float(m.group(2)), {})[m.group(1).lower()] = float(e["odds"])
    return {k: v for k, v in ladder.items() if "over" in v and "under" in v}


def parse_ah_ladder(card: dict[str, Any]) -> dict[float, dict[str, float]]:
    """返回 {主队让球数: {'home':odd,'away':odd}}; 仅作交叉验证, 不用于解 supremacy。"""
    blk = card.get("markets", {}).get("odds_AH", {})
    rows: dict[float, dict[str, float]] = {}
    for e in _entries(blk):
        m = re.match(r"(Home|Away)\s+([+-]?[\d.]+)", str(e.get("line", "")))
        if m:
            val = float(m.group(2))
            hcap = val if m.group(1) == "Home" else -val
            rows.setdefault(hcap, {})[m.group(1).lower()] = float(e["odds"])
    return rows


# ===========================================================================
# 2. 去水
# ===========================================================================
def devig_proportional(odds: list[float]) -> list[float]:
    inv = [1.0 / o for o in odds]
    s = sum(inv)
    return [x / s for x in inv]


def devig_two_way(over: float, under: float) -> float:
    io, iu = 1.0 / over, 1.0 / under
    return io / (io + iu)


# ===========================================================================
# 3. OU -> 期望总进球 mu
# ===========================================================================
def fair_total_from_ou(ladder: dict[float, dict[str, float]]) -> float | None:
    if not ladder:
        return None
    pts = sorted((L, devig_two_way(v["over"], v["under"])) for L, v in ladder.items())
    for (l0, p0), (l1, p1) in zip(pts, pts[1:]):
        if (p0 - 0.5) * (p1 - 0.5) <= 0 and p0 != p1:
            return l0 + (p0 - 0.5) / (p0 - p1) * (l1 - l0)
    return pts[0][0] - 0.5 if pts[0][1] < 0.5 else pts[-1][0] + 0.5


# ===========================================================================
# 4. Dixon-Coles 比分矩阵
# ===========================================================================
def _dc_tau(i: int, j: int, lh: float, la: float, rho: float) -> float:
    if i == 0 and j == 0:
        return 1.0 - lh * la * rho
    if i == 0 and j == 1:
        return 1.0 + lh * rho
    if i == 1 and j == 0:
        return 1.0 + la * rho
    if i == 1 and j == 1:
        return 1.0 - rho
    return 1.0


def _poisson_pmf(values: np.ndarray, lam: float) -> np.ndarray:
    return np.array([math.exp(-lam) * lam**int(k) / math.factorial(int(k)) for k in values], dtype=float)


def score_matrix(lh: float, la: float, rho: float = DEFAULT_RHO, max_goals: int = MAX_GOALS) -> np.ndarray:
    i = np.arange(max_goals + 1)
    M = np.outer(_poisson_pmf(i, lh), _poisson_pmf(i, la))
    for x in range(2):
        for y in range(2):
            M[x, y] *= _dc_tau(x, y, lh, la, rho)
    return M / M.sum()


def hda_from_matrix(M: np.ndarray) -> tuple[float, float, float]:
    return float(np.tril(M, -1).sum()), float(np.trace(M)), float(np.triu(M, 1).sum())


# ===========================================================================
# 5. 解 lambda(固定 mu, 拟合 delta 复现 1X2)
# ===========================================================================
def solve_lambdas(p1x2: tuple[float, float, float], mu: float,
                  rho: float = DEFAULT_RHO) -> tuple[float, float, float, float]:
    ph, pd, pa = p1x2

    def sse(delta: float) -> float:
        lh, la = (mu + delta) / 2.0, (mu - delta) / 2.0
        if lh <= 0.01 or la <= 0.01:
            return 1e6
        h, d, a = hda_from_matrix(score_matrix(lh, la, rho))
        return (h - ph) ** 2 + (d - pd) ** 2 + (a - pa) ** 2

    lo, hi = -mu + 0.05, mu - 0.05
    gr = (math.sqrt(5) - 1) / 2
    c = hi - gr * (hi - lo)
    d = lo + gr * (hi - lo)
    fc, fd = sse(c), sse(d)
    for _ in range(80):
        if abs(hi - lo) < 1e-8:
            break
        if fc < fd:
            hi, d, fd = d, c, fc
            c = hi - gr * (hi - lo)
            fc = sse(c)
        else:
            lo, c, fc = c, d, fd
            d = lo + gr * (hi - lo)
            fd = sse(d)
    delta = (lo + hi) / 2.0
    return (mu + delta) / 2.0, (mu - delta) / 2.0, delta, float(sse(delta))


# ===========================================================================
# 6. 矩阵工具:区域代表比分 / top 比分
# ===========================================================================
def top_scores(M: np.ndarray, n: int = 8) -> list[tuple[str, float]]:
    order = np.argsort(M.ravel())[::-1]
    idx = np.dstack(np.unravel_index(order, M.shape))[0]
    return [(f"{i}-{j}", float(M[i, j])) for i, j in idx[:n]]


def _rep_in_mask(M: np.ndarray, mask: np.ndarray) -> tuple[str, float]:
    masked = np.where(mask, M, -1.0)
    i, j = np.unravel_index(int(np.argmax(masked)), M.shape)
    return f"{i}-{j}", float(M[i, j])


def _rank_of(M: np.ndarray, i: int, j: int) -> int:
    flat = np.sort(M.ravel())[::-1]
    return int(np.searchsorted(-flat, -M[i, j], side="left")) + 1


# ===========================================================================
# 7. 评估
# ===========================================================================
def rps_hda(pred: tuple[float, float, float], outcome: str) -> float:
    obs = {"H": (1, 0, 0), "D": (0, 1, 0), "A": (0, 0, 1)}[outcome]
    cp, co = np.cumsum(pred), np.cumsum(obs)
    return float(np.sum((cp[:-1] - co[:-1]) ** 2))


def log_score_hda(pred: tuple[float, float, float], outcome: str) -> float:
    return -math.log(max({"H": pred[0], "D": pred[1], "A": pred[2]}[outcome], 1e-12))


def log_score_exact(M: np.ndarray, h: int, a: int) -> float:
    p = M[h, a] if (h < M.shape[0] and a < M.shape[1]) else 1e-12
    return -math.log(max(p, 1e-12))


def outcome_of(h: int, a: int) -> str:
    return "H" if h > a else ("A" if a > h else "D")


# ===========================================================================
# 8. 桶化(把概率折回旧版序数标签, 便于 drop-in 兼容旧 UI)
# ===========================================================================
def bucket_weight(p: float) -> str:
    if p >= 0.18:
        return "high"
    if p >= 0.10:
        return "medium"
    if p >= 0.05:
        return "medium_low"
    if p >= 0.02:
        return "low"
    return "very_low"


# ===========================================================================
# 9. 顶层:产出新版 score_distribution(与旧版同键 + model 扩展)
# ===========================================================================
def build_score_distribution(card: dict[str, Any], actual: tuple[int, int] | None = None,
                             rho: float = DEFAULT_RHO, max_goals: int = MAX_GOALS) -> dict[str, Any]:
    fid = fixture_num(card)
    odds = parse_1x2(card)
    ou = parse_ou_ladder(card)
    # ---- 缺市场则干净跳过, 不伪造 ----
    if not odds:
        return {"status": "skipped", "fixture_id": fid, "skip_reason": "odds_1X2 unavailable/unparseable"}
    mu = fair_total_from_ou(ou)
    if mu is None:
        return {"status": "skipped", "fixture_id": fid, "skip_reason": "odds_OU unavailable/unparseable"}

    p1x2 = tuple(devig_proportional(list(odds)))
    lh, la, delta, sse = solve_lambdas(p1x2, mu, rho)
    M = score_matrix(lh, la, rho, max_goals)
    model_hda = hda_from_matrix(M)
    max_abs_err = max(abs(m - t) for m, t in zip(model_hda, p1x2))

    n = M.shape[0]
    diff = np.subtract.outer(np.arange(n), np.arange(n))   # home - away
    total = np.add.outer(np.arange(n), np.arange(n))
    fav_home = model_hda[0] >= model_hda[2]
    fav_sign = 1 if fav_home else -1

    draw_mask = diff == 0
    favwin_mask = (diff * fav_sign) > 0
    favby2_mask = (diff * fav_sign) >= 2
    open_mask = total >= 4
    favwin_open_mask = favwin_mask & open_mask
    collapse_mask = (diff * fav_sign) < 0

    draw_mass = float(M[draw_mask].sum())
    favwin = float(M[favwin_mask].sum())
    favby2 = float(M[favby2_mask].sum())
    open_p = float(M[open_mask].sum())
    favwin_open = float(M[favwin_open_mask].sum())
    collapse = float(M[collapse_mask].sum())

    main_sc, main_p = top_scores(M, 1)[0]

    def item(path: str, mask_or_score, region_p: float, reason: str) -> dict[str, Any]:
        if isinstance(mask_or_score, str):
            sc, p = mask_or_score, float(M[tuple(map(int, mask_or_score.split("-")))])
        else:
            sc, p = _rep_in_mask(M, mask_or_score)
        return {"score": sc, "path": path, "probability": round(p, 4),
                "region_probability": round(region_p, 4), "weight": bucket_weight(region_p),
                "reason_cn": reason}

    # 保留旧版六条路径标签, 但每条是矩阵上的区域, 权重=真实概率
    score_pool = [
        item("小胜主线", main_sc, main_p, "比分矩阵众数;市场+基础面主路径。"),
        item("防平路径", draw_mask, draw_mass, "全平局质量;AH 是期望净胜球, 不保证胜差。"),
        item("优势扩大", favby2_mask, favby2, "热门净胜≥2 的区域质量。"),
        item("打开局", open_mask, open_p, "总进球≥4 的区域质量(分布尾部, 非单一比分)。"),
        item("强队打穿", favwin_open_mask, favwin_open, "热门在高比分局取胜的联合质量。"),
        item("防线崩盘", collapse_mask, collapse, "热门输球尾部质量。"),
    ]

    out: dict[str, Any] = {
        "status": "ready",
        "fixture_id": fid,
        "engine": "w1_score_engine.dixon_coles.v1",
        "model": {
            "mu": round(mu, 3), "delta": round(delta, 3),
            "lambda_home": round(lh, 3), "lambda_away": round(la, 3),
            "rho": rho, "max_goals": max_goals,
            "devig_1x2": [round(x, 3) for x in p1x2],
            "model_hda": [round(x, 3) for x in model_hda],
            "fit_sse": round(sse, 6),
            "market_reproduction_max_abs_err": round(max_abs_err, 4),
            "market_reproduction_ok": bool(max_abs_err < 0.02),
        },
        "main_score": main_sc,
        "fallback_score": _rep_in_mask(M, draw_mask)[0],
        "top_scores": [
            {"score": score, "probability": round(prob, 4)}
            for score, prob in top_scores(M, 8)
        ],
        "score_pool": score_pool,
        "game_open_trigger": {
            "open_game_prob": round(open_p, 4),
            "high_total_prob": round(float(M[total >= 3].sum()), 4),
            "blowout_prob": round(float(M[np.abs(diff) >= 3].sum()), 4),
            "favorite_collapse_prob": round(collapse, 4),
            "timing_risks_modeled": False,
            "note_cn": "早球/红牌/点球属临场路径依赖, 赛前比分矩阵不建模, 仅以分布宽度体现; 需另接信号。",
            "must_reprice_if_triggered": True,
        },
        "market_vs_score_risk": {
            "supremacy_delta": round(delta, 3),
            "favorite_side": "home" if fav_home else "away",
            "favorite_win_prob": round(favwin, 4),
            "favorite_cover_minus1_prob": round(favby2, 4),
            "draw_prob": round(draw_mass, 4),
            "summary_cn": (f"市场期望净胜球 δ={delta:.2f}, 但热门取胜仅 {favwin:.0%}、"
                           f"平局 {draw_mass:.0%}; AH 是期望不是保证。"),
        },
        "score_summary_cn": ("比分分布来自市场派生的 Dixon-Coles 矩阵; 六条路径是矩阵区域, "
                             "权重为会求和的真实概率, 而非模板比分。"),
    }

    # ---- 赛后评估(替换 main_hit/pool_hit/miss)----
    if actual is not None:
        h, a = actual
        oc = outcome_of(h, a)
        p_act = float(M[h, a]) if (h < n and a < n) else 0.0
        rps_m = rps_hda(model_hda, oc)
        rps_u = rps_hda((1 / 3, 1 / 3, 1 / 3), oc)
        out["post_match_calibration"] = {
            "actual_score": f"{h}-{a}",
            "outcome": oc,
            "actual_score_probability": round(p_act, 4),
            "actual_score_rank": _rank_of(M, h, a) if (h < n and a < n) else None,
            "rps_model": round(rps_m, 4),
            "rps_uniform_baseline": round(rps_u, 4),
            "beat_uniform": bool(rps_m < rps_u),
            "log_score_exact": round(log_score_exact(M, h, a), 4),
            "log_score_outcome": round(log_score_hda(model_hda, oc), 4),
            "note_cn": (f"实际比分 {h}-{a} 概率 {p_act:.1%}, 在矩阵中排第 "
                        f"{_rank_of(M, h, a) if (h<n and a<n) else '-'}; 单场不调权重, 累计入 RPS 评估。"),
        }
    else:
        out["post_match_calibration"] = {
            "actual_score": None, "outcome": None,
            "note_cn": "未完赛; 赛后写入 actual_score 后由 RPS/log 评估。",
        }

    return out


def build_matrix_topscores(card: dict[str, Any], rho: float = DEFAULT_RHO,
                           max_goals: int = MAX_GOALS, n: int = 8) -> list[tuple[str, float]]:
    """便捷函数: 直接返回某张卡的前 n 高比分(供报告/快速检查)。缺市场返回 []。"""
    odds = parse_1x2(card)
    ou = parse_ou_ladder(card)
    if not odds or not ou:
        return []
    mu = fair_total_from_ou(ou)
    if mu is None:
        return []
    p1x2 = tuple(devig_proportional(list(odds)))
    lh, la, _, _ = solve_lambdas(p1x2, mu, rho)
    return top_scores(score_matrix(lh, la, rho, max_goals), n)
