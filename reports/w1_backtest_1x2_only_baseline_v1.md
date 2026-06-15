# W1 1X2-only 市场基准回测 V1

> pipeline_mode = `1X2_ONLY` · w1_full_pipeline_validated = `false`
> 仅市场 1X2 校准基准；无 OU → 无比分矩阵，**不验证完整 W1 管线 / 总进球 / AH**。

## 总览
- 样本 n：1074
- 方向准确率：0.635
- mean RPS：0.2977（uniform 基线 0.4817，beats_uniform=True）
- mean logloss：0.7883 · mean Brier：0.4597
- 主胜概率校准 ECE：0.0241

## 分层（节选）
- phase=finals: n=192 dir=0.5781 rps=0.3976
- phase=qualifier: n=882 dir=0.6474 rps=0.276
- fav 0.50-0.70: n=367 dir=0.5913 rps=0.3473
- fav<0.50 (close): n=321 dir=0.3988 rps=0.4427
- fav>=0.70: n=386 dir=0.8731 rps=0.13

## Walk-forward（时间切分）
- train ['2014-06-12', '2025-03-25'] n=644 rps=0.3101
- test ['2025-09-09', '2026-04-01'] n=215 rps=0.312

## 边界
- 市场基准衡量市场本身，非 W1 独立模型；S2 增量须相对此基准用样本外证明。
- 不构成投注/资金建议，不承诺命中率。
