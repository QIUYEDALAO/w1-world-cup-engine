# W1_S0_SAFE_OUTPUT_AND_S1B_SEED_V1 结果报告

生成时间：2026-06-15 CST
origin：`git@github.com:QIUYEDALAO/w1-world-cup-engine.git`
阶段基线 HEAD：`aa725c3`
执行边界：S0 纯展示层 + S1B-Seed 全新隔离;不改 λ/ρ/score matrix/PLAY_GUARD/thresholds。

## 1. commit 列表

| commit | 内容 | 状态 |
|---|---|---|
| `51e7a4b` | (1/3) S0 输出层安全视图 | **已落地** |
| (2/3) | S1B-Seed ingestion + 1X2-only baseline | **已 staged，未提交**（见第 9 节 .git 锁） |
| (3/3) | 本 RESULT 报告 | 待提交 |

push：**未 push**（commit 2/3 因环境 .git 锁未能在沙箱内创建）。

## 2. 文件清单

**Commit 1（S0，已提交）**
- `scripts/build_w1_dashboard_data.py`：新增 `build_safe_view`（矩阵派生区间/尾部，附加字段）。
- `reports/dashboard/W1_VISUAL_DASHBOARD.html`：头条降权 + 区间行 + 场景标签修正。
- `reports/dashboard/assets/w1_dashboard_data.json`：重建（含 safe_view）。
- `docs/W1_OUTPUT_LAYER_SAFE_VIEW_V1.md`、`scripts/check_w1_output_safe_view.py`。

**Commit 2（S1B，已 staged）**
- `scripts/normalize_w1_international_dataset.py`、`scripts/w1_backtest_engine.py`
- `scripts/check_w1_international_dataset.py`、`check_w1_team_name_reconciliation.py`、`check_w1_host_no_qualifier_history.py`、`check_w1_team_sample_sparsity.py`、`check_w1_backtest_spine.py`
- `config/w1_international_dataset_schema.json`、`config/w1_team_aliases.json`
- `docs/W1_INTERNATIONAL_BACKTEST_DATASET_V1.md`、`docs/W1_BACKTEST_AND_DATA_SPINE_V1.md`
- `reports/W1_INTERNATIONAL_DATASET_QUALITY_V1.md`、`reports/w1_backtest_1x2_only_baseline_v1.(json|md)`
- `reports/W1_EXPERT_PROJECT_REPORT.md`（§7 注册新 checker）、`.gitignore`

**不入仓**（gitignored）：`data/raw/international/WorldCup2026.xlsx`、`data/processed/international/*.csv|*.json`。

## 3. checker 结果（实跑，全 PASS）

新增（6）：`output_safe_view`、`international_dataset`、`team_name_reconciliation`(BLOCKER)、`host_no_qualifier_history`(WARN)、`team_sample_sparsity`(报告)、`backtest_spine`。
既有核心（9）：score_matrix / recommendation_output_policy / market_probability_panel / post_match_result_sync / dashboard_backend_predict_integration / visual_dashboard / rho_calibration / production_lite / odds_movement_status_consistency。
守门（2）：recommendation_accuracy_audit、rho_real_ou_calibration（commit 1 后 PASS）。
**合计 17/17 PASS，无回归。**

## 4. 数据产出摘要

- 统一数据集 **1081** 行（预选 889 + 2022/2018/2014 各 64）。
- team_id 映射 **100%**（0 未映射）；别名表 207 队 / 425 别名。
- 1X2 赔率可用 1074；**OU/AH 全缺 → `pipeline_mode=1X2_ONLY`、`w1_full_pipeline_validated=false`**。
- xG（预选）339/889；统计 909；犯规 875。
- 2022 脏 `Finished` 标签定位 **5** 行（乌拉圭-韩国/瑞士-喀麦隆/摩洛哥-克罗地亚/阿根廷-沙特 标 Penalties；塞内加尔-荷兰 标 Extra time）。
- `HGP/HGP.1` → `home_penalties`/`away_penalties`。
- 东道主 **USA/Mexico/Canada** 标记 `host_auto_qualified_2026`，预选 0 场（WARN，gate 正式 S2）。
- 样本稀疏：37 支球队 total<5。
- **1X2-only 基准**：n=1074，方向准确率 0.635，mean RPS 0.2977（uniform 0.4817，beats），主胜 ECE 0.0241；强热门(≥0.70) 方向 0.873、接近盘(<0.50) 0.399；walk-forward test(215 场) RPS 0.312。

