# W1 世界杯赛前预测系统专家项目报告

生成时间：2026-06-15  
项目路径：`/Users/liudehua/.openclaw/workspace/w1_world_cup_engine`  
当前 HEAD：`1394a3c`  
remote：none  
push：skipped_no_remote  
当前验收口径：11/11 checker PASS  

## 0. 合规与使用边界

W1 当前定位是世界杯赛前分析研究系统，输出用于赛前分析参考、模型概率读数、一致性核对和风控门槛判断。系统不承诺命中率，不根据单场结果宣称模型有效，也不构成投注、下注或资金层面的建议。

报告面向足球数据、盘口、概率模型和策略评审专家。本文不写营销话术，不把比分池或盘口概率解释成确定结论，不把风险路径称为推荐。

## 1. 系统定位

W1 是一套世界杯赛前预测与复盘系统，核心目标是把赛前市场信息、赔率快照、阵容/首发、裁判、天气、盘口异动、比分矩阵和赛后校准串成一条可审计链路。

当前核心模型是 `market_implied_poisson_dixon_coles`。其产物不是单一比分，而是完整比分联合分布，即 score matrix。以下输出都从同一比分矩阵派生：

- 1X2：主胜 / 平 / 客胜概率。
- OU：不同大小球线的 over / push / under 概率。
- AH：不同让球线的过 / 走 / 未过概率。
- BTTS：双方进球 Yes / No。
- Top scores：比分矩阵中的高概率比分。
- score_distribution：主比分、备选比分、风险路径、打开局和尾部质量。

普通 dashboard 展示层只保留主比分唯一、备选比分最多一个、盘口读数摘要和关键风险解释。专家视图保留完整矩阵、Top 8、全盘口线、market/model 对比和调试信息。

## 2. 核心模型与 rho 口径

核心实现文件：

- `scripts/w1_score_engine.py`
- `scripts/build_w1_dashboard_data.py`
- `reports/dashboard/assets/w1_dashboard_data.json`
- `reports/dashboard/W1_VISUAL_DASHBOARD.html`

核心模型口径：

- 模型名称：`market_implied_poisson_dixon_coles`
- score matrix：由市场隐含总进球、胜差和 Dixon-Coles 相关项派生。
- `DEFAULT_RHO=-0.057766`
- 该 rho 不再使用早期经验默认值 `-0.10`。

rho provenance：

- 配置文件：`config/w1_rho_provenance.json`
- 校准报告：`reports/W1_RHO_REAL_OU_CALIBRATION_REPORT.md`
- 校准 JSON：`reports/w1_rho_real_ou_calibration.json`
- 候选 provenance：`reports/w1_rho_provenance_candidate.json`
- 样本来源：football-data 五大联赛 E0 / SP1 / D1 / I1 / F1，6 个赛季。
- OU 样本数：`10731`
- mode：`ou`
- rho_hat：`-0.057766`
- production_ready：true

注意：rho 的上线只更新常数与 provenance，不改变 score matrix 核心结构、lambda 推导、盘口解析、lineup/tactical 权重或 PLAY_GUARD。

## 3. 已完成能力

### 3.1 Score Matrix Core

相关文件：

- `scripts/w1_score_engine.py`
- `scripts/w1_score_matrix_batch.py`
- `scripts/check_w1_score_matrix.py`
- `reports/W1_SCORE_MATRIX_BATCH_REPORT.md`

能力说明：

- 生成市场隐含 Poisson + Dixon-Coles score matrix。
- 输出 `score_matrix_summary`：`mu_total_goals`、`delta_goal_diff`、`lambda_home`、`lambda_away`、`dixon_coles_rho`、Top scores、1X2 概率、open_game_mass、collapse_mass、market_fit_error。
- `open_game_mass` 来自 `P(total_goals >= 4)`。
- `collapse_mass` 来自比分矩阵尾部质量，不是独立拍权重。

### 3.2 Manual Lineup Override

相关文件：

- `data/manual_lineups/1539001.json`
- `data/manual_lineups/66456942.json`
- `data/fixture_aliases.json`
- `scripts/check_w1_manual_lineup_override.py`

能力说明：

- 支持人工核验首发 override。
- 解决 Australia vs Turkey 的 `1539001 <-> 66456942` fixture alias。
- override 标注 `source_type=manual_verified`，不伪装成实时 API 成功。

### 3.3 Australia vs Turkey post-match result

相关文件：

- `data/results/round1_results.json`
- `scripts/check_w1_post_match_result_update.py`

能力说明：

