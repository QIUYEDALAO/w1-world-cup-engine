# W1_INTERNATIONAL_BACKTEST_DATASET_V1 (S1B-Seed)

阶段：`W1_S0_SAFE_OUTPUT_AND_S1B_SEED_V1`（S1B 子轨）
定位：把国家队历史数据做成统一、可回测、防泄漏的种子集，**解决"错域"问题**（此前回测只有五大俱乐部联赛）。

## 1. 三段式定位（经四轮评审确认）

- **S1B-Seed（本阶段）**：当前 1081 场国家队比赛种子集 → 国家队域起点、1X2-only 基准、强度 prototype、赛果/xG/统计研究。
- **S1B-Odds-Extension（后续）**：给这些比赛补 OU/AH 收盘赔率 → 才能复现完整 W1 OU→μ→λ 比分矩阵管线、总进球/大小球校准、AH 校验。
- **S1B-Forward-Ledger（后续，最干净）**：从本届世界杯 + 国际比赛日开始，赛前完整快照逐场落库 → lineup/天气/相位等 research_features 的唯一可靠来源。

## 2. 数据来源与实测

源文件：`data/raw/international/WorldCup2026.xlsx`（4 sheet，**不入仓**）。

| sheet | 场次 | 1X2 | xG | 备注 |
|---|---:|---|---|---|
| WorldCup2026Qualifiers | 889 | ✓(avg/max) | 部分 339 | 真实主客场 |
| WorldCup2022 | 64 | ✓(bet365/Betfair/avg) | ✗ | 中立场(除卡塔尔) |
| WorldCup2018 | 64 | ✓(Pinnacle/avg) | ✗ | 中立场(除俄罗斯) |
| WorldCup2014 | 64 | ✓(bet365/Pinnacle/avg) | ✗ | 中立场(除巴西) |

合计 **1081** 场。**OU/AH 全缺** → `pipeline_mode=1X2_ONLY`。

## 3. 已知数据问题与处理（实测确认）

- **xG 非全量**：仅预选赛 339/889 有值；正赛无 xG。→ research/辅助字段，非必需。
- **统计非全量**：射门/角球 909、犯规 875。→ 覆盖率入报告，不可假设全量。
- **WorldCup2022 `Finished` 脏标签**：5 行（乌拉圭-韩国 0-0、瑞士-喀麦隆 1-0、摩洛哥-克罗地亚 0-0、阿根廷-沙特 1-2 标 Penalties；塞内加尔-荷兰 0-2 标 Extra time）→ 不信 `Finished`，用 ET/点球字段非空推导 `finish_type`，并定位脏行。2018/2014 自洽。
- **重复 HGP 列**：→ `home_penalties` / `away_penalties`。
- **队名跨源不一致**：Turkey/Türkiye、Curacao/Curaçao、D.R. Congo/Congo DR（与 Congo 区分）等 → `config/w1_team_aliases.json` 归一；未映射 = BLOCKER。
- **东道主无预选历史**：USA/Mexico/Canada 自动出线，预选 0 场 → 标 `host_auto_qualified_2026`，WARN，gate 正式 S2。
- **样本稀疏**：37 支球队 total<5 → 强度模型须时间衰减 + shrinkage。

## 4. 产物

- `data/processed/international/w1_international_dataset.csv`（统一 schema，**不入仓**，本地生成）。
- `data/processed/international/w1_international_coverage.json`（覆盖摘要）。
- `config/w1_international_dataset_schema.json`（字段/角色/硬规则，入仓）。
- `config/w1_team_aliases.json`（canonical team-id 映射，入仓）。
- `reports/W1_INTERNATIONAL_DATASET_QUALITY_V1.md`（数据质量报告，入仓）。

## 5. 复现

```bash
# 把上传的世界杯工作簿放到 data/raw/international/WorldCup2026.xlsx
python3 scripts/normalize_w1_international_dataset.py --rebuild-aliases   # 生成/刷新队名表
python3 scripts/normalize_w1_international_dataset.py                     # 生成统一 CSV + 覆盖摘要
```

## 6. 边界

国家队域研究与回测，不是投注平台、不输出资金建议、不承诺命中率、不把模型-市场分歧表述为投注机会。OU/AH 补齐前，本种子集只能做 1X2-only，不能宣称完整 W1 管线验收。
