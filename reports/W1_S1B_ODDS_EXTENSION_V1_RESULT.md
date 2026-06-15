# W1_S1B_ODDS_EXTENSION_V1 结果报告

生成时间：2026-06-15 CST
origin：`git@github.com:QIUYEDALAO/w1-world-cup-engine.git`
阶段基线 HEAD：`c11ea3e`
执行边界：仅消费本地 OU 文件(无外部抓取);只在 128 场覆盖子集解锁完整管线;不外推 1081;AH/2014 不覆盖。

## 1. commit 列表（提交粒度）

| commit | 内容 |
|---|---|
| 1/3 | spec + schema + §7 注册（`docs/W1_S1B_ODDS_EXTENSION_V1.md`、`config/w1_odds_extension_schema.json`、`reports/W1_EXPERT_PROJECT_REPORT.md`） |
| 2/3 | 合并 + 完整回测 + checker（merge / full_pipeline 脚本 + 2 checker + backtest 报告） |
| 3/3 | 本 RESULT 报告 |

实际 hash 以 `git log --oneline` 为准;`.git` 锁阻挡时见第 9 节本机收尾命令。

## 2. 文件清单

**入仓**：`docs/W1_S1B_ODDS_EXTENSION_V1.md`、`config/w1_odds_extension_schema.json`、`scripts/merge_w1_odds_extension.py`、`scripts/w1_backtest_full_pipeline.py`、`scripts/check_w1_odds_extension.py`、`scripts/check_w1_full_pipeline_backtest.py`、`reports/w1_backtest_full_pipeline_v1.(json|md)`、`reports/W1_EXPERT_PROJECT_REPORT.md`(§7)。
**不入仓**(gitignored)：`data/local_odds/*.csv`、`data/processed/international/w1_international_dataset_extended.csv`、`w1_odds_extension_coverage.json`、`w1_current_odds_snapshot_quality.json`。

## 3. checker 结果（实跑，全 PASS）

本阶段新增 2：`check_w1_odds_extension`（covered=128、FULL/validated 仅覆盖子集、AH 缺失、合并无外部抓取、本地 odds gitignored）、`check_w1_full_pipeline_backtest`（n=128、scope 限 2018+2022 不外推、market reproduction、OU/BTTS 校准、引擎只读）。
负向测试：把一条预选赛行改成 `FULL` → checker 立即 FAIL；还原后 PASS。
无回归：上两阶段新增 checker（9）+ 核心（9）+ 守门（2）全部 PASS。

## 4. FULL subset 覆盖数

- **FULL 覆盖子集 = 128 场**（WC2018 64 + WC2022 64）。
- 2014（64）未覆盖：`NO_LOCAL_ODDS_SOURCE_2014`（WARN）。
- per-match：覆盖 128 = `FULL`；其余 1081−128 仍 `1X2_ONLY`。
- `w1_full_pipeline_validated_for_full_dataset = false`；仅 128 场子集为 true。

## 5. 主要指标（128 场 FULL replay）

- direction 0.539；**mean RPS 0.4027**（uniform 0.48，beats=true）；logloss(1X2) 0.979；exact-score logloss 2.876。
- **OU 校准 ECE**：O1.5 ≈ 0.057、O2.5 ≈ 0.081；**BTTS ECE ≈ 0.069**。
- **market reproduction**：117/128 在 0.02 内（91.4%），mean_abs_err 0.0091 —— 引擎对市场 1X2 复现良好。
- walk-forward 60/20/20（按 match_date 时序，无未来泄漏）。
- 定位：**完整管线机制验证 + finals OU/BTTS 校准 sanity；128 场偏小,不调参、不外推。**

## 6. WARN_ONLY

- 2014 无本地 OU → 不覆盖（WARN，不补假数据）。
- AH 数据源缺失 → AH 回测 SKIP（WARN）。
- 128 场样本小：只做 sanity，不据此调 rho/score matrix/政策/阈值。
- 不外推到 1081 / 预选赛；2026 的 12 场仅 current snapshot，不进历史回测。

## 7. 红线确认（实测）

- 未改 `scripts/w1_score_engine.py`、`DEFAULT_RHO=-0.057766`、`config/w1_decision_policy.json`、`config/w1_odds_movement_thresholds.json`（工作区 diff 不含这些文件;DEFAULT_RHO 原值在位）。
- 回测**只读 import** `w1_score_engine`（用其 `solve_lambdas`/`score_matrix`/`DEFAULT_RHO`），未改引擎。
- 合并/回测脚本**无 requests/urllib/web_fetch/socket** 等外部抓取；未访问 footiqo/API。
- 未覆盖样本不标 FULL；本地 odds 与扩展 CSV 未入仓；无投注/资金/命中率表达。

## 8. git status / push

- 工作区:本阶段脚本/报告/spec 已 `git add`;`data/local_odds/`、`data/processed/international/` 仍 gitignored 未跟踪。
- push:沙箱走 SSH 连不上 origin，需本机 push（见第 9 节）。

## 9. BLOCKER / 本机收尾命令

代码/逻辑:none。环境:沙箱 `.git` 锁(EPERM)与 SSH push 限制(与前几阶段同)。本机执行：

```bash
cd <repo>
rm -f .git/HEAD.lock .git/index.lock; git worktree prune
git add docs/W1_S1B_ODDS_EXTENSION_V1.md config/w1_odds_extension_schema.json reports/W1_EXPERT_PROJECT_REPORT.md
git commit -m "W1_S1B_ODDS_EXTENSION_V1 (commit 1/3): spec + schema + checker registration"
git add scripts/merge_w1_odds_extension.py scripts/w1_backtest_full_pipeline.py scripts/check_w1_odds_extension.py scripts/check_w1_full_pipeline_backtest.py reports/w1_backtest_full_pipeline_v1.json reports/w1_backtest_full_pipeline_v1.md
git commit -m "W1_S1B_ODDS_EXTENSION_V1 (commit 2/3): local OU merge + 128-match FULL pipeline replay + checkers"
git add reports/W1_S1B_ODDS_EXTENSION_V1_RESULT.md
git commit -m "W1_S1B_ODDS_EXTENSION_V1 (commit 3/3): RESULT"
git push origin main
```

## 10. 下一阶段建议

1. **扩 OU 覆盖**：按覆盖率探测 Tier1→Tier2，补主流区近季预选 OU(仍本地文件,不抓取),把 FULL 子集从 128 往外扩;每扩一批都重标 scope,不外推。
2. **AH 数据**：若拿到本地 AH 文件,再开 AH 校验(当前 SKIP)。
3. **Forward-Ledger 持续跑**;**S2 仍 prototype** 迭代(加对手强度调整),达标前不接线上。

边界不变：概率建模与赛前/赛后研究;不是投注平台,不输出资金建议,不承诺命中率,不把模型-市场分歧表述为投注机会。
