#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 OU/AH coverage PROBE (gap analysis only — NO external fetch).

Quantifies how much OU/AH closing-odds coverage is missing in the S1B seed set
and proposes a realistic first target (finals-first). Reads only the local
normalized dataset. Performs NO network access, NO scraping, NO purchase, and
records NO fetched odds values. This is planning, not Odds-Extension collection.
"""
from __future__ import annotations

import collections
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data/processed/international/w1_international_dataset.csv"
OUT_JSON = ROOT / "reports/w1_ou_coverage_probe_v1.json"
OUT_MD = ROOT / "reports/W1_OU_COVERAGE_PROBE_V1.md"


def main() -> int:
    if not CSV_PATH.is_file():
        raise SystemExit(f"dataset not found: {CSV_PATH} (run normalize_w1_international_dataset.py)")
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    n = len(rows)
    ou_have = sum(1 for r in rows if r.get("ou_market_available") == "True")
    ah_have = sum(1 for r in rows if r.get("ah_market_available") == "True")
    by_phase = collections.Counter(r["phase"] for r in rows)
    by_comp = collections.Counter(r["competition"] for r in rows)
    odds_1x2 = sum(1 for r in rows if r.get("odds_1x2_available") == "True")

    payload = {
        "schema_version": "W1_OU_COVERAGE_PROBE_V1",
        "external_fetch_performed": False,
        "data_collected": False,
        "scope": "gap analysis + priority only; NO fetch / scrape / purchase / new source",
        "totals": {
            "matches": n,
            "ou_available": ou_have,
            "ah_available": ah_have,
            "ou_gap": n - ou_have,
            "ah_gap": n - ah_have,
            "odds_1x2_available": odds_1x2,
        },
        "gap_by_phase": {k: {"matches": v, "ou_gap": v} for k, v in by_phase.items()},
        "gap_by_competition": {k: v for k, v in sorted(by_comp.items())},
        "recommended_priority": [
            {"tier": 1, "target": "finals (2014/2018/2022)", "matches": by_phase.get("finals", 0),
             "rationale_cn": "场次少、来源好补、信息密度高；先解锁正赛 OU→μ→λ 与总进球校准。"},
            {"tier": 2, "target": "recent strong-confederation qualifiers", "matches": "subset of " + str(by_phase.get("qualifier", 0)),
             "rationale_cn": "主流区(欧/南美)近季预选 OU 较可得；扩样本但避免小国尾部。"},
            {"tier": 3, "target": "minnow-vs-minnow qualifiers", "matches": "tail",
             "rationale_cn": "覆盖稀疏、常付费、边际收益低；暂不投入。"},
        ],
        "notes_cn": [
            "当前 OU/AH 覆盖为 0，全部需补；本探测不抓取、不采购，只给缺口与优先级。",
            "正式 Odds-Extension 采集需单独立项确认数据源与授权。",
            "不构成投注/资金建议，不承诺命中率。",
        ],
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    t = payload["totals"]
    L = [
        "# W1 OU/AH 覆盖率探测 V1（只做缺口分析，不抓取）",
        "",
        "> external_fetch_performed = `false` · data_collected = `false`",
        "> 仅缺口 + 优先级；不抓取/爬取/采购/接新数据源。正式采集需单独立项。",
        "",
        "## 缺口",
        f"- 总场次：{t['matches']}；1X2 可用 {t['odds_1x2_available']}。",
        f"- **OU 可用 {t['ou_available']} → 缺口 {t['ou_gap']}**；AH 可用 {t['ah_available']} → 缺口 {t['ah_gap']}。",
        "",
        "## 分层",
        f"- 按 phase：{dict(by_phase)}",
        f"- 按赛事：{dict(sorted(by_comp.items()))}",
        "",
        "## 建议补数优先级",
        f"- **Tier 1（先做）**：正赛 {by_phase.get('finals',0)} 场——来源好补、信息密度高，先解锁 OU→μ→λ 与总进球校准。",
        f"- **Tier 2**：主流区近季预选（{by_phase.get('qualifier',0)} 的子集）——扩样本，避开小国尾部。",
        "- **Tier 3**：小国互踢预选——覆盖稀疏、常付费、边际收益低，暂不投入。",
        "",
        "## 边界",
        "- 本阶段不抓取、不采购、不接新数据源；只产缺口与目标清单。",
        "- 不构成投注/资金建议，不承诺命中率。",
        "",
    ]
    OUT_MD.write_text("\n".join(L), encoding="utf-8")
    print(f"W1 OU coverage probe: matches={n} ou_gap={t['ou_gap']} ah_gap={t['ah_gap']} (no fetch; finals-first target={by_phase.get('finals',0)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
