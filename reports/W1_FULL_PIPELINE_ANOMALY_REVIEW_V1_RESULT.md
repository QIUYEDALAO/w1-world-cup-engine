# W1_FULL_PIPELINE_ANOMALY_REVIEW_V1 结果报告

生成时间：2026-06-16 CST
origin：`git@github.com:QIUYEDALAO/w1-world-cup-engine.git`
执行边界：纯诊断;不改 engine/ρ/decision_policy/thresholds;不 refetch;不抓取。

## 1. commit 列表

| commit | 内容 |
|---|---|
| 1/2 | spec + 诊断脚本 + checker + §7 注册 |
| 2/2 | 异常复核报告 + 本 RESULT |

实际 hash 以 `git log --oneline` 为准;`.git` 锁阻挡时见第 8 节本机收尾命令。

## 2. 文件清单

- `docs/W1_FULL_PIPELINE_ANOMALY_REVIEW_V1.md`（spec）
- `scripts/review_w1_full_pipeline_anomaly.py`（诊断:复算 128 → 抽 11 → 归因）
- `scripts/check_w1_anomaly_review.py`（checker）
- `reports/w1_full_pipeline_anomaly_review_v1.json` + `reports/W1_FULL_PIPELINE_ANOMALY_REVIEW_V1.md`（报告）
- `reports/W1_EXPERT_PROJECT_REPORT.md`（§7 注册）

## 3. 核心结论

11/128 超阈值样本（max abs err ≥ 0.02）**全部归因为 `DRAW_RATE_TENSION`**：

- **11/11 的最差复现项都是平局(D)**；主客分裂复现良好，误差是平局误差的溢出。
- 根因：市场隐含 Dixon-Coles 中，μ 由 OU 固定、ρ 固定，**单一 δ 无法同时匹配市场平局率**；市场平局定价偏离 μ+ρ 所能产生的平局率时，残差落在 D。
- **`data_bug_found = false`**：orientation 结构性排除（覆盖行按精确 `date+home_id+away_id` 合并）；μ 均在正常区间；fit_sse 均不高。**非数据 bug、非引擎 bug。**
- 记录为**已知限制**，本阶段**不改引擎**。

逐场（节选，按误差降序）：denmark-france(err 0.058, drawgap −0.058)、australia-denmark(0.033)、england-belgium(0.032)、france-australia(0.028)、argentina-australia(0.027)…全部 worst=D。

## 4. checker 结果

- 本阶段新增 `check_w1_anomaly_review`：**PASS**；负向测试（注入 `engine_modified=true`）立即 FAIL，还原 PASS。
- 全量 `check_w1_*.py`：**32 PASS / 9 FAIL**。**9 个失败全部是既有/运行时脏数据问题，与本阶段无关**：
  - 既有基线失败（干净 HEAD 即失败）：click_to_predict、early_prediction_mode、environment_context、post_match_calibration、report_templates、round1_real_fixture_cards、watcher、weather_integration。
  - `post_match_result_update`：因 `data/results/round1_results.json` 运行时被改（`away_team: Türkiye` 不匹配）——**本阶段未触碰该文件**（本阶段只新增 review 脚本/checker/报告/§7 一行，未碰其任何输入）。
- 本阶段**零回归**。

## 5. 红线确认（实测）

- 未改 `scripts/w1_score_engine.py`、`DEFAULT_RHO=-0.057766`、`config/w1_decision_policy.json`、`config/w1_odds_movement_thresholds.json`。
- 诊断脚本**只读 import** `w1_score_engine`，无 `DEFAULT_RHO` 赋值；无 requests/urllib/web_fetch 等抓取；未 refetch。
- 未来修法 `W1_DRAW_CALIBRATION_RESEARCH` **仅登记，未在本阶段实现**（`implemented_in_this_stage=false`）。
- 无投注/资金/命中率表达。

## 6. WARN_ONLY

- 平局结构张力为方法固有限制，记录在案;在 `W1_DRAW_CALIBRATION_RESEARCH` 落地前不修。
- 既有 9 个 checker 失败属运行时脏数据/历史模板,超出本阶段范围（建议单独做一次运行时清理:`round1_results.json` 的 Türkiye 字段、watcher 时间等）。

## 7. 是否回滚

否。诊断完成、根因确认、红线未触碰、零回归。

## 8. BLOCKER / 本机收尾命令

代码/逻辑:none。环境:沙箱 `.git` 锁(EPERM) + SSH push 限制(同前)。本机执行：

```bash
cd <repo>
rm -f .git/HEAD.lock .git/index.lock; git worktree prune
git add docs/W1_FULL_PIPELINE_ANOMALY_REVIEW_V1.md scripts/review_w1_full_pipeline_anomaly.py scripts/check_w1_anomaly_review.py reports/W1_EXPERT_PROJECT_REPORT.md
git commit -m "W1_FULL_PIPELINE_ANOMALY_REVIEW_V1 (commit 1/2): spec + diagnostic + checker + registration"
git add reports/w1_full_pipeline_anomaly_review_v1.json reports/W1_FULL_PIPELINE_ANOMALY_REVIEW_V1.md reports/W1_FULL_PIPELINE_ANOMALY_REVIEW_V1_RESULT.md
git commit -m "W1_FULL_PIPELINE_ANOMALY_REVIEW_V1 (commit 2/2): anomaly report + RESULT"
git push origin main
```

## 9. 下一阶段建议

1. **(可选, 低风险) 运行时清理**：修 `round1_results.json` 的 Türkiye 字段 + watcher/模板等 8 个既有失败,让全量 checker 归零。
2. **`W1_DRAW_CALIBRATION_RESEARCH`**（动引擎,需先回测证明）：研究按场让 ρ 或加平局校准项,吸收平局残差;在 128(及后续扩展)子集上对比 log-score/ECE,达标再上线。
3. 扩 OU 覆盖 / 补 AH（仍本地文件,不抓取）/ Forward-Ledger 持续跑 / S2 仍 prototype。

边界不变：概率建模与赛前/赛后研究;不是投注平台,不输出资金建议,不承诺命中率,不把模型-市场分歧表述为投注机会。
