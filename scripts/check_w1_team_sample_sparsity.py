#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 S1B per-team sample sparsity report + consolidated data-quality report.

Report-only (not a blocker). Writes reports/W1_INTERNATIONAL_DATASET_QUALITY_V1.md
with coverage, dirty-label locations, host gaps, and per-team sparsity so the
strength model (S2) can apply time-decay / shrinkage instead of naive means.
"""
from __future__ import annotations

import collections
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data/processed/international/w1_international_dataset.csv"
COV = ROOT / "data/processed/international/w1_international_coverage.json"
ALIASES = ROOT / "config/w1_team_aliases.json"
OUT_MD = ROOT / "reports/W1_INTERNATIONAL_DATASET_QUALITY_V1.md"
LOW_SAMPLE = 5


def main() -> int:
    if not CSV_PATH.is_file():
        print("SKIP sparsity report: dataset not generated")
        return 0
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    cov = json.loads(COV.read_text(encoding="utf-8")) if COV.is_file() else {}
    teams = json.loads(ALIASES.read_text(encoding="utf-8")).get("teams", {}) if ALIASES.is_file() else {}

    tot, qual, fin, last = collections.Counter(), collections.Counter(), collections.Counter(), {}
    for r in rows:
        for side in ("home", "away"):
            tid = r[f"{side}_team_id"]
            tot[tid] += 1
            if r["phase"] == "qualifier":
                qual[tid] += 1
            else:
                fin[tid] += 1
            if r.get("match_date"):
                last[tid] = max(last.get(tid, ""), r["match_date"])
    low = [t for t in tot if tot[t] < LOW_SAMPLE]

    L = ["# W1 国际赛种子集数据质量报告 V1", "",
         "> S1B-Seed · pipeline_mode = `1X2_ONLY` · w1_full_pipeline_validated = `false`", "",
         "## 1. 覆盖",
         f"- 总场次：{cov.get('total_rows')}（{cov.get('by_sheet')}）",
         f"- 1X2 赔率可用：{cov.get('odds_1x2_available')}",
         f"- OU 可用：{cov.get('ou_market_available')} · AH 可用：{cov.get('ah_market_available')}（**缺失 → 仅 1X2-only**）",
         f"- xG（预选）：{cov.get('xg_available_qualifiers')}/{cov.get('qualifier_rows')}（部分覆盖，非必需字段）",
         f"- 比赛统计：{cov.get('stats_available_total')} · 犯规：{cov.get('fouls_available_total')}",
         "",
         "## 2. 脏 Finished 标签（仅定位，建模用 90 分钟比分 + ET/点球推导）"]
    for d in cov.get("dirty_finished_labels", []):
        L.append(f"- {d['sheet']}: {d['match']} {d['score']} 标为 `{d['finished_label_raw']}`（实际无加时/点球）")

    L += ["", "## 3. 东道主缺预选历史（WARN，gate 正式 S2）"]
    for tid, e in teams.items():
        if e.get("host_auto_qualified_2026"):
            L.append(f"- {e['canonical_name']}（{tid}）：预选 {qual.get(tid,0)} 场 / 总 {tot.get(tid,0)} 场 · 最近 {last.get(tid,'–')}")

    L += ["", f"## 4. 样本稀疏（total < {LOW_SAMPLE} 的球队：{len(low)} 支；强度模型需时间衰减 + shrinkage）",
          "", "| team_id | 总 | 预选 | 正赛 | 最近 |", "|---|---:|---:|---:|---|"]
    for tid, c in sorted(tot.items(), key=lambda kv: kv[1], reverse=True)[:15]:
        L.append(f"| {tid} | {c} | {qual.get(tid,0)} | {fin.get(tid,0)} | {last.get(tid,'–')} |")
    L += ["", f"低样本球队（total<{LOW_SAMPLE}）：" + ", ".join(sorted(low)[:40]) + (" …" if len(low) > 40 else ""),
          "", "## 边界", "- 仅赛前分析与赛后研究；不构成投注/资金建议，不承诺命中率。", ""]
    OUT_MD.write_text("\n".join(L), encoding="utf-8")
    print(f"W1 team sample sparsity report written: teams={len(tot)} low_sample={len(low)} -> {OUT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