- 写入 Australia 2-0 Turkey 赛果。
- 触发 `post_match_calibration` 的 RPS / log score 复盘字段。
- 不基于单场结果调 rho、score matrix、盘口阈值或 PLAY_GUARD。

### 3.4 Recommendation Accuracy Audit

相关文件：

- `scripts/audit_w1_recommendation_accuracy.py`
- `scripts/check_w1_recommendation_accuracy_audit.py`
- `reports/W1_RECOMMENDATION_ACCURACY_AUDIT.md`
- `reports/w1_recommendation_accuracy_audit.json`

能力说明：

- 统计已完赛样本的方向准确率、主比分准确率、主/备比分准确率、score_pool 覆盖、mean RPS 和 mean log loss。
- 当前样本量仍很小，不能据此调参。
- 精确比分命中率不是唯一指标，RPS/log score 才是更主要的概率校准指标。

### 3.5 Rho Calibration Pipeline

相关文件：

- `scripts/w1_rho_calibration.py`
- `scripts/check_w1_rho_calibration.py`
- `scripts/convert_footballdata_league_csv_to_rho.py`
- `scripts/check_w1_rho_real_ou_calibration.py`
- `data/historical/rho_calibration_real.csv`

能力说明：

- 支持 football-data 联赛 CSV 转 W1 rho 校准 CSV。
- 支持 mode=ou 校准。
- 输出报告和 reliability figure。
- rho 上线需要 provenance 支撑，不自动根据单场赛果改生产参数。

### 3.6 Recommendation Output Policy

相关文件：

- `docs/W1_RECOMMENDATION_OUTPUT_POLICY.md`
- `scripts/check_w1_recommendation_output_policy.py`

能力说明：

- 主比分唯一。
- 备选比分最多 1 个。
- 风险路径、尾部路径、打开局路径单独展示，不称为推荐。
- 完整 score_pool 只在专家/详情层展示。
- Top 8 是比分概率分布，不是推荐列表。

### 3.7 Dashboard Backend Predict Integration

相关文件：

- `scripts/w1_local_predict_server.py`
- `scripts/run_w1_dashboard.sh`
- `scripts/check_w1_dashboard_backend_predict_integration.py`
- `reports/dashboard/W1_VISUAL_DASHBOARD.html`

当前接口：

- `GET /health`
- `GET /dashboard-data`
- `GET /progress`
- `POST /predict`

能力说明：

- dashboard 支持 `backendConnected` 双状态。
- 后端未连接时使用内嵌静态快照。
- 后端连接后可触发 `/predict`。
- `/predict` 成功后刷新 dashboard data。
- `/predict` 失败时保留旧快照，不覆盖为空。

### 3.8 Match Stage Gate

相关文件：

- `scripts/check_w1_match_stage_gate.py`
- `reports/dashboard/W1_VISUAL_DASHBOARD.html`

能力说明：

- stageGate 根据 `kickoff_utc` 与当前时间动态判断阶段。
- 阶段包括早盘参考、赛前观察、正式判断准备、最终版、锁盘/赛前确认、赛中/已开赛。
- 不再写死固定时点。

### 3.9 Predict Runtime Alias Fix

相关文件：

- `data/fixture_aliases.json`
- `scripts/w1_local_predict_server.py`
- `scripts/check_w1_manual_lineup_override.py`

能力说明：

- `/predict` 以 fixture_id 为主键。
- manual lineup 查询同时尝试 request fixture_id、alias fixture_id 和 match card fixture_id。
- 解决点击一场比赛却命中另一场或命中不到 override 的问题。

### 3.10 Odds Movement Monitor V1

相关文件：

- `config/w1_odds_movement_thresholds.json`
- `scripts/check_w1_odds_movement_monitor.py`
- `scripts/check_w1_odds_movement_threshold_calibration.py`
- `reports/dashboard/assets/w1_dashboard_data.json`

能力说明：

- 盘口异动只读市场变化，不直接改 λ。
- 不改 score matrix，不改 rho。
- 必须先去水，再比较概率或 μ。
- 1X2 主指标使用 TV distance。
- OU 使用隐含 μ drift。
- 输出 recent / cumulative / phase-aware 的市场变化状态。

状态枚举（W1_P0_CONSISTENCY_AND_AUDIT_REFRESH_V1 起对齐）：

