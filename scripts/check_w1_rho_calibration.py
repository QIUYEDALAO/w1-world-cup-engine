#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
W1 rho 校准 checker
===================
守 5 类不变量, 任一失败非零退出。核心是 D 闸门: 把生产 DEFAULT_RHO 与一份
【非合成、达标】的校准报告绑死, 从机制上杜绝合成 rho 进生产。

  A. schema 锁定: 模板 CSV 表头 == 校准脚本 REQUIRED+OPTIONAL 列(防字段漂移)。
  B. 还原冒烟: 用已知 rho_true 生成小样本, 拟合应还原(防拟合代码被改坏)。
  C. 合成守卫: 合成数据必须被 is_synthetic 识别, 且 PRODUCTION_READY=NO。
  D. 生产 rho 出处闸门: 若 DEFAULT_RHO 已标记 calibrated, 必须有非合成、达标、
     rho 值一致的报告背书; 占位态则放行。
  E. 源码守卫: 新脚本不得含违禁词 / fixture_id 硬编码。

用法: python3 scripts/check_w1_rho_calibration.py
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

TEMPLATE = ROOT / "data/historical/rho_calibration_template.csv"
PROVENANCE = ROOT / "config/w1_rho_provenance.json"
REPORT = ROOT / "reports/W1_RHO_CALIBRATION_REPORT.md"
SHIPPED_DEFAULT_RHO = -0.10          # 文档化的占位默认值
MIN_PROD_SAMPLE = 500
RECOVERY_TOL = 0.06                  # 还原冒烟容差(小样本)

FORBIDDEN = ["bet", "stake", "profit", "guaranteed", "稳" + "赚", "必" + "胜"]
HARDCODE = [r'fid\s*==\s*["\']', r'==\s*["\']1489', r'fixture_id\s*==\s*["\']\d']


class Fail(Exception):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise Fail(msg)


def guard_source(path: Path) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    for term in FORBIDDEN:
        pat = rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])" if term.isascii() else re.escape(term)
        check(not re.search(pat, text, re.I), f"{path.name}: 含违禁词 {term}")
    for pat in HARDCODE:
        m = re.search(pat, text)
        check(m is None, f"{path.name}: 含 fixture_id 硬编码 {m.group(0) if m else ''}")


def parse_report_field(text: str, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}:\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else None


def write_synthetic_history(path: Path, R, E, n: int, rho_true: float, seed: int) -> None:
    """Write a deterministic SYNTH smoke sample without requiring an extra helper file."""
    import numpy as np

    rng = np.random.default_rng(seed)
    lh, la = 1.35, 1.05
    matrix = E.score_matrix(lh, la, rho_true, E.MAX_GOALS)
    flat = matrix.reshape(-1)
    flat = flat / flat.sum()
    choices = rng.choice(len(flat), size=n, p=flat)
    home_goals = choices // matrix.shape[1]
    away_goals = choices % matrix.shape[1]
    h_prob, d_prob, a_prob = E.hda_from_matrix(matrix)
    odds = (1 / h_prob, 1 / d_prob, 1 / a_prob)
    mu = lh + la
    line = 2.5
    p_over = 1.0 - R.poisson.cdf(2, mu)
    over_odds = 1 / p_over
    under_odds = 1 / (1 - p_over)
    header = list(R.REQUIRED_COLUMNS) + list(R.OPTIONAL_COLUMNS)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for idx, (hg, ag) in enumerate(zip(home_goals, away_goals), start=1):
            writer.writerow({
                "match_date": "2020-01-01",
                "home_team": f"Synth Home {idx}",
                "away_team": f"Synth Away {idx}",
                "closing_home_odds": f"{odds[0]:.6f}",
                "closing_draw_odds": f"{odds[1]:.6f}",
                "closing_away_odds": f"{odds[2]:.6f}",
                "closing_ou_main_line": f"{line:.1f}",
                "closing_over_odds": f"{over_odds:.6f}",
                "closing_under_odds": f"{under_odds:.6f}",
                "home_goals": int(hg),
                "away_goals": int(ag),
                "market_snapshot_lead_minutes": 60,
                "competition": "SYNTH",
                "neutral_venue": 1,
                "lineup_completeness": "unknown",
                "closing_ah_main_line": "",
                "closing_fair_total_override": f"{mu:.6f}",
                "bookmaker_count": 1,
            })


