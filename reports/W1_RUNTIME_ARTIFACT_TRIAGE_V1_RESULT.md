# W1_RUNTIME_ARTIFACT_TRIAGE_V1 结果报告

生成时间：2026-06-16 CST
origin：`git@github.com:QIUYEDALAO/w1-world-cup-engine.git`
阶段基线 HEAD：`c2f2829`
范围：修正版"治本"——只移出 `w1_dashboard_data.json` + `state/`;cards/HTML/results 保留跟踪。

## 1. 选择"治本"的原因

committed 的运行产物每次 predict/watcher/build 都会变,反复把仓库跑脏、反复触发 checker(前几阶段一直在清)。把"运行会变"的产物移出跟踪 + 按需重建,才能让仓库长期保持 clean,不再每阶段来一轮清理。

## 2. 从 git 跟踪中移出的 runtime artifact（已 staged）

- `reports/dashboard/assets/w1_dashboard_data.json` — `git rm --cached`(本地保留)。
- `state/`(全部:`w1_predict_progress.json`、`w1_refresh_state.json`、`w1_live_refresh_state.json`、`w1_weather_cache.json`)— `git rm -r --cached`(本地保留)。

**保留跟踪(STOP 守住,未误删源)**:`reports/dashboard/W1_VISUAL_DASHBOARD.html`(手写模板+JS)、`data/results/round1_results.json`(赛果事实)、`data/processed/match_cards/group_stage_round1/*.json`(源卡,实测**无任何生成脚本**,grep 写入=0)。

## 3. 新增 .gitignore 规则

```
reports/dashboard/assets/w1_dashboard_data.json
state/
```
(`data/local_odds/`、`data/processed/international/`、`data/raw/`、`data/forward_ledger/` 早已 gitignored;未新增 cards/HTML/results。)

## 4. checker skip-safe 改造

读取这两个运行产物的 checker(`visual_dashboard`、`dashboard_data_binding`、`watcher`、`report_templates`)在上一阶段 `W1_RUNTIME_CHECKER_CLEANUP_V1` **已具备 skip-safe**(实测含 `if not DATA_JSON.is_file()` / `if not STATE.is_file()` 守卫);本阶段复核确认,无需重复改造。

新增 `scripts/check_w1_runtime_artifact_policy.py`(已注册 §7,PASS):强制运行产物未跟踪、源/模板/事实仍跟踪、本地/生成数据未入仓、QC 证据在仓——防止再被误跟踪或误删源。

## 5. 两份 odds QC 报告入仓

实测它们在 stash 的**未跟踪子树** `stash@{0}^3`(非 tracked 部分,`git checkout stash@{0} -- ` 取不到),已用 `git show stash@{0}^3:<file>` 恢复到工作区。核验为**聚合证据**(列结构/覆盖率 PASS 表),**不含逐场原始赔率 dump**,可安全入仓。待 `git add` + commit。

## 6. 模拟运行后 git clean 证明（含一个诚实结论）

- ✅ **目标达成**:`git rm --cached` 后运行一次 `build`,`w1_dashboard_data.json` 与 `state/*` 出现在 `git status --ignored`(被 ignore),**不再以 tracked-dirty 出现**——这两个产物的"跑脏"已根治。
- ⚠️ **未完全 clean(有意保留,非本阶段)**:同一次 build 仍改脏**被跟踪的 HTML**(内嵌 `generated_at_utc` 时间戳)并把 `live_refresh` 写回**源卡**。因为按修正范围 HTML/卡保留跟踪,所以"build 后 git 全 clean"**要等两处后续重构**(见第 9 节)。本阶段只保证两个目标产物干净。

## 7. checker PASS / SKIP 汇总

- 全量 `check_w1_*.py`(沙箱):**41 PASS / 1 FAIL**。
- 唯一 FAIL=`watcher`:仅因 `w1_watcher.sh` 硬编码 `cd /Users/liudehua/...`(真机路径,沙箱不存在)导致 dry-run 失败;**在真机上 PASS**(与你 41/0/2 一致)。非本阶段回归。
- 新增 `check_w1_runtime_artifact_policy` PASS;`check_w1_odds_extension`/`full_pipeline_backtest`/`anomaly_review` 等均 PASS。