- `MARKET_STABLE`
- `MARKET_MOVING`
- `MARKET_ALERT`
- `MARKET_CONFLICT`（保留，monitor 暂未触发）
- `HARD_THIN`（= HARD_SKIP）
- `SOFT_THIN`（= WARN_ONLY）
- `THIN_MARKET_SKIP`（DEPRECATED，accepted-but-deprecated，映射到 `HARD_THIN`，待 odds snapshot 采集上线后移除）

`status` 只承载会改变 PLAY_GUARD 门控的区分；`status_reason_code`（如 `NO_1X2` / `NO_OU` / `FEW_BOOKS` / `STALE` / `WIDE_SPREAD`）只承载不改变门控的原因。`READY` 不属于 odds_movement.status，只属于 `market_signal.status`。

PLAY_GUARD 关系：

- `THIN_MARKET_SKIP` 任意校准状态都进入 PLAY_GUARD 的 skip / blocking 路径。
- `MARKET_MOVING` 永远 WARN_ONLY，不硬拦。
- `MARKET_ALERT` / `MARKET_CONFLICT` 只有 Tier A 且 `calibrated=full` 时才可硬 gating。
- Tier B/C 或 `calibrated!=full` 时只能 WARN_ONLY。

### 3.11 Odds Movement Threshold Calibration

相关文件：

- `config/w1_odds_movement_thresholds.json`
- `W1_ODDS_MOVEMENT_THRESHOLD_CALIBRATION_SPEC.md`
- `scripts/check_w1_odds_movement_threshold_calibration.py`

当前默认配置：

- `calibrated=none`
- `tier=C`
- `source_report=null`

校准设计：

- 阈值应由 MAJOR_NEWS vs NO_MAJOR_NEWS 两组分布估计。
- minor/medium 建议使用 NO_NEWS 90 分位。
- medium/major 建议使用 `max(NO_NEWS 97 分位, Youden opt)`。
- AUC < 0.65 的指标降级 WARN_ONLY，不进入 gating。
- Tier A/B/C 表示阈值可信度和上线等级。
- 样本不足时保持默认阈值。
- 禁止按单场结果调阈值。
- 标注新闻，不标注赛果。

### 3.12 Market Probability Panel V1

相关文件：

- `scripts/check_w1_market_probability_panel.py`
- `reports/dashboard/W1_VISUAL_DASHBOARD.html`
- `reports/dashboard/assets/w1_dashboard_data.json`

能力说明：

- 从同一 score matrix 派生 1X2 / OU / AH / BTTS。
- 普通视图展示核心盘口读数。
- 专家视图保留完整 OU/AH lines、score matrix、Top 8 和 market comparison。
- 主盘多为市场输入的再表达，主要用于一致性核对。
- 衍生盘如 BTTS、clean sheet、goal bands 是同一比分矩阵的补充切面。

### 3.13 Market Panel Readability V1

相关文件：

- `reports/dashboard/W1_VISUAL_DASHBOARD.html`
- `scripts/check_w1_market_probability_panel.py`

能力说明：

- 新增“盘口读数摘要”。
- 每个卡片增加“读数：...”解释层。
- 1X2 翻译为主队小优、双方接近、客队小优、优势较明显等。
- OU 2.5 翻译为偏大比分、偏小比分、接近均衡。
- AH 翻译为主队不败读数、让球压力等。
- BTTS 翻译为双方进球五五开、偏双方都有进球、偏至少一方零进球。
- market/model 差值翻译为一致、轻微偏离、偏离较大需复核盘口来源。

### 3.14 Secondary Score Display Fix

相关文件：

- `scripts/build_w1_dashboard_data.py`
- `reports/dashboard/W1_VISUAL_DASHBOARD.html`
- `scripts/check_w1_recommendation_output_policy.py`
- `scripts/check_w1_visual_dashboard.py`

能力说明：

- 修复顶部“备选比分”为空的问题。
- 若 `fallback_score` 为空、重复或属于风险路径，则从 `score_matrix.top_scores` 选择一个合格备选。
- 备选比分不能等于主比分。
- 备选比分最多一个。
- 备选比分必须来自 score matrix / recommendation_view。
- 若没有合格备选，输出 `secondary_score_reason_cn`，UI 不再无解释显示横杠。

## 4. Dashboard 当前能力

核心文件：

- `reports/dashboard/W1_VISUAL_DASHBOARD.html`
- `reports/dashboard/assets/w1_dashboard_data.json`
- `scripts/build_w1_dashboard_data.py`
- `scripts/w1_local_predict_server.py`

前端能力：

- 支持静态 HTML 双击或本地服务打开。
- 支持 `backendConnected` 双状态。
- 后端未连接时使用内嵌静态快照。
- 后端已连接时可点击开始预测。
- 失败时保留旧快照。
- stageGate 按 kickoff 动态判断当前阶段。

