# W1_S1B_ODDS_EXTENSION_V1

阶段：`W1_S1B_ODDS_EXTENSION_V1`
定位：用**本地提供**的 OU 赔率把国际赛数据集的一个**覆盖子集**升级到完整 W1 比分矩阵管线(OU→μ→λ→Dixon-Coles),并做校准 sanity。**不抓取、不接 API、不爬取、不采购、不访问 footiqo。**

## 1. 覆盖范围(经老板确认)

- **FULL 覆盖子集 = WC2018 + WC2022 正赛共 128 场**(本地 OU 阶梯齐全)。
- **2014**:无本地 OU → 不覆盖,`NO_LOCAL_ODDS_SOURCE_2014`,WARN,不补假数据。
- **AH**:数据源无 → `AH_MISSING_NO_SOURCE`,SKIP/WARN,不跑 AH 回测。
- **2026 当前 12 场**:仅 current odds snapshot / Forward-Ledger,**不进历史回测**。
- per-match `pipeline_mode`:覆盖 128 场 = `FULL`;其余 1081−128 仍 `1X2_ONLY`。
- `w1_full_pipeline_validated=true` **只限 128 场**;`...for_full_dataset=false`。**不外推到 1081 / 预选赛 / 2014 / AH。**

## 2. 数据来源与边界

- 输入:`data/local_odds/world_cup_odds_historical.csv`(footiqo / xBet closing odds,90 分钟常规时间;H/D/A + OU 阶梯 O05..U45 + BTTS;无 AH)。本地文件,**不入仓**(gitignored)。
- 合并只读本地文件;回测只读 import `w1_score_engine`(不改引擎、不改 `DEFAULT_RHO`)。

## 3. 链路

1. **B1 合并**(`merge_w1_odds_extension.py`):按 `match_date + home_team_id + away_team_id` 把本地 OU/1X2/BTTS 合并进数据集 → `w1_international_dataset_extended.csv`(gitignored);齐全 OU → `ou_market_available=true` + 反解 `ou_mu_derived` + `pipeline_mode=FULL`。
2. **B2 回测**(`w1_backtest_full_pipeline.py`):128 场上 1X2 去水 + OU→μ + `solve_lambdas` + `score_matrix` → 1X2/OU/BTTS/exact-score/top-scores;评估 RPS/log/Brier + OU/BTTS 校准(ECE)+ market reproduction error;walk-forward 60/20/20。

## 4. 当前结果(128 场)

- direction 0.539,mean RPS 0.4027(优于 uniform 0.48)。
- OU 校准 ECE:O1.5≈0.057、O2.5≈0.081;BTTS ECE≈0.069。
- market reproduction:117/128 在 0.02 内,mean_abs_err 0.0091。
- 定位:**128 场小样本,只做完整管线机制验证 + finals OU/BTTS 校准 sanity,不调参、不外推。**

## 5. checker

```bash
python3 scripts/check_w1_odds_extension.py          # 覆盖/FULL 仅覆盖子集/AH 缺失/无抓取
python3 scripts/check_w1_full_pipeline_backtest.py  # scope 限定、不外推、reproduction、OU/BTTS 校准、引擎只读
```

## 6. 边界

概率建模与赛前/赛后研究;不是投注平台、不输出资金建议、不承诺命中率、不把模型-市场分歧表述为投注机会。缺 OU 的样本与 AH 永远不标 FULL。
