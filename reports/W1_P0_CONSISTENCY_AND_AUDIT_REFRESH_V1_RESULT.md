# W1_P0_CONSISTENCY_AND_AUDIT_REFRESH_V1 结果报告

生成时间：2026-06-15 CST
阶段基线 HEAD（开工时）：`7faa947`
当前 HEAD：本阶段提交（最终 hash 以 `git log -1 --oneline` 为准，详见第 10 节）
执行边界：只做 P0 一致性 + 审计刷新；不改模型行为。

---

## 1. 修改了哪些文件，各解决什么问题

| 文件 | 改动 | 解决的问题 |
|---|---|---|
| `config/w1_match_card_schema.json` | `odds_movement.status` 枚举新增 `HARD_THIN` / `SOFT_THIN`；`THIN_MARKET_SKIP` 标注 deprecated（别名→HARD_THIN）；加描述说明 `READY` 不属于此字段 | schema 与代码实际输出对齐；保留旧值为 accepted-but-deprecated |
| `scripts/build_w1_dashboard_data.py` | 抽出单一事实源：`ODDS_MOVEMENT_STATUS_PRIORITY`、`ODDS_MOVEMENT_DEPRECATED_STATUS_ALIASES`、`ODDS_MOVEMENT_REASON_BY_STATUS`、`ODDS_MOVEMENT_GATE_MAP` + `normalize_odds_movement_status()` / `resolve_odds_movement_gate()`；把原 if/elif 门控替换为查表；输入侧 `THIN_MARKET_SKIP` 归一到 `HARD_THIN` | status→gate 显式化、可被 checker 复用；**行为不变** |
| `scripts/check_w1_odds_movement_status_consistency.py`（新增） | 枚举成员校验、reason 前缀/允许集校验、status↔play_guard_input/gate_effect 一致性、优先级显式断言、`THIN_MARKET_SKIP` 仅 WARN | 防止 status 口径再次漂移 |
| `data/processed/match_cards/group_stage_round1/fixture_1538999_south-korea_vs_czech-republic.json` | 该卡片遗留 `odds_movement.status` 由 `READY` → `SOFT_THIN`，加 `status_note` | 清除错放的 READY（READY 只属于 `market_signal.status`，该卡 market_signal.status 已是 READY，未动） |
| `reports/dashboard/assets/w1_dashboard_data.json`、`reports/dashboard/W1_VISUAL_DASHBOARD.html` | 重建 | 让 8 场赛果进入 `post_match_calibration`；应用枚举/门控重构后的派生产物 |
| `reports/W1_RECOMMENDATION_ACCURACY_AUDIT.md`、`reports/w1_recommendation_accuracy_audit.json` | 重跑 n=4 → n=8 | 审计纳入德国 7-1、荷兰 2-2、科特迪瓦 1-0、瑞典 5-1 |
| `reports/W1_EXPERT_PROJECT_REPORT.md` | §3.10 枚举说明更新为 HARD/SOFT 细分 + deprecated；§7 注册新 checker | 文档与代码对齐 |
| `docs/W1_P0_CONSISTENCY_AND_AUDIT_REFRESH_V1.md` | 阶段说明（上一轮已生成） | 本阶段规格 |

> 行为不变证据：重构前/后对 24 场 `odds_movement` 的 `status|reason|recommended_gate|allow_formal|reference_action|gate_effect` 指纹逐场比对，**差异 = NONE**。

---

## 2. checker 结果（实跑）

**本阶段要求的 8 个 + 新增一致性 checker：9/9 PASS**

```
[PASS] check_w1_score_matrix
[PASS] check_w1_recommendation_output_policy
[PASS] check_w1_market_probability_panel
[PASS] check_w1_post_match_result_sync
[PASS] check_w1_dashboard_backend_predict_integration
[PASS] check_w1_visual_dashboard
[PASS] check_w1_rho_calibration            (rho=-0.057766, provenance=calibrated)
[PASS] check_w1_production_lite
[PASS] check_w1_odds_movement_status_consistency  (dashboard_blocks=24, card_blocks=1, warnings=0)
```

负向测试：向某卡注入 `odds_movement.status="READY"`，新 checker 立即 FAIL（命中 READY 规则）；还原后 PASS——证明 checker 真正生效。

**两个 git-diff 守门 checker：提交后已 PASS**

```
[PASS] check_w1_recommendation_accuracy_audit
[PASS] check_w1_rho_real_ou_calibration
```

这两个 checker 用 `git diff --name-only` 检测受保护文件是否有“未提交改动”。本阶段提交后 `scripts/build_w1_dashboard_data.py` 的工作区 diff 已清空，二者均转为 PASS。它们未检测到 `w1_score_engine.py` / `w1_odds_movement_thresholds.json` / `w1_decision_policy.json` 的任何改动。