盘口概率面板：

- 1X2：主胜 / 平 / 客胜。
- OU：默认 O/U 2.5，专家视图展示更多线。
- AH：显示当前主盘口及过 / 走 / 未过。
- BTTS：Yes / No。
- 普通视图新增盘口读数摘要。
- 专家视图保留 score matrix、Top 8、完整盘口线和 market/model 对比。

## 5. 数据链路

点击 dashboard “开始预测”后的目标链路：

1. 初始化比赛。
2. 使用 fixture_id 精确定位 match record。
3. 实时请求赔率 API。
4. 实时请求首发 API。
5. 实时请求裁判 / fixture detail。
6. 实时请求伤停 / 停赛。
7. 请求 Open-Meteo 天气。
8. 写入 runtime/match card。
9. 重算 data_quality、lineup_effect、tactical_effect、score_distribution、market_probability_panel、odds_movement 和 play_guard。
10. 重建 dashboard data 并展示进度和结果。

重要边界：

- API key 只允许后端/env 使用，不能进入前端。
- fallback/cache/verified_fallback 必须标注 source，不得伪装成 live API success。
- 失败时不能覆盖为空数据。

## 6. 数据源与关键 schema

关键 schema/config：

- `config/w1_match_card_schema.json`
- `config/w1_decision_policy.json`
- `config/w1_ledger_schema.json`
- `config/w1_rho_provenance.json`
- `config/w1_odds_movement_thresholds.json`

关键数据：

- `data/processed/match_cards/group_stage_round1/*.json`
- `data/processed/ledger/w1_ledger_group_stage_round1.csv`
- `data/results/round1_results.json`
- `data/manual_lineups/*.json`
- `data/fixture_aliases.json`
- `data/static/world_cup_2026_venues.json`
- `reports/dashboard/assets/w1_dashboard_data.json`

主要字段域：

- `score_distribution`
- `score_matrix_summary`
- `recommendation_view`
- `market_probability_panel`
- `odds_movement`
- `data_quality`
- `environment_context`
- `lineup_effect`
- `tactical_effect`
- `referee_effect`
- `live_refresh`
- `post_match_calibration`

## 7. 当前验收 checker

当前阶段要求的 11 个 checker：

```bash
python3 scripts/check_w1_match_stage_gate.py
python3 scripts/check_w1_dashboard_backend_predict_integration.py
python3 scripts/check_w1_recommendation_output_policy.py
python3 scripts/check_w1_rho_calibration.py
python3 scripts/check_w1_score_matrix.py
python3 scripts/check_w1_dashboard_data_binding.py
python3 scripts/check_w1_visual_dashboard.py
python3 scripts/check_w1_production_lite.py
python3 scripts/check_w1_odds_movement_monitor.py
python3 scripts/check_w1_odds_movement_threshold_calibration.py
python3 scripts/check_w1_market_probability_panel.py
```

当前记录：11/11 PASS。

补充 checker：

- `scripts/check_w1_manual_lineup_override.py`
- `scripts/check_w1_post_match_result_update.py`
- `scripts/check_w1_recommendation_accuracy_audit.py`
- `scripts/check_w1_rho_real_ou_calibration.py`
- `scripts/check_w1_weather_integration.py`
- `scripts/check_w1_lineup_api_binding.py`
- `scripts/check_w1_odds_movement_status_consistency.py`（W1_P0_CONSISTENCY_AND_AUDIT_REFRESH_V1：odds_movement.status 枚举/前缀/门控一致性，THIN_MARKET_SKIP 仅 WARN）
- `scripts/check_w1_output_safe_view.py`（W1_S0_SAFE_OUTPUT_AND_S1B_SEED_V1：safe_view 区间/尾部字段、主≤1/备≤1、热门输与净胜≥3 分离、专家区默认折叠、无促性表达）
- `scripts/check_w1_international_dataset.py`（S1B：国际赛数据 schema/90min/finished 推导/覆盖/pipeline_mode；数据缺失安全 SKIP）
- `scripts/check_w1_team_name_reconciliation.py`（S1B BLOCKER：队名未映射/alias 一对多 FAIL；校验别名表 + W1 fixtures）
- `scripts/check_w1_host_no_qualifier_history.py`（S1B WARN：USA/Mexico/Canada 东道主缺预选历史，gate 正式 S2）
- `scripts/check_w1_team_sample_sparsity.py`（S1B 报告：每队样本量/最近比赛日期/低样本，生成数据质量报告）
- `scripts/check_w1_backtest_spine.py`（S1B：1X2_ONLY 标签、leakage guard、walk-forward 不重叠，不冒称完整管线）
- `scripts/check_w1_forward_ledger.py`（W1_FORWARD_LEDGER_AND_S2_PROTOTYPE_V1：赛前快照 schema/as_of/append-only，强制无赛后字段 leakage guard）
- `scripts/check_w1_team_strength_prototype.py`（S2 prototype：prototype 标签、时序无未来泄漏、shrinkage、东道主 fallback、不接线上 λ）
- `scripts/check_w1_ou_coverage.py`（OU/AH 覆盖率探测：coverage-only、external_fetch_performed=false、无外部抓取）

