# W1 S1B Full Pipeline Backtest V1

> pipeline_mode = `FULL` · w1_full_pipeline_validated = `true`
> 范围：World Cup 2018 + 2022（128 场）

## 总览
- FULL subset n：128
- 方向准确率：0.5391
- mean RPS：0.4027（uniform 基线 0.48， beats uniform）
- mean logloss (1X2)：0.9787 · exact-score log loss：2.8762
- mean Brier：0.5739

## Market Reproduction
- 阈值：max_abs_err < 0.02
- 通过率：0.9141（117/128）
- mean abs err：0.0091

## OU Calibration
- over_1.5: ECE=0.057, n=128
- over_2.5: ECE=0.0807, n=128
- BTTS calibration: ECE=0.0686, n=128

## Walk-Forward（chronological 60/20/20）
- train：['2018-06-14', '2022-11-23'] — rps=0.3932 market_repro=0.9079
- val：['2022-11-24', '2022-11-30'] — rps=0.3654 market_repro=0.9615
- test：['2022-11-30', '2022-12-18'] — rps=0.468 market_repro=0.8846

## 边界
- AH：SKIP/WARN — 无 AH 数据源
- 2014：SKIP/WARN — 无本地赔率覆盖
- 2026 current snapshot：不参与历史回测
- W1 是概率建模/赛前分析/风险读数系统，非投注平台
- 不输出资金建议，不承诺命中率
- 模型-市场分歧是诊断信号，非投注信号
