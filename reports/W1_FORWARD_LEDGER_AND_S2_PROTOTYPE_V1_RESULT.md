# W1_FORWARD_LEDGER_AND_S2_PROTOTYPE_V1 结果报告

生成时间：2026-06-15 CST
origin：`git@github.com:QIUYEDALAO/w1-world-cup-engine.git`
阶段基线 HEAD：`e9b31cc`
执行边界：F 轨只落库本地/手动/空值赛前字段(无外部抓取);S2 只做 prototype、不接线上 λ;O 轨只做覆盖率探测。

## 1. commit 列表（提交粒度）

| commit | 内容 |
|---|---|
| 1/3 | Forward-Ledger（spec/schema/snapshot/checker + §7 注册 + .gitignore） |
| 2/3 | S2 强度 prototype + OU/AH 覆盖率探测（脚本/报告/checker） |
| 3/3 | 本 RESULT 报告 |

实际 hash 以 `git log --oneline` 为准;若 `.git` 锁阻挡见第 9 节收尾命令。

## 2. 文件清单

**F 轨**：`docs/W1_FORWARD_LEDGER_V1.md`、`config/w1_forward_ledger_schema.json`、`scripts/snapshot_w1_forward_ledger.py`、`scripts/check_w1_forward_ledger.py`。
**S 轨**：`docs/W1_TEAM_STRENGTH_PROTOTYPE_V1.md`、`scripts/w1_team_strength_prototype.py`、`scripts/check_w1_team_strength_prototype.py`、`reports/w1_team_strength_prototype_v1.(json|md)`。
**O 轨**：`scripts/probe_w1_ou_coverage.py`、`scripts/check_w1_ou_coverage.py`、`reports/w1_ou_coverage_probe_v1.json`、`reports/W1_OU_COVERAGE_PROBE_V1.md`。
**公共**：`reports/W1_EXPERT_PROJECT_REPORT.md`(§7 注册 3 个新 checker)、`.gitignore`(加 `data/forward_ledger/`)。
**不入仓**(gitignored)：`data/forward_ledger/*.jsonl`、`data/processed/international/*`、`data/raw/*`。

## 3. checker 结果（实跑，全 PASS）

本阶段新增 3：`forward_ledger`、`team_strength_prototype`、`ou_coverage`。
负向测试：向 prototype 注入 `import w1_score_engine` → checker 立即 FAIL；还原后 PASS（证明"不接线上"约束真生效）。
无回归：上一阶段 6 个新 checker + 核心 9 + 守门 2 全部 PASS。

## 4. 三轨产出摘要

**F 轨 Forward-Ledger**
- 对 12 场未开赛 fixture 落库赛前快照（append-only，`as_of=2026-06-15T15:26:45Z`）。
- 每条含可用性标志（lineup/odds/weather/referee/tactical）；**零赛后字段**（checker 强制）。
- 西班牙 vs 佛得角示例：snapshot_phase=T-1h，odds/weather/tactical 可用、lineup/referee 未确认。

**S 轨 S2 强度 prototype（研究对照，未接线上）**
- 时间衰减泊松攻防 + L2 shrinkage + 东道主 fallback；时序 80/20：train 864 → test 217，**无未来泄漏**。
- 测试集：模型 RPS **0.3507**（优于 uniform 0.48）；**同子集 模型 0.3556 vs 市场 0.3134**——**模型优于 uniform 但尚不及市场**（诚实结论，支撑"prototype 不做生产验收"）。
- 已知 prototype 局限：小国在弱组刷数据使净强度评分偏高（如 bermuda），需更强对手强度调整 + 更重 shrinkage;属研究层 caveat，不影响线上。
- 强制标 `prototype=true`/`production_validated=false`/`production_wired=false`。

**O 轨 OU/AH 覆盖率探测（不抓取）**
- OU/AH 当前覆盖 0 → 缺口 **1081/1081**。
- 优先级：Tier1 正赛 **192** 场（先解锁 OU→μ→λ）→ Tier2 主流区近季预选 → Tier3 小国尾部暂不投入。
- `external_fetch_performed=false`、`data_collected=false`（checker 强制）。

