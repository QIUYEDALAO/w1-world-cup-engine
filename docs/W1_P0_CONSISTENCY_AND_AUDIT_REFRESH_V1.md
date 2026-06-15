# W1_P0_CONSISTENCY_AND_AUDIT_REFRESH_V1 阶段说明与验收 checklist

生成时间：2026-06-15 CST
项目路径：`/Users/liudehua/.openclaw/workspace/w1_world_cup_engine`
基线 HEAD：`7faa947`（branch=main，remote=none）
来源：`reports/W1_EXPERT_REVIEW_REPORT_V3.md` 第 1/3 节两个 P0。
定位：一致性清扫 + 评估刷新的小阶段。**只对齐口径、修数据、加校验、刷新审计；不改任何模型行为。**

---

## 0. 目标与原则

本阶段只做两件事：

- **工作流 A（口径一致性）**：统一 `odds_movement.status` 枚举，清掉错放的 `READY`，新增防漂移 checker。
- **工作流 B（评估刷新）**：准确率审计从 n=4 重跑到 n=8，只更新 audit/report。

贯穿原则（来自 V3，已与评审确认）：

> **`status` 承载会改变 PLAY_GUARD 门控的区分；`status_reason_code` 只承载不改变门控的细节。**

因此 `HARD_THIN`（HARD_SKIP）与 `SOFT_THIN`（WARN_ONLY）门控效果不同，必须留在 `status` 层，不下沉为 reason_code。

---

## 1. 修改文件范围

### 工作流 A：odds_movement.status 口径统一

| 文件 | 改动 | 说明 |
|---|---|---|
| `config/w1_match_card_schema.json` | `odds_movement.status` 枚举改为 `["MARKET_STABLE","MARKET_MOVING","MARKET_ALERT","MARKET_CONFLICT","HARD_THIN","SOFT_THIN","THIN_MARKET_SKIP"]`；`THIN_MARKET_SKIP` 加 `deprecated` 描述与移除时间点 | 新增 HARD/SOFT 为正式值；旧值保留为 accepted-but-deprecated |
| `scripts/build_w1_dashboard_data.py` | 把 `odds_movement_monitor` 内 791–820 行的 `status → (recommended_gate, allow_formal, reference_action, gate_effect)` 大 if/elif **重构为单一映射表**（见 §3）；级联判定顺序显式化为常量；若输入侧出现 `THIN_MARKET_SKIP` 一律归一到 `HARD_THIN` | 行为不变，只是把隐式逻辑抽成表，供 checker 复用同一张表 |
| `data/processed/match_cards/group_stage_round1/fixture_1538999_south-korea_vs_czech-republic.json` | `odds_movement.status="READY"` → 修正：`READY` 移至 `market_signal.status`（或 `odds_status`），`odds_movement.status` 置为合法枚举值（建议由 monitor 重新生成；若卡片层 odds_movement 仅为历史冗余，置为与该场一致的 `SOFT_THIN`） | 唯一一张被污染的卡片 |
| `reports/W1_EXPERT_PROJECT_REPORT.md` | §3.10 的 status 枚举说明从 `THIN_MARKET_SKIP` 更新为 HARD/SOFT 细分 + deprecated 注记；§7 checker 清单加入新 checker | 文档与代码对齐 |

> 注：match card 的 `odds_movement` 不由 `build_w1_dashboard_data.py` 写入（该脚本读卡片、把权威 odds_movement 重算进 dashboard data）。所以 `READY` 是静态数据污染，没有"活的写入口"在持续产生它；修这一张卡片 + 新 checker 兜底即可，无需追改生成器。

### 工作流 A：新增 checker

| 文件 | 说明 |
|---|---|
| `scripts/check_w1_odds_movement_status_consistency.py`（新建） | 见 §2。与既有 `check_w1_dashboard_data_binding.py`（已校验 schema_version / recommended_gate / 必填键）互补，专注 status 枚举与 status↔gate 一致性 |

### 工作流 A：重新生成（口径变更后的派生产物）

- `reports/dashboard/assets/w1_dashboard_data.json`：重跑 `build_w1_dashboard_data.py` 重建。
- `reports/dashboard/W1_VISUAL_DASHBOARD.html`：内嵌快照随之刷新。

### 工作流 B：审计刷新

| 文件 | 改动 |
|---|---|
| `reports/dashboard/assets/w1_dashboard_data.json` | 先重建，使德国 7-1、荷兰 2-2、科特迪瓦 1-0、瑞典 5-1 的 `actual_score` 经 results overlay 进入 `post_match_calibration`（RPS / log score） |
| `scripts/audit_w1_recommendation_accuracy.py` | 直接重跑，无需改代码（除非发现仍硬取 4 场） |
| `reports/W1_RECOMMENDATION_ACCURACY_AUDIT.md` | n=4 → n=8 输出 |
| `reports/w1_recommendation_accuracy_audit.json` | n=4 → n=8 输出 |

