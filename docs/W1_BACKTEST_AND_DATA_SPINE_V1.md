# W1_BACKTEST_AND_DATA_SPINE_V1 (S1A folded into S1B)

阶段：`W1_S0_SAFE_OUTPUT_AND_S1B_SEED_V1`
定位：最小回测框架 + 数据中台。S1A（通用回测框架）并入 B 轨——1X2-only 基准 + 指标/校准/分层/walk-forward 就是当前最小框架，不另造空壳。

## 1. 框架组成

- **数据中台**：`normalize_w1_international_dataset.py` → 统一 `w1_international_dataset.csv`（见 `W1_INTERNATIONAL_BACKTEST_DATASET_V1`）。
- **回测内核**：`w1_backtest_engine.py` → 市场 1X2 去水基准评估。
- **指标**：方向准确率、RPS、log-score、Brier，且与 uniform 基线对比（beats_uniform）。
- **校准**：主胜概率 reliability + ECE。
- **分层 slice**：phase（预选/正赛）、competition、neutral_site、favorite_strength 档。
- **walk-forward**：按日期 60/20/20 时间切分（train 过去 → test 未来）；市场基准无拟合参数，切分为 S2 复用 + 诚实 test-set 汇报。
- **leakage guard**：预测只用赛前 1X2 赔率；赛后字段（比分/xG/统计）只作标签，禁止进入预测；engine 内显式记录并由 checker 校验。

## 2. 当前基线读数（1X2-only）

`reports/w1_backtest_1x2_only_baseline_v1.(json|md)`：n≈1074，方向准确率约 0.63，mean RPS 约 0.30（优于 uniform 0.48），主胜 ECE 约 0.024。

**强弱档**：强热门(>=0.70) 方向≈0.87；接近盘(<0.50) ≈0.40——印证强弱悬殊场次信息更足、接近盘更难，这正是后续强度模型要分层评估的地方。

## 3. 它能/不能回答什么

能：市场 1X2 本身的方向与校准质量、按域/赛事/强弱分层、时间外推稳定性。
不能（缺 OU）：比分矩阵复现、总进球/大小球校准、AH 校验、精确比分。→ 一律 `pipeline_mode=1X2_ONLY`、`w1_full_pipeline_validated=false`。

**关键**：1X2-only 基准衡量的是**市场**，不是 W1 独立模型。S2 国家队强度模型的任何"增量"，必须相对此基准、用 walk-forward 样本外证明，否则不得进入正式 λ。

## 4. checker

```bash
python3 scripts/check_w1_international_dataset.py          # schema/90min/finished/覆盖/pipeline_mode
python3 scripts/check_w1_team_name_reconciliation.py      # BLOCKER：未映射/一对多
python3 scripts/check_w1_host_no_qualifier_history.py     # WARN：东道主缺预选
python3 scripts/check_w1_team_sample_sparsity.py          # 报告：每队样本量 + 数据质量报告
python3 scripts/check_w1_backtest_spine.py                # 1X2_ONLY 标签/leakage/walk-forward
```

数据集为 gitignored，本地生成；checker 在数据缺失时安全 SKIP（team-reconciliation 仍校验已入仓的别名表 + W1 fixtures）。

## 5. 边界

概率建模与赛前/赛后研究；不是投注平台、不输出资金建议、不承诺命中率、不把模型-市场分歧表述为投注机会。
