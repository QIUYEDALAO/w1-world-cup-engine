# W1_TEAM_STRENGTH_PROTOTYPE_V1

阶段：`W1_FORWARD_LEDGER_AND_S2_PROTOTYPE_V1`（S 轨）
定位：**prototype，不是生产验收**。建立第一个独立于市场的国家队攻防强度估计，并和已有 1X2-only 市场基准做 walk-forward 对照。

## 1. 红线

- **不接入线上 λ**：本 prototype 只产研究报告，不写回 `w1_score_engine.py`、不改生产预测、不改 `DEFAULT_RHO` / `decision_policy` / `odds thresholds`。
- **无未来泄漏**：时序切分，评估测试集时只用测试期之前的比赛拟合强度。
- 强制标 `prototype=true` / `production_validated=false`。

## 2. 模型（prototype 版）

- 泊松攻防模型：`log λ_home = c + home_adv·(非中立) + atk[home] − def[away]`，`log λ_away = c + atk[away] − def[home]`。
- **时间衰减**：权重 `exp(−ln2·age_days/half_life)`，half_life≈400 天（国家队代际衰减快）。
- **shrinkage / partial pooling**：对 atk/def 加 L2 正则，向全局先验(0=联盟均值)收缩；低样本球队自然被拉向先验。
- **东道主 fallback**：USA/Mexico/Canada 无预选历史 → 评分高度依赖少量正赛/友谊，报告显式标注其评分来源不足、置信低；不可当作可靠强度。
- 1X2 由 λ_home/λ_away 的独立泊松网格派生（prototype 暂不加 Dixon-Coles ρ，避免与生产参数耦合）。

## 3. 评估

- 时序 60/20/20，测试集=最近 20%（train 全部早于 test）。
- 在测试集上对比：**强度模型 vs 1X2 市场基准 vs uniform**，指标 RPS / log-score / Brier / 方向。
- 结论口径：看模型能否优于 uniform、能否接近市场;**不得**宣称"跑赢市场"或可用于生产。

## 4. 复现

```bash
python3 scripts/w1_team_strength_prototype.py      # 拟合 + 测试集对照，产出报告
python3 scripts/check_w1_team_strength_prototype.py # 校验 prototype 标签/无泄漏/不接线上
```

## 5. 边界

研究用途；不接线上预测;不是投注平台、不输出资金建议、不承诺命中率;模型-市场差异仅作研究复核，不表述为投注机会。正式 S2 验收须等 S1B 数据增强(连续国际赛 + OU/AH)后再做。