## 5. 红线确认（实测）

- 未改 `scripts/w1_score_engine.py`、`DEFAULT_RHO`、`config/w1_decision_policy.json`、`config/w1_odds_movement_thresholds.json`（均不在本阶段 diff）。
- **S2 不接入线上 λ / 不写回生产**（checker 静态断言无 `import w1_score_engine` 等耦合 + `production_wired=false`）。
- **Forward-Ledger 无赛后/比分字段**（checker leakage guard）。
- **S2 walk-forward 无未来泄漏**（train_end ≤ test_start，checker 断言）。
- **O 轨无外部抓取/采购**（checker 静态断言无 requests/urllib/web_fetch 等 + coverage-only）。
- 无投注/资金/命中率承诺表达;原始/生成大数据未入仓。

## 6. WARN_ONLY

- S2 仅 prototype：当前不及市场基准，**不得**当生产用;正式验收须等 S1B 数据增强（连续国际赛 + OU/AH）。
- Forward-Ledger 现仅 12 场（本届剩余），需持续逐场积累。
- OU/AH 仍缺，完整 W1 管线仍未验收（`1X2_ONLY` 不变）。
- prototype 评分对小样本/弱组球队偏噪（需对手强度调整 + 更重 shrinkage）。

## 7. 是否回滚

否。三轨产物齐全、checker 全 PASS、红线未触碰。

## 8. BLOCKER

代码/逻辑层面：none。环境层面：若沙箱 `.git` 锁阻挡 commit/push（与前两阶段同一限制），见第 9 节本机收尾命令（不需重写代码）。

## 9. 本机收尾命令（若 .git 锁阻挡）

```bash
cd <repo>
rm -f .git/HEAD.lock .git/index.lock; git worktree prune
git add docs/W1_FORWARD_LEDGER_V1.md config/w1_forward_ledger_schema.json scripts/snapshot_w1_forward_ledger.py scripts/check_w1_forward_ledger.py reports/W1_EXPERT_PROJECT_REPORT.md .gitignore
git commit -m "W1_FORWARD_LEDGER_AND_S2_PROTOTYPE_V1 (commit 1/3): Forward-Ledger"
git add docs/W1_TEAM_STRENGTH_PROTOTYPE_V1.md scripts/w1_team_strength_prototype.py scripts/check_w1_team_strength_prototype.py reports/w1_team_strength_prototype_v1.json reports/w1_team_strength_prototype_v1.md scripts/probe_w1_ou_coverage.py scripts/check_w1_ou_coverage.py reports/w1_ou_coverage_probe_v1.json reports/W1_OU_COVERAGE_PROBE_V1.md
git commit -m "W1_FORWARD_LEDGER_AND_S2_PROTOTYPE_V1 (commit 2/3): S2 strength prototype + OU coverage probe"
git add reports/W1_FORWARD_LEDGER_AND_S2_PROTOTYPE_V1_RESULT.md
git commit -m "W1_FORWARD_LEDGER_AND_S2_PROTOTYPE_V1 (commit 3/3): RESULT"
git push origin main
```

## 10. 下一阶段建议

1. **S1B-Odds-Extension**（正赛 192 场优先补 OU/AH）→ 解锁完整 W1 管线与总进球/AH 校准。
2. **Forward-Ledger 持续运行**：每个比赛日 + 本届剩余场次逐场快照，攒因子消融数据。
3. **S2 迭代（仍 prototype）**：加对手强度调整 + 更重 shrinkage + 友谊赛/Elo 补东道主;持续和市场基准 walk-forward 对照，达标前不接线上。

边界不变：W1 是概率建模、赛前分析、风险读数与赛后复盘系统;不是投注平台,不输出资金建议,不承诺命中率,不把模型-市场分歧表述为投注机会。