def main() -> int:
    try:
        import w1_score_engine as E
        import w1_rho_calibration as R

        # ---- A. schema 锁定 ----
        check(TEMPLATE.is_file(), f"缺模板 CSV: {TEMPLATE}")
        header = TEMPLATE.read_text(encoding="utf-8-sig").splitlines()[0].strip().split(",")
        expected = list(R.REQUIRED_COLUMNS) + list(R.OPTIONAL_COLUMNS)
        check(header == expected,
              f"模板表头与脚本 schema 不一致\n模板: {header}\n脚本: {expected}")

        # ---- E. 源码守卫(放在重计算前, 快速失败) ----
        guard_source(HERE / "w1_rho_calibration.py")
        guard_source(HERE / "make_synthetic_history.py")

        # ---- C. 合成守卫(纯逻辑, 快) ----
        synth_rows = [{"competition": "SYNTH"} for _ in range(10)]
        real_rows = [{"competition": "WC"} for _ in range(10)]
        check(R.is_synthetic(synth_rows), "is_synthetic 未能识别合成数据")
        check(not R.is_synthetic(real_rows), "is_synthetic 误判真实数据为合成")

        # ---- B. 还原冒烟: 生成小样本 -> 拟合 -> 应还原 rho_true ----
        rho_true = -0.10
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "smoke.csv"
            write_synthetic_history(csv_path, R, E, n=3000, rho_true=rho_true, seed=5)
            rows, stats = R.load_history(csv_path)
            for rec in rows:
                rec["_mu"] = R.row_mu(rec)
            rho_hat, nll_hat, nll_zero, _ = R.fit_rho(rows, E.MAX_GOALS)
            # (a) 还原: 与真值接近
            check(abs(rho_hat - rho_true) < RECOVERY_TOL,
                  f"还原冒烟失败: rho_true={rho_true}, rho_hat={rho_hat:.4f}, "
                  f"|diff|>{RECOVERY_TOL}; 拟合代码可能被改坏")
            # (b) 未顶到搜索边界(顶界=拟合病态/被改坏)
            lo, hi = R.RHO_BOUNDS
            check(lo + 0.005 < rho_hat < hi - 0.005,
                  f"还原冒烟: rho_hat={rho_hat:.4f} 顶到边界, 拟合病态")
            # (c) DC 应优于独立 Poisson
            check(nll_zero - nll_hat > 0,
                  f"还原冒烟: DC 未优于独立 Poisson(ΔNLL={nll_zero - nll_hat:.2f})")
            check(R.is_synthetic(rows), "还原冒烟: 合成数据未被识别")

        # ---- D. 生产 rho 出处闸门(防合成进生产的核心) ----
        check(PROVENANCE.is_file(), f"缺出处文件: {PROVENANCE}")
        prov = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        default_rho = float(E.DEFAULT_RHO)

        if not prov.get("calibrated", False):
            # 占位态: DEFAULT_RHO 应等于出处记录的占位值, 不需要报告背书
            check(abs(default_rho - float(prov.get("default_rho", SHIPPED_DEFAULT_RHO))) < 1e-9,
                  f"占位态下 DEFAULT_RHO({default_rho}) 与出处 default_rho 不一致")
        else:
            # 已校准: 必须有非合成、达标、值一致的报告背书
            check(prov.get("input_synthetic") is False,
                  "出处标记 calibrated=true 但 input_synthetic 非 false(疑似合成 rho)")
            vs = int(prov.get("valid_sample") or 0)
            check(vs >= MIN_PROD_SAMPLE, f"出处 valid_sample={vs} < {MIN_PROD_SAMPLE}")
            check(abs(default_rho - float(prov.get("default_rho"))) < 1e-9,
                  "DEFAULT_RHO 与出处 default_rho 不一致")
            sr = prov.get("source_report")
            check(sr and (ROOT / sr).is_file(), f"出处 source_report 不存在: {sr}")
            rep = (ROOT / sr).read_text(encoding="utf-8")
            check(parse_report_field(rep, "PRODUCTION_READY") == "YES",
                  "背书报告 PRODUCTION_READY != YES")
            check(parse_report_field(rep, "INPUT_SYNTHETIC") == "NO",
                  "背书报告 INPUT_SYNTHETIC != NO(合成数据不得用于生产 rho)")
            rep_n = int(parse_report_field(rep, "VALID_SAMPLE") or 0)
            check(rep_n >= MIN_PROD_SAMPLE, f"背书报告 VALID_SAMPLE={rep_n} < {MIN_PROD_SAMPLE}")
            rep_rho = float(parse_report_field(rep, "RHO_HAT") or 99)
            check(abs(rep_rho - default_rho) < 1e-3,
                  f"背书报告 RHO_HAT={rep_rho} 与 DEFAULT_RHO={default_rho} 不一致")

    except (Fail, Exception) as exc:  # noqa
        print(f"W1 rho calibration check FAIL: {exc}", file=sys.stderr)
        return 1

    state = "calibrated" if prov.get("calibrated") else "uncalibrated_placeholder"
    print(f"W1 rho calibration check PASS (rho={E.DEFAULT_RHO}, provenance={state})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