**与本阶段无关的既有失败（在干净 HEAD `7faa947` 同样 FAIL，非本次引入）**

`check_w1_click_to_predict`、`check_w1_early_prediction_mode`、`check_w1_environment_context`、`check_w1_post_match_calibration`、`check_w1_report_templates`、`check_w1_round1_real_fixture_cards`、`check_w1_watcher`、`check_w1_weather_integration`。

已用 HEAD 隔离 worktree 验证：上述 8 个在干净基线即 FAIL；它们由运行时脏数据/历史模板问题导致（例如 `report_templates` 要求 `W1_LIVE_DASHBOARD.md` 含 state 的 `next_run_cst`，而该 .md 未含；`round1_real_fixture_cards` 要求 1538999 为 W1_WAIT，但该卡今日实盘已被确认首发改为 W1_PLAY）。均不属本阶段范围，本阶段也未触碰其输入逻辑。

---

## 3. 审计 n=8 核心指标变化

| 指标 | n=4（旧） | n=8（新） |
|---|---:|---:|
| total_completed_matches | 4 | 8 |
| direction_accuracy | 50.0% | 50.0% |
| primary_score_accuracy | 0.0% | 0.0% |
| secondary_score_accuracy | 25.0% | 12.5% |
| primary_or_secondary_accuracy | 25.0% | 12.5% |
| score_pool_coverage | 50.0% | 50.0% |
| mean_actual_score_probability | 0.0693 | 0.0575 |
| mean_rps_1x2 | 0.5012 | 0.4131 |
| mean_exact_score_log_loss | 3.0738 | 3.4229 |

新增 4 场：德国 7-1 库拉索（主胜，方向命中）、荷兰 2-2 日本（平，方向未中）、科特迪瓦 1-0 厄瓜多尔（主胜，方向未中）、瑞典 5-1 突尼斯（主胜，方向命中）。

读数说明（仅陈述，不作调参依据）：

- `mean_rps_1x2` 下降，主因德国/瑞典是高置信热门且方向命中，1X2 概率损失低。
- `mean_exact_score_log_loss` 上升，主因德国 7-1、瑞典 5-1 是**打开局/尾部样本**，精确比分概率极低；这是**尾部偏重样本的预期表现，非调参触发**。
- `secondary_score_accuracy` 由 25% 降到 12.5% 只是分母翻倍，命中数仍为 1。
- **n=8 仍然太小，不允许据此调 rho / score matrix / 推荐政策 / 盘口阈值。** 报告文本已注明。

---

## 4. DEFAULT_RHO 是否未变

**未变。** `scripts/w1_score_engine.py` 不在本次改动文件列表内；`DEFAULT_RHO = -0.057766` 原样；`check_w1_rho_calibration` 实跑 PASS 且回显 `rho=-0.057766, provenance=calibrated`。

## 5. score matrix core 是否未变

**未变。** `scripts/w1_score_engine.py`（λ 反解、devig、OU→μ、Dixon-Coles 矩阵、评估）未被修改。`build` 侧仅改 odds_movement 的 status→gate 表达，未触碰比分矩阵派生路径；`check_w1_score_matrix` PASS。

## 6. odds thresholds 是否未变

**未变。** `config/w1_odds_movement_thresholds.json` 未被修改（仍 `calibrated=none`、`tier=C`、各阈值原值）。本阶段只统一 status 枚举与门控映射表达，不动任何阈值。

## 7. PLAY_GUARD 是否未变

**核心逻辑未变。** `config/w1_decision_policy.json`（W1_PLAY_GUARD_V1 规则）未被修改。`build` 内仅把 odds_movement 的 status→gate 由 if/elif 改为查表，输出逐场指纹与改造前完全一致（diff=NONE），属“显式化”而非“改逻辑”。

---

## 8. WARN_ONLY

- 本阶段 P0 改动已提交；未 push。
- 两个 git-diff 守门 checker 提交后已转为 PASS。
- 8 个既有 checker 失败（干净 HEAD 同样失败），属运行时脏数据/历史模板问题，**超出本阶段范围**。
- 预先存在的运行时脏文件 `fixture_1539001_*.json`、`state/w1_predict_progress.json` 仍留在工作区，**未纳入本阶段提交**。
- 审计 n=8 仍属小样本，不作调参依据。

---

## 9. BLOCKER

- **代码/逻辑层面：none。** 本阶段四项目标（枚举统一、READY 修复、一致性 checker、审计刷新）均已在工作区完成并通过 checker。
- **环境层面：none。** `.git/index.lock` 已解除，提交已完成。

## 10. commit hash

本阶段已提交为：

`W1_P0_CONSISTENCY_AND_AUDIT_REFRESH_V1: unify odds_movement status enum`

最终 hash 以 `git log -1 --oneline` 为准；本报告随提交一起写入，避免记录自指 hash 造成不一致。
