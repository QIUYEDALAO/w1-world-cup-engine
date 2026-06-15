# W1 国家队强度模型 PROTOTYPE V1

> prototype=`true` · production_validated=`false` · production_wired=`false`
> 仅研究对照，不接入线上 λ，不改任何生产配置。

## 模型
- time-decayed Poisson attack/defense + L2 shrinkage (independent Poisson 1X2)；half_life=400.0d，L2=2.0。
- walk-forward：train ['2014-06-12', '2025-09-09'] (n=864) → test ['2025-09-09', '2026-04-01'] (n=217)，无未来泄漏=True，cold-start 跳过 0。

## 测试集对照
- 强度模型：RPS 0.3507，方向 0.576，优于 uniform=True。
- 同子集对照：模型 RPS 0.3556 vs 市场 RPS 0.3134（n=214）；方向 模型 0.5701 vs 市场 0.5981。

## 东道主 fallback
- 东道主无预选历史，评分仅来自少量正赛/友谊，置信低；不可当可靠强度，需后续补友谊赛/Elo。
- 是否在训练集出现：{'canada': True, 'mexico': True, 'usa': True}

## 评分（净强度 atk−def，节选）
Top：israel 0.974, bermuda 0.71, qatar 0.701, belgium 0.655, turkey 0.627, new_zealand 0.623
Bottom：egypt -0.575, rwanda -0.59, saudi_arabia -0.622, faroe_islands -0.672, tunisia -0.684, paraguay -0.693

## 边界
- 不接线上预测；模型-市场差异仅作研究复核，不表述为投注机会。
- 不构成投注/资金建议，不承诺命中率。正式 S2 验收须等 S1B 数据增强。