## 5. S0 安全视图（自洽核对）

- 头条"主比分"降权为"最高单格概率"；新增总进球区间 / 净胜区间 / 分布形态读数。
- 修正错标：原"防线崩盘（热门输）46%"=blowout，已拆为 **大胜（净胜≥3）46%** 与 **热门被翻盘（热门输）3.7%**（西班牙实测）。
- safe_view ready 24/24。

## 6. 未改动红线确认（实测）

- `scripts/w1_score_engine.py` 未改；`DEFAULT_RHO=-0.057766` 未变。
- `config/w1_odds_movement_thresholds.json`、`config/w1_decision_policy.json` 未改。
- **S0 模型指纹不变**：重建前后 24 场 score_matrix_summary（λ/ρ/μ/δ/model_hda/top_scores/market_fit_error）逐场比对，**diff=NONE**。
- 全程无投注/资金/命中率承诺表达（checker 强制）。

## 7. WARN_ONLY

- 缺 OU/AH → 仅 1X2-only，不能复现完整 W1 比分矩阵管线。
- 东道主缺预选历史（gate 正式 S2）。
- 样本稀疏（强度模型需时间衰减 + shrinkage）。
- 数据集 gitignored，本地生成；checker 在数据缺失时安全 SKIP。

## 8. 是否回滚

否。commit 1 已落地且 17 checker 全 PASS；commit 2/3 内容已在工作区/暂存区，无需回滚。

## 9. BLOCKER（环境，非代码）

沙箱内 `.git/HEAD.lock`（及 `index.lock`、遗留 `worktrees/w1_base/HEAD.lock`）无法删除（mount `Operation not permitted`），导致 commit 2/3 无法在此环境创建、无法 push。代码与验收**已全部完成**。

### 手动收尾命令（在可写环境执行）

```bash
cd <repo>
rm -f .git/HEAD.lock .git/index.lock .git/worktrees/w1_base/HEAD.lock && git worktree prune
# commit 2（S1B；文件已 staged，如丢失可重新 git add 第 2 节列出的文件）
git commit -m "W1_S0_SAFE_OUTPUT_AND_S1B_SEED_V1 (commit 2/3): S1B-Seed ingestion + 1X2-only baseline"
# commit 3（RESULT）
git add reports/W1_S0_SAFE_OUTPUT_AND_S1B_SEED_V1_RESULT.md
git commit -m "W1_S0_SAFE_OUTPUT_AND_S1B_SEED_V1 (commit 3/3): stage RESULT report"
git push origin main
# 收尾后复跑两个守门 checker 应仍 PASS
python3 scripts/check_w1_recommendation_accuracy_audit.py
python3 scripts/check_w1_rho_real_ou_calibration.py
```

## 10. 下一阶段建议

1. **S1B-Odds-Extension**：给这 1081 场补 OU/AH 收盘赔率 → 解锁完整 W1 管线与总进球/AH 校准。
2. **S1B-Forward-Ledger**：本届世界杯起逐场赛前快照落库（lineup/天气/相位 research_features 唯一干净来源）。
3. **S2 prototype**：用 results + 部分 xG 起步国家队攻防强度（时间衰减 + shrinkage；东道主用友谊赛/Elo 补），与 1X2 基准做 walk-forward 对照；正式验收等 S1B 数据增强。

边界不变：W1 是概率建模、赛前分析、风险读数与赛后复盘系统;不是投注平台,不输出资金建议,不承诺命中率,不把模型-市场分歧表述为投注机会。