## 8. 当前 WARN_ONLY / 限制

### 8.1 版本与工作区

- remote=none。
- push=skipped_no_remote。
- runtime/cards/state/log/raw snapshots dirty，目前不应混入提交。
- 当前 dirty 文件包含前序 cards、state、dashboard data、logs、raw snapshots 等。

### 8.2 odds movement thresholds

- `config/w1_odds_movement_thresholds.json` 当前仍是 `calibrated=none`、`tier=C`。
- V1 默认阈值可用于 WARN_ONLY 和基础风控提示，但不能假装已经完成 Tier A 校准。
- 多档盘口历史需要 going-forward 自己积累。
- stale snapshots 触发 `THIN_MARKET_SKIP` 是正确行为，不应简单放宽。

### 8.3 post-match audit

- 当前 post-match audit 样本很小。
- n 太小，不能据此调参。
- 单场复盘只能进入 calibration 样本，不应直接改 rho、score matrix、lineup/tactical 权重或 odds movement 阈值。

### 8.4 Football-API lineup binding

- Football-API lineup binding 仍需进一步确认 squad vs starting XI。
- squad 只能说明名单可用，不能等同 confirmed starting XI。
- starting XI 才能解除首发阻断。

### 8.5 扫描噪声

- secret scan 可能命中变量名 `token` 或 CSS `space-between` 子串。
- 这类命中不是实际 secret，需要人工区分。

## 9. 专家重点评审问题

1. score matrix 的 lambda 反解是否应该加入 lineup/tactical 的小幅修正，还是保持市场先验为主？
2. lineup_effect / tactical_effect 目前偏解释层，如何避免和市场重复计价？
3. 盘口异动的 TV distance 与 μ drift 阈值如何做正负样本标注？
4. `THIN_MARKET_SKIP` 的 strictness 是否适合世界杯小组赛早盘环境？
5. `MARKET_ALERT` / `MARKET_CONFLICT` 在 Tier C 下只 WARN_ONLY 是否足够保守？
6. score_pool 的 Top scores、主比分、备选比分、风险路径在专家报告中如何避免被误读为确定结论？
7. RPS/log score 应如何与方向准确率、主比分准确率并行汇报？
8. 足球赛果尾部事件是否需要 overdispersion 或更复杂的 bivariate 结构？

## 10. 下一步建议

按优先级建议：

1. 继续收集 dashboard UI/可读性问题，攒成一个阶段包再修，不要小修即 commit。
2. Football-API lineup binding：区分 squad 与 starting XI。starting XI 才能解除首发阻断，squad 不得误判为首发。
3. Odds snapshot collection：开始逐场收集多档共识盘口快照，包括不同时间点、book_count、staleness、spread、盘口主线变化。
4. Threshold calibration：攒够 positive/negative 标注后再做 Tier A/B calibration。
5. Post-match audit：继续累计 RPS/log-loss，不按单场调参。
6. Dashboard 专家报告/导出模板：为每场生成可交付专家审阅的赛前卡与赛后复盘卡。

## 11. 阶段末状态

STATUS：report generated  
HEAD：`1394a3c`  
checker：当前记录 11/11 PASS，本报告生成阶段未重新跑完整 checker  
DEFAULT_RHO：`-0.057766`  
production_ready：rho provenance 已校准；odds movement thresholds 仍 Tier C / uncalibrated  
WARN_ONLY：

- remote none。
- runtime dirty files 存在。
- odds movement thresholds 未完成生产级校准。
- post-match audit n 太小，不能据此调参。
- Football-API lineup binding 仍需确认 squad vs starting XI。

BLOCKER：none  
next_stage：建议进入 `W1_LINEUP_API_BINDING_FIX_V1` 或 `W1_ODDS_SNAPSHOT_COLLECTION_V1`。