## 8. stash 处理 / 红线 / 回滚

- stash 处理:仅从 `stash@{0}^3` 取回两份 QC 报告;stash 其余(脏 cards/results/html/data/predict_progress)**未 pop**,保留为备份(那些是运行态,源以 HEAD 为准)。
- 红线:未改 `w1_score_engine`/`DEFAULT_RHO`/`decision_policy`/`thresholds`;未改 FULL pipeline / anomaly 结论;未引入 draw calibration / per-match rho;**未删除本地 runtime 文件,只 git rm --cached**;未弱化 checker 安全断言;未造假;未抓取/refetch/接 API;无投注/资金/命中率表达。
- 回滚:否。

## 9. BLOCKER / 本机收尾命令

沙箱 `.git` 锁(EPERM)+ 无 unlink + SSH push 限制,commit/push 在真机完成。**注意:QC 报告在 stash 的未跟踪子树,必须用 `^3` 取,普通 `git checkout stash@{0} -- ` 取不到。**

```bash
cd <repo>
rm -f .git/HEAD.lock .git/index.lock; git worktree prune
# 丢弃 smoke 误写入卡的 live_refresh(如有)
git checkout -- data/processed/match_cards/group_stage_round1/fixture_1489378_iran_vs_new-zealand.json 2>/dev/null || true
# 取回 QC 证据(从 stash 未跟踪子树)
git show "stash@{0}^3:reports/W1_LOCAL_ODDS_2026_QUALITY_CHECK.md" > reports/W1_LOCAL_ODDS_2026_QUALITY_CHECK.md
git show "stash@{0}^3:reports/W1_LOCAL_ODDS_HISTORICAL_QUALITY_CHECK.md" > reports/W1_LOCAL_ODDS_HISTORICAL_QUALITY_CHECK.md
# untrack 两个运行产物(本地保留)
git rm --cached reports/dashboard/assets/w1_dashboard_data.json
git rm -r --cached state/
# commit 1: 政策 + gitignore + untrack + 政策 checker + §7
git add .gitignore docs/W1_RUNTIME_ARTIFACT_POLICY_V1.md scripts/check_w1_runtime_artifact_policy.py reports/W1_EXPERT_PROJECT_REPORT.md
git commit -m "W1_RUNTIME_ARTIFACT_TRIAGE_V1 (commit 1/3): untrack dashboard_data.json + state/; runtime artifact policy + checker"
# commit 2: QC 证据
git add reports/W1_LOCAL_ODDS_2026_QUALITY_CHECK.md reports/W1_LOCAL_ODDS_HISTORICAL_QUALITY_CHECK.md
git commit -m "W1_RUNTIME_ARTIFACT_TRIAGE_V1 (commit 2/3): local odds QC evidence reports"
# commit 3: RESULT
git add reports/W1_RUNTIME_ARTIFACT_TRIAGE_V1_RESULT.md
git commit -m "W1_RUNTIME_ARTIFACT_TRIAGE_V1 (commit 3/3): RESULT"
git push origin main
# 复跑政策 checker 应 PASS
python3 scripts/check_w1_runtime_artifact_policy.py
```

## 10. 下一阶段建议

1. **`W1_DASHBOARD_TEMPLATE_DATA_SPLIT`**:tracked HTML 模板运行时加载 gitignored `assets/*.json`,模板不再内嵌数据/时间戳 → build 不再改脏 HTML。
2. **`W1_PREDICT_OVERLAY_SPLIT`**:predict/build 把 `live_refresh` 写到单独 gitignored overlay,不再写回源卡 → predict 不再改脏卡。
   完成 1+2 后,"任意 predict/build 后 git 仍 clean" 才完全达成。
3. 其余仍按既定:扩 OU 覆盖 / 补 AH(本地文件)、Forward-Ledger 持续跑、S2 prototype、`W1_DRAW_CALIBRATION_RESEARCH`(动引擎,需先回测)。

边界不变:概率建模与赛前/赛后研究;不是投注平台,不输出资金建议,不承诺命中率,不把模型-市场分歧表述为投注机会。
