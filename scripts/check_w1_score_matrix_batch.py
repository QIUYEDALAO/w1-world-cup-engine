#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最小 checker for W1 score matrix batch (验证用, 非完整测试体系)
================================================================
守护 5 类不变量, 任一失败即非零退出。可放进 CI / pre-commit。

  A. 引擎可 import, 对样本卡 build_score_distribution 不崩溃;
  B. ready 输出的结构与数值边界 (概率∈[0,1]、matrix 求和≈1、market 复现误差有界);
  C. 缺市场必须干净 skip(带 skip_reason), 不得 partial / 不得伪造;
  D. 回归守卫: 引擎/批量源码内【禁止】出现硬编码 fixture_id(旧版痛点);
  E. 合规守卫: 源码与产出不得含投注/资金类违禁词。

用法: python3 scripts/check_w1_score_matrix_batch.py [--cards-dir <dir>]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

FORBIDDEN = ["bet", "stake", "profit", "guaranteed", "稳赚", "必胜"]
# 旧版痛点: 把答案写死给特定 fixture。新引擎绝不允许再出现。
HARDCODE_PATTERNS = [r'fid\s*==\s*["\']', r'==\s*["\']1489', r'fixture_id\s*==\s*["\']\d']


class Fail(Exception):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise Fail(msg)


def in01(x) -> bool:
    return isinstance(x, (int, float)) and -1e-9 <= x <= 1 + 1e-9


def guard_source(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for term in FORBIDDEN:
        pat = rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])" if term.isascii() else re.escape(term)
        check(not re.search(pat, text, re.I), f"{path.name}: 含违禁词 {term}")
    for pat in HARDCODE_PATTERNS:
        m = re.search(pat, text)
        check(m is None, f"{path.name}: 检测到硬编码 fixture_id 风格代码: {m.group(0) if m else ''}")


def validate_ready(sd: dict, fid: str) -> None:
    m = sd["model"]
    check(m["mu"] > 0, f"{fid}: mu 应>0")
    check(m["lambda_home"] > 0 and m["lambda_away"] > 0, f"{fid}: lambda 应>0")
    check(in01(m["market_reproduction_max_abs_err"]) is False or m["market_reproduction_max_abs_err"] < 0.10,
          f"{fid}: 市场复现误差过大({m['market_reproduction_max_abs_err']}), 检查 mu/delta 求解")
    check(re.match(r"^\d+-\d+$", sd["main_score"]) is not None, f"{fid}: main_score 格式异常")
    pool = sd["score_pool"]
    check(len(pool) == 6, f"{fid}: score_pool 应为 6 条")
    for it in pool:
        check(in01(it["probability"]), f"{fid}: pool probability 越界 {it}")
        check(in01(it["region_probability"]), f"{fid}: pool region_probability 越界 {it}")
    g = sd["game_open_trigger"]
    for k in ("open_game_prob", "high_total_prob", "blowout_prob", "favorite_collapse_prob"):
        check(in01(g[k]), f"{fid}: game_open_trigger.{k} 越界")
    pmc = sd["post_match_calibration"]
    if pmc.get("actual_score"):
        check(in01(pmc["actual_score_probability"]), f"{fid}: actual_score_probability 越界")
        check(0 <= pmc["rps_model"] <= 2, f"{fid}: rps_model 越界")
        check(isinstance(pmc["beat_uniform"], bool), f"{fid}: beat_uniform 应为 bool")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards-dir", type=Path, default=HERE.parent / "data/processed/match_cards/group_stage_round1")
    args = ap.parse_args()

    try:
        import w1_score_engine as E  # noqa
        import numpy as np

        # D + E: 源码守卫
        guard_source(HERE / "w1_score_engine.py")
        batch = HERE / "w1_score_matrix_batch.py"
        if batch.is_file():
            guard_source(batch)

        # A: 样本卡不崩溃 + B/C: 不变量
        cards = [p for p in sorted(args.cards_dir.glob("*.json"))
                 if str(json.loads(p.read_text(encoding="utf-8")).get("schema_version", "")).startswith("w1_match_card")]
        check(len(cards) > 0, f"目录内无 w1_match_card: {args.cards_dir}")
        n_ready = n_skip = 0
        for p in cards:
            card = json.loads(p.read_text(encoding="utf-8"))
            fid = E.fixture_num(card)
            sd = E.build_score_distribution(card)
            check(sd["status"] in ("ready", "skipped"), f"{fid}: status 必须是 ready/skipped, 不得 partial")
            if sd["status"] == "skipped":
                check(bool(sd.get("skip_reason")), f"{fid}: skip 必须带 skip_reason")
                n_skip += 1
                continue
            n_ready += 1
            validate_ready(sd, fid)
            # matrix 求和≈1
            lh, la = sd["model"]["lambda_home"], sd["model"]["lambda_away"]
            M = E.score_matrix(lh, la, sd["model"]["rho"], sd["model"]["max_goals"])
            check(abs(float(M.sum()) - 1.0) < 1e-6, f"{fid}: 比分矩阵未归一")

    except (Fail, Exception) as exc:  # noqa
        print(f"W1 score matrix batch check FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"W1 score matrix batch check PASS ({n_ready} ready / {n_skip} skipped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
