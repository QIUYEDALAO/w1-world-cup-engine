#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
W1 Score Matrix Batch
=====================
读 match card 目录, 批量产出【新版 score_distribution】(市场派生 Dixon-Coles 矩阵),
可选拉取【旧版 score_distribution】做新旧对比, 输出 markdown 报告 + 可选 JSON。

【不接入生产】: 本工具只读卡 + 写报告/JSON, 不触碰 build_w1_dashboard_data.py。

用法:
  python3 scripts/w1_score_matrix_batch.py \
      --cards-dir data/processed/match_cards/group_stage_round1 \
      --old-dashboard-data reports/dashboard/assets/w1_dashboard_data.json \
      --report reports/W1_SCORE_MATRIX_BATCH_REPORT.md \
      --json-out reports/w1_new_score_distribution.json

  # actuals 来源优先级: --actuals 文件 > 旧 dashboard data 的 actual_score
  # --actuals 格式: {"1489373": [1,1], "1489370": [4,1]}
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import w1_score_engine as E  # noqa: E402


# --------------------------------------------------------------------------
def load_cards(cards_dir: Path) -> list[tuple[str, dict[str, Any]]]:
    """读目录下所有 *.json, 只保留 schema 为 w1_match_card 的卡, 按 fixture 排序。"""
    cards = []
    for p in sorted(cards_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(data.get("schema_version", "")).startswith("w1_match_card"):
            cards.append((E.fixture_num(data), data))
    return cards


def load_old(path: Path | None) -> tuple[dict[str, dict], dict[str, tuple[int, int]]]:
    """从旧 dashboard data 提取 {fid: old_score_distribution} 与 {fid: actual_score}。"""
    old_sd: dict[str, dict] = {}
    actuals: dict[str, tuple[int, int]] = {}
    if not path or not path.is_file():
        return old_sd, actuals
    data = json.loads(path.read_text(encoding="utf-8"))
    for r in data.get("match_records", []):
        fid = E.fixture_num(str(r.get("fixture_id", "")))
        if r.get("score_distribution"):
            old_sd[fid] = r["score_distribution"]
        sc = r.get("actual_score") or {}
        if sc.get("home") is not None and sc.get("away") is not None:
            actuals[fid] = (int(sc["home"]), int(sc["away"]))
    return old_sd, actuals


def team_names(card: dict[str, Any]) -> str:
    t = card.get("teams", {})
    return f"{t.get('home', {}).get('name', '?')} vs {t.get('away', {}).get('name', '?')}"


def yn(v: bool) -> str:
    return "✅" if v else "—"


# --------------------------------------------------------------------------
def build_report(rows: list[dict[str, Any]], old_sd: dict[str, dict],
                 meta: dict[str, Any]) -> str:
    L: list[str] = []
    w = L.append

    w("# W1 Score Matrix 批量验证报告")
    w("")
    w(f"- 生成时间: {meta['generated_at']}")
    w(f"- cards 目录: `{meta['cards_dir']}`")
    w(f"- 卡数量: {meta['n_cards']} (成功 {meta['n_ok']} / 跳过 {meta['n_skip']})")
    w(f"- rho (Dixon-Coles 低分相关, **未校准, 默认值**): {meta['rho']}")
    w(f"- max_goals: {meta['max_goals']}")
    w("- 定位: 仅验证, **未接入** build_w1_dashboard_data.py")
    w("- 边界: 本报告用于赛前数据分析与赛后复盘, 不构成投注/下注/资金建议。")
    w("")

    # ---- 1. 读取稳定性 ----
    w("## 1. 读取稳定性 (能否稳定读 odds entries)")
    w("")
    w("| fixture | 对阵 | 1X2 | AH | OU | 结果 |")
    w("|---|---|:--:|:--:|:--:|---|")
    for r in rows:
        flags = r["read"]
        status = "OK" if r["ok"] else f"SKIP: {r.get('skip_reason','')}"
        w(f"| {r['fid']} | {r['teams']} | {yn(flags['1x2'])} | {yn(flags['ah'])} "
          f"| {yn(flags['ou'])} | {status} |")
    w("")

    ok_rows = [r for r in rows if r["ok"]]

    # ---- 2. μ / δ / λ ----
    w("## 2. 批量 μ / δ / λ (市场反解)")
    w("")
    w("| fixture | 去水1X2 (H/D/A) | μ | δ(净胜) | λ_home | λ_away |")
    w("|---|---|--:|--:|--:|--:|")
    for r in ok_rows:
        m = r["sd"]["model"]
        w(f"| {r['fid']} | {m['devig_1x2']} | {m['mu']} | {m['delta']} "
          f"| {m['lambda_home']} | {m['lambda_away']} |")
    w("")

    # ---- 3. 市场复现校验 ----
    w("## 3. 市场复现校验 (模型 1X2 是否≈去水 1X2)")
    w("")
    w("模型用反解的 λ 生成矩阵后, 再算回 1X2; 应与输入去水 1X2 吻合。最大绝对误差 < 0.02 视为通过。")
    w("")
    w("| fixture | 去水1X2 | 模型1X2 | 最大绝对误差 | 通过 |")
    w("|---|---|---|--:|:--:|")
    for r in ok_rows:
        m = r["sd"]["model"]
        w(f"| {r['fid']} | {m['devig_1x2']} | {m['model_hda']} "
          f"| {m['market_reproduction_max_abs_err']} | {yn(m['market_reproduction_ok'])} |")
    w("")

    # ---- 4. 比分矩阵摘要 ----
    w("## 4. 比分矩阵摘要 (top 比分 + 场景区域概率)")
    w("")
    for r in ok_rows:
        sd = r["sd"]
        got = E.build_matrix_topscores(r["card"], meta["rho"], meta["max_goals"])
        w(f"### {r['fid']} — {r['teams']}")
        w("")
        w("前 6 高比分: " + ", ".join(f"`{s}` {p*100:.1f}%" for s, p in got[:6]))
        w("")
        gt = sd["game_open_trigger"]
        w(f"- 防平质量: **{sd['market_vs_score_risk']['draw_prob']*100:.1f}%**  ")
        w(f"- 热门取胜: **{sd['market_vs_score_risk']['favorite_win_prob']*100:.1f}%** "
          f"(热门方 = {sd['market_vs_score_risk']['favorite_side']})  ")
        w(f"- 打开局(总进球≥4): **{gt['open_game_prob']*100:.1f}%**  ")
        w(f"- 大胜(净胜≥3): **{gt['blowout_prob']*100:.1f}%**  ")
        w(f"- 防线崩盘(热门输): **{gt['favorite_collapse_prob']*100:.1f}%**")
        w("")

    # ---- 5. 完赛评估 ----
    finished = [r for r in ok_rows if r["sd"].get("post_match_calibration", {}).get("actual_score")]
    w("## 5. 完赛评估 (actual_score_probability / RPS / log-score)")
    w("")
    if finished:
        w("| fixture | 实际 | 结果 | 该比分概率 | 矩阵排名 | RPS模型 | RPS均匀 | 胜过均匀 | log精确 | log胜平负 |")
        w("|---|:--:|:--:|--:|:--:|--:|--:|:--:|--:|--:|")
        for r in finished:
            c = r["sd"]["post_match_calibration"]
            w(f"| {r['fid']} | {c['actual_score']} | {c['outcome']} "
              f"| {c['actual_score_probability']*100:.2f}% | #{c['actual_score_rank']} "
              f"| {c['rps_model']} | {c['rps_uniform_baseline']} | {yn(c['beat_uniform'])} "
              f"| {c['log_score_exact']} | {c['log_score_outcome']} |")
        w("")
        w("> 单场 RPS 不用于调权重: 大热门翻车的那场会狠罚自信而正确的模型, "
          "这是为什么必须累计样本评估而非逐场反应。")
    else:
        w("(无完赛比赛或未提供 actual_score。)")
    w("")

    # ---- 6. 新旧对比 ----
    w("## 6. 新旧 score_distribution 对比")
    w("")
    compared = [r for r in ok_rows if r["fid"] in old_sd]
    if not compared:
        w("(未提供旧 dashboard data, 或无可对齐 fixture。)")
    else:
        for r in compared:
            old = old_sd[r["fid"]]
            new = r["sd"]
            c = new.get("post_match_calibration", {})
            w(f"### {r['fid']} — {r['teams']}")
            w("")
            w(f"- **旧 main_score**: `{old.get('main_score')}` "
              f"(权重为序数标签, 不可求和)")
            w(f"- **新 main_score (矩阵众数)**: `{new['main_score']}` "
              f"({dict(E.build_matrix_topscores(r['card'], meta['rho'], meta['max_goals'])[:1])})")
            if c.get("actual_score"):
                w(f"- 实际: `{c['actual_score']}` → 新模型给该比分 "
                  f"**{c['actual_score_probability']*100:.2f}%** (排名 #{c['actual_score_rank']})")
            w("")
            w("| 路径 | 旧权重(序数) | 新代表比分 | 新区域概率 |")
            w("|---|:--:|:--:|--:|")
            old_pool = {it.get("path"): it.get("weight") for it in old.get("score_pool", [])}
            for it in new["score_pool"]:
                ow = old_pool.get(it["path"], "—")
                w(f"| {it['path']} | {ow} | `{it['score']}` | {it['region_probability']*100:.1f}% |")
            w("")

    # ---- 7. 注意与边界 ----
    w("## 7. 注意事项与已知边界")
    w("")
    w("- **rho 未校准**: 当前为默认 -0.10。低 μ 比赛的平局概率可能略偏高(USA 场 SSE 偏大即此因)。"
      "下一步用历史国际比赛终场比分极大似然拟合 rho。")
    w("- **supremacy 来自 1X2+OU, 不解析 AH**: 因卡内 AH 标注存在歧义(例如两侧同标 `+1`), "
      "AH 仅作交叉验证, 不参与解 δ。")
    w("- **去水为比例法**: 对深盘热门有 favorite-longshot 偏差, 后续可换 Shin/power 方法。")
    w("- **timing 风险不建模**: 早球/红牌/点球属临场路径依赖, 矩阵只给分布宽度, 不给时间点。")
    w("- **样本量**: 完赛仅个位数, 任何 RPS 结论都需累计整届乃至跨届; 分段校准只能在大历史集上做。")
    w("")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="W1 score matrix batch (验证用, 不接入生产)")
    ap.add_argument("--cards-dir", required=True, type=Path)
    ap.add_argument("--old-dashboard-data", type=Path, default=None)
    ap.add_argument("--actuals", type=Path, default=None, help='JSON: {"1489373":[1,1]}')
    ap.add_argument("--rho", type=float, default=E.DEFAULT_RHO)
    ap.add_argument("--max-goals", type=int, default=E.MAX_GOALS)
    ap.add_argument("--report", type=Path, default=Path("reports/W1_SCORE_MATRIX_BATCH_REPORT.md"))
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()

    if not args.cards_dir.is_dir():
        print(f"FAIL: cards-dir 不存在: {args.cards_dir}", file=sys.stderr)
        return 2

    cards = load_cards(args.cards_dir)
    if not cards:
        print(f"FAIL: 目录内未找到 w1_match_card: {args.cards_dir}", file=sys.stderr)
        return 2

    old_sd, actuals = load_old(args.old_dashboard_data)
    if args.actuals and args.actuals.is_file():
        for fid, sc in json.loads(args.actuals.read_text(encoding="utf-8")).items():
            actuals[E.fixture_num(fid)] = (int(sc[0]), int(sc[1]))

    rows: list[dict[str, Any]] = []
    json_dump: dict[str, Any] = {}
    n_ok = n_skip = 0
    for fid, card in cards:
        actual = actuals.get(fid)
        sd = E.build_score_distribution(card, actual=actual, rho=args.rho, max_goals=args.max_goals)
        ok = sd.get("status") == "ready"
        n_ok += ok
        n_skip += (not ok)
        rows.append({
            "fid": fid, "card": card, "teams": team_names(card), "ok": ok,
            "skip_reason": sd.get("skip_reason", ""), "sd": sd,
            "read": {
                "1x2": E.parse_1x2(card) is not None,
                "ah": len(E.parse_ah_ladder(card)) > 0,
                "ou": len(E.parse_ou_ladder(card)) > 0,
            },
        })
        json_dump[fid] = sd

    meta = {
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cards_dir": str(args.cards_dir), "n_cards": len(cards),
        "n_ok": n_ok, "n_skip": n_skip, "rho": args.rho, "max_goals": args.max_goals,
    }
    report = build_report(rows, old_sd, meta)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(json_dump, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"PASS: {n_ok} ready / {n_skip} skipped. report -> {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
