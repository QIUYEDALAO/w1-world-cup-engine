# W1_FULL_PIPELINE_ANOMALY_REVIEW_V1

阶段：`W1_FULL_PIPELINE_ANOMALY_REVIEW_V1`
定位：**纯诊断**。复核 S1B-Odds-Extension 128 场 FULL replay 中 market reproduction 超阈值(max abs err ≥ 0.02)的 11 场,确认根因、排除数据问题、记录为已知限制。**不改引擎、不调参、不 refetch。**

## 1. 红线

- 不改 `scripts/w1_score_engine.py`、`DEFAULT_RHO`、`config/w1_decision_policy.json`、`config/w1_odds_movement_thresholds.json`。
- 不抓取/不访问外部源/不 refetch;只读已有本地扩展数据集 + 只读 import `w1_score_engine`。
- 平局结构张力**记录为已知限制,不在本阶段"修"**(任何修法都要动引擎/ρ → 单独研究阶段 `W1_DRAW_CALIBRATION_RESEARCH`)。
- 无投注/资金/命中率表达。

## 2. 预判(轻量复算已得)

11/128 超阈值样本:**11/11 的最差复现项都是"平局(D)"**,主客分裂复现良好,误差几乎全落在平局概率(平均 |draw_gap|≈0.028)。

根因:市场隐含 DC 方法中,μ 由 OU 固定、ρ 固定,只用一个 δ 拟合 H/D/A 三目标 → δ 只能调主客倾斜,**平局率被 μ、ρ 钉死**;市场平局定价偏离 μ+ρ 所能产生的平局率时,残差全甩到 D。**这是方法固有张力,不是数据 bug。**

数据问题可结构性排除:覆盖行是按**精确** `(date, home_id, away_id)` 合并的 → orientation/队名不可能错;μ 来自完整 OU 阶梯。本阶段仍逐场显式核对以闭环。

## 3. 链路

- `review_w1_full_pipeline_anomaly.py`:复算 128 → 抽 11 → 逐场 dump(devig 1X2 / model_hda / 各项误差 / 最差项 / draw_gap / μ / δ / λ / fav / fit_sse / 实际比分)→ 归因分类。
- 分类桶:`DRAW_RATE_TENSION`(误差集中于 D,主客均 <0.02)/ `MU_1X2_INCONSISTENCY` / `ORIENTATION_TEAM` / `OU_LADDER_SELECTION` / `EXTREME_FAVORITE` / `OTHER`。
- 产出报告 + checker;结论 + 未来研究候选(仅登记)。

## 4. 复现

```bash
python3 scripts/review_w1_full_pipeline_anomaly.py
python3 scripts/check_w1_anomaly_review.py
```

## 5. 边界

赛后诊断研究;不是投注平台、不输出资金建议、不承诺命中率、不把模型-市场分歧表述为投注机会。