> 依赖顺序：**先重建 dashboard data（读 results overlay，DEFAULT_RHO 不变）→ 再跑 audit**。重建只是按本地数据确定性地把新赛果算进 calibration，不触碰任何模型参数。

---

## 2. 新 checker 规格：`check_w1_odds_movement_status_consistency.py`

校验对象：`reports/dashboard/assets/w1_dashboard_data.json` 内所有 `W1_ODDS_MOVEMENT_MONITOR_V1` 块 + `data/processed/match_cards/**` 所有卡片的 `odds_movement`。

断言项：

1. **枚举成员**：每个 `odds_movement.status` ∈ schema 枚举。出现 `THIN_MARKET_SKIP` → **WARN 不 FAIL**，并打印移除时间点。
2. **READY 不得出现在 odds_movement.status**：命中即 FAIL（READY 只能在 `market_signal.status` / `odds_status`）。
3. **status ↔ status_reason_code 前缀一致**：`SOFT_THIN_*` 只能在 `SOFT_THIN` 下，`HARD_THIN_*` 只能在 `HARD_THIN` 下，`ALERT_*` 只能在 `MARKET_ALERT` 下，依此类推。
4. **status ↔ 门控一致（核心不变量）**：用 §3 的同一张映射表，断言 `play_guard_input.recommended_gate`、`play_guard_input.allow_formal_judgment`、`calibration.gate_effect` 与 status 推导出的值**完全一致**；任一不符 FAIL。
5. **级联优先级显式存在**：断言代码内存在显式的优先级常量（见 §3），顺序为
   `HARD_THIN > SOFT_THIN > MARKET_CONFLICT > MARKET_ALERT > MARKET_MOVING > MARKET_STABLE`。

注册位置：加入 `reports/W1_EXPERT_PROJECT_REPORT.md` §7 的 canonical checker 清单；如有统一 runner（watcher/CI）枚举 checker，也一并登记。

---

## 3. 单一事实源：status → 门控映射表（实现与 checker 共用）

> 这张表是本阶段的核心交付：代码与 checker 必须引用**同一份**，不得各写一套。门控效果直接取自当前 791–820 行行为，**不做任何改动**。

| status | recommended_gate | allow_formal | reference_action | gate_effect |
|---|---|---|---|---|
| `HARD_THIN` | `SKIP` | false | `DOWNGRADE` | `HARD_SKIP` |
| `SOFT_THIN` | `OBSERVE_ONLY` | false | `EARLY_REFERENCE` | `WARN_ONLY` |
| `MARKET_STABLE` | `ALLOW_FORMAL` | true | `UPGRADE` | `ALLOW` |
| `MARKET_MOVING` | `OBSERVE_ONLY` | false | `HOLD` | `WARN_ONLY` |
| `MARKET_ALERT` / `MARKET_CONFLICT`（`calibrated=full` 且 `tier=A`） | `OBSERVE_ONLY` | false | `DOWNGRADE` | `TIER_A_GATE` |
| `MARKET_ALERT` / `MARKET_CONFLICT`（其余，当前默认 tier C） | `OBSERVE_ONLY` | false | `RECOMPUTE`（major 时）/ `HOLD` | `WARN_ONLY` |

级联优先级常量（判定多条件命中时取最高优先）：

```
HARD_THIN > SOFT_THIN > MARKET_CONFLICT > MARKET_ALERT > MARKET_MOVING > MARKET_STABLE
```

> 备注：当前 monitor 实际尚未产出 `MARKET_CONFLICT`（`coherence.x2_ou_ah_consistent` 恒为真）。它在表与优先级中**保留占位**，本阶段不实现其触发逻辑（属行为变更，见 §4）。

---

## 4. 禁止事项（本阶段红线）

- ❌ 不拆"流动性轴 / 异动轴"两个正交字段（thin 短路异动的重构留到后续立项）。
- ❌ 不改任何门控行为：§3 映射表只是把现有 if/elif 抽成表，输出必须逐项等价。
- ❌ 不改 `config/w1_odds_movement_thresholds.json`（阈值、tier、liquidity 全部不动）。
- ❌ 不改 `scripts/w1_score_engine.py` 的 score matrix core、`DEFAULT_RHO`、lambda 反解、devig、OU→μ 逻辑。
- ❌ 不实现 `MARKET_CONFLICT` 触发逻辑（仅占位）。
- ❌ 不根据 n=8（或任何单场/小样本）调 rho、score matrix、推荐政策或盘口阈值。
- ❌ 不把方向准确率当作调参依据；核心评估仍为 RPS / log score。
- ❌ 审计刷新只动 audit/report 与重建的 dashboard 派生产物，不动模型代码与配置。

