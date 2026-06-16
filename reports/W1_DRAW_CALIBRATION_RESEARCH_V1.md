# W1_DRAW_CALIBRATION_RESEARCH_V1 — 指标报告

> 纯研究 / prototype / diagnostic。`research_only=true`、`production_wired=false`。
> 范围：World Cup 2018 + 2022 FULL subset (OU ladder), n=128; NOT 1081, NOT qualifiers, NOT AH/2014。
> baseline 下 draw-tension 超阈值（≥0.02）场次：**11/128**。

## 候选总览（lower is better；market_repro pass_rate 越高越好）

| 候选 | RPS | logloss_1X2 | draw ECE | draw logloss | exact-score logloss | OU2.5 ECE | BTTS ECE | repro mean err | repro pass |
|---|---|---|---|---|---|---|---|---|---|
| B0 baseline (fixed ρ) | 0.4027 | 0.9787 | 0.0281 | 0.5219 | 2.8762 | 0.0807 | 0.0686 | 0.0091 | 0.9141 |
| C1 draw-fit ρ (oracle) | 0.402 | 0.972 | 0.0323 | 0.5177 | 2.872 | 0.0807 | 0.0688 | 0.0006 | 1.0 |
| C2 draw layer | 0.402 | 0.9741 | 0.0319 | 0.5173 | 2.8716 | 0.0842 | 0.0695 | 0.0046 | 0.9688 |
| C3 parametric WF | 0.4024 | 0.9743 | 0.0331 | 0.5198 | 2.8743 | 0.0807 | 0.0686 | 0.0045 | 1.0 |

> C1 为逐场后验上界（`oracle_like` / `market_reconciliation_only`），**不是生产候选**。

## C3 walk-forward（chronological 60/20/20，仅 test 判定泛化）
- train RPS=0.3929 · val RPS=0.3652 · **test RPS=0.4671**
- baseline 同 test 段 RPS=0.468 → C3 test 优于 baseline
- train→test RPS gap=0.0742（过拟合诊断）
- ρ(features) 系数 ['bias', 'mu', 'market_draw', 'favorite_strength', 'knockout'] = [1.84848, -0.23851, -3.41651, -0.8112, 0.01171]

## 结论
- production_change_recommended: **False**
- next_stage_recommended: **None**
- 无候选在样本外**稳定**优于 baseline：C3 test RPS 仅领先 0.0009（< 噪声阈值 0.005）且 draw_logloss 未同向改善；C1 oracle 上界即便把 market-reproduction 打到近 0，outcome RPS 也只改善 0.0007——说明 11/128 的 draw 残差主要是 **market-reproduction 工件**而非预测缺陷。不建议进入下一阶段，更不接生产。
- 本研究为信号，128 场 finals-only 样本小，绝不可直接上线、不可改 DEFAULT_RHO、不可替换 score engine。

## 边界
- 128 场、finals-only、含 knockout/neutral，样本小、结构特殊；任何改善只是 research signal。
- 不改 DEFAULT_RHO / score engine / decision_policy / thresholds；不接 dashboard/predict/build；不外推 1081/预选赛。
- W1 是概率建模/赛前-赛后研究系统，非投注平台；无资金建议、无命中率承诺。
