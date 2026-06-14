# W1 Recommendation Accuracy Audit

生成时间：2026-06-14T07:34:47.857151+00:00

## 1. 审计范围

本报告只读取现有本地数据，统计所有已有 actual_score 或 post_match_calibration 的已完赛 match_records。runtime state 仅作为辅助背景，不作为主数据源。

输入优先级：

1. `reports/dashboard/assets/w1_dashboard_data.json`
2. `data/results/round1_results.json`
3. `data/processed/match_cards/`
4. `data/manual_lineups/`
5. `state/` runtime 仅辅助

## 2. 核心指标

- total_completed_matches：4
- direction_accuracy：50.0%
- primary_score_accuracy：0.0%
- secondary_score_accuracy：25.0%
- primary_or_secondary_accuracy：25.0%
- score_pool_coverage：50.0%
- mean_actual_score_probability：0.0701
- mean_rps_1x2：0.5031
- mean_exact_score_log_loss：3.0662

## 3. 逐场表

| fixture_id | match | actual_score | predicted_direction | actual_direction | direction_hit | primary_score | secondary_score | score_pool_hit | actual_score_probability | rps_1x2 | exact_score_log_loss | lineup_source | confirmed_lineup | data_quality |
|---|---|---:|---|---|---|---:|---:|---|---:|---:|---:|---|---|---|
| 1489369 | 墨西哥 vs 南非 | 2-0 | 主胜 | 主胜 | 是 | 1-0 | 0-0 | 是 | 0.1600 | 0.1162 | 1.8325 | missing | 否 | partial |
| 1489370 | 美国 vs 巴拉圭 | 4-1 | 主胜 | 主胜 | 是 | 1-1 | 1-1 | 否 | 0.0125 | 0.3301 | 4.3797 | missing | 否 | partial |
| 1489373 | 卡塔尔 vs 瑞士 | 1-1 | 客胜 | 平局 | 否 | 0-2 | 1-1 | 是 | 0.0777 | 0.6007 | 2.5551 | OpenClaw verified lineup snapshot | 是 | partial |
| 1539001 | 澳大利亚 vs 土耳其 | 2-0 | 客胜 | 主胜 | 否 | 0-1 | 1-1 | 否 | 0.0303 | 0.9654 | 3.4974 | manual_verified | 是 | partial |

## 4. 指定样本复盘

### Qatar vs Switzerland 1-1

Qatar vs Switzerland 1-1 是热门未胜样本。score pool 覆盖到 1-1，但方向层面暴露出热门胜出与实际平局之间的偏差。该样本更适合进入 RPS/log score 累计评估，而不是被简单记为成功。

### USA vs Paraguay 4-1

USA vs Paraguay 4-1 是尾部打开样本。平手附近的市场结构并没有阻止大比分路径出现，说明 open-game mass 和尾部概率必须保留，不能用 OU 或 AH 直接锁死比分。

### Australia vs Turkey 2-0

Australia vs Turkey 2-0 是方向性失误样本。当前矩阵给出的 Turkey 方向更高，但实际 Australia 2-0。该场应作为 calibration 样本进入累计评估，不因单场调权重。

## 5. 最差与最好样本

### worst_3_by_log_loss

- 1489370 美国 vs 巴拉圭 4-1：exact_score_log_loss=4.3797
- 1539001 澳大利亚 vs 土耳其 2-0：exact_score_log_loss=3.4974
- 1489373 卡塔尔 vs 瑞士 1-1：exact_score_log_loss=2.5551

### best_3_by_actual_score_probability

- 1489369 墨西哥 vs 南非 2-0：actual_score_probability=0.1600
- 1489373 卡塔尔 vs 瑞士 1-1：actual_score_probability=0.0777
- 1539001 澳大利亚 vs 土耳其 2-0：actual_score_probability=0.0303

## 6. 审计结论

- 精确比分命中率不是唯一指标；它对小样本高度敏感。
- score_pool 覆盖不等于推荐成功，只说明实际比分进入了候选路径。
- RPS/log score 才是当前主评估口径，用于衡量方向概率和精确比分概率的损失。
- 当前样本量小，不允许调权重。
- Australia 2-0 Turkey 是方向性失误样本。
- Qatar 1-1 Switzerland 是热门未胜样本。
- USA 4-1 Paraguay 是尾部打开样本。
- 本审计不改变 score matrix、rho、PLAY_GUARD，也不根据结果调参。

## 7. 合规边界

本报告仅用于赛前/赛后分析研究与专家审阅，不提供交易、执行或资金操作意见，不承诺命中率。