---

## 5. 验收 checklist

### A. 口径一致性
- [ ] schema 枚举已含 `HARD_THIN` / `SOFT_THIN`；`THIN_MARKET_SKIP` 标注 deprecated + 移除时间点。
- [ ] `build_w1_dashboard_data.py` 中 status→门控已重构为 §3 单一映射表；输出与改造前逐场逐字段等价（diff 验证）。
- [ ] 级联优先级已写成显式常量，顺序符合 §3。
- [ ] 输入侧 `THIN_MARKET_SKIP` 归一到 `HARD_THIN`。
- [ ] `fixture_1538999` 卡片的 `READY` 已从 `odds_movement.status` 清除并归位到 `market_signal.status` / `odds_status`。
- [ ] `reports/dashboard/assets/w1_dashboard_data.json` 与 `W1_VISUAL_DASHBOARD.html` 已重建，24 场 status 全部合法。

### B. 新 checker
- [ ] `scripts/check_w1_odds_movement_status_consistency.py` 已创建，§2 五条断言全部实现。
- [ ] 对 `THIN_MARKET_SKIP` 为 WARN 非 FAIL，并打印移除时间点。
- [ ] 已登记进 `W1_EXPERT_PROJECT_REPORT.md` §7 及统一 runner。

### C. 审计刷新
- [ ] dashboard data 已先重建，8 场完赛均有 `post_match_calibration`。
- [ ] audit md/json 已更新为 n=8（含德国 7-1、荷兰 2-2、科特迪瓦 1-0、瑞典 5-1）。
- [ ] 报告显著注明：**n=8 仍太小，不能据此调参**；德国 7-1、瑞典 5-1 为打开局/尾部样本，mean log-loss 上升属预期，**尾部偏重样本、非调参触发**。
- [ ] 审计头部新增 "as-of 时间 + 与 results 文件一致性" 字段，避免再次过期未察。

### D. 全量回归
- [ ] 原 8 个 checker 仍全部 PASS：`check_w1_score_matrix` / `recommendation_output_policy` / `market_probability_panel` / `post_match_result_sync` / `dashboard_backend_predict_integration` / `visual_dashboard` / `rho_calibration` / `production_lite`。
- [ ] 新 checker PASS。
- [ ] `git diff` 仅覆盖 §1 文件范围；无 thresholds / score_engine / rho 变更。

---

## 6. 完成输出格式

阶段结束产出一份 `reports/W1_P0_CONSISTENCY_AND_AUDIT_REFRESH_V1_RESULT.md`，包含：

1. **STATUS / HEAD**：阶段状态、起止 HEAD。
2. **checker 结果**：9 个 checker（8 原 + 1 新）逐个 PASS/FAIL 实跑输出。
3. **枚举变更前后对照**：odds_movement.status 旧/新枚举 + THIN_MARKET_SKIP 移除时间点。
4. **READY 修复确认**：fixture_1538999 改前/改后片段。
5. **审计 n=4 → n=8 对照**：direction_accuracy、mean_rps_1x2、mean_exact_score_log_loss 等关键指标前后值（仅陈述，不解读为调参信号）。
6. **改动文件清单**：`git diff --name-only`，逐条对应 §1。
7. **禁止事项核对**：§4 每条逐项声明"已遵守"，并附 thresholds/score_engine/rho 未变的 diff 证据。
8. **边界声明**：研究用途、不构成投注/资金建议、不承诺命中率。

完成报告**不得包含**：任何"因本次赛果建议调整 X"的措辞；任何命中率/收益承诺；任何把 n=8 当作调参依据的结论。

---

## 7. 本阶段明确不含（顺延项，勿丢）

来自 V3 但不属本阶段，记录以免遗漏：

- `w1_score_engine.py` 头注释"不接入生产"陈旧、docstring 误写 scipy 依赖 → 可并入本阶段文档清理，或单列 doc-nit。
- `collapse_mass` 命名两义（summary=blowout vs score_pool=热门输球）→ 顺延。
- μ 用 OU 中位线当均值、proportional 去水偏差、单场拟合误差升 WARN → 属模型研究，进 P2 回测后处理。
- 流动性轴 / 异动轴正交拆分 → 单独立项。
- 盘口快照采集（P1）、历史回测框架（P2）→ 本阶段后启动。
