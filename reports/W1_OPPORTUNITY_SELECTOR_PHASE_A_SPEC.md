# W1_OPPORTUNITY_SELECTOR — 阶段 A 执行规格书（供技术人员实施，待我验收）

> 来源：《W1 系统升级报告书 — 专家修订版》确认结果。
> **已确认的边界（4 项决策）**：
> 1. **方案 A**：W1 是**研究系统**，不是投注/推介系统。
> 2. **承认现状**：当前 selector ≈ **市场共识**，**不得声称独立优势**。
> 3. **本轮只做阶段 A**：**只读 Candidate 统一 + 视图分离**（不做校准/不做选择器/不做 λ 因子调整）。
> 4. **API 不接生产路径**：只保留**离线验证 + 后续数据结构准备**。
>
> 本规格是给执行人员的任务清单。每个任务给出**升级思路（为什么这样做）/ 输入输出 / 红线约束 / 验收标准**。

---

## 全局红线（每个任务都必须守）

- **不改** `scripts/w1_score_engine.py`、`DEFAULT_RHO=-0.057766`、`config/w1_decision_policy.json`、`config/w1_odds_movement_thresholds.json`。
- **不改** `build_w1_dashboard_data.py` 里的 **λ / score matrix 计算逻辑**（candidates 必须是**只读派生**，不新增模型计算、不调 λ）。
- **不接 API / 不抓取 / 不爬取 / 不采购**。
- **不做** 校准（Phase B）、**不做** 风险扣分提升准确度声明、**不做** TOP_PICK 单点选择（Phase D）。
- **文案守红线**：不得出现"投注/下注/资金/入场/升盘/命中率承诺/最高命中率/机会(投注含义)"等措辞；候选一律标注"**≈市场共识 · 未校准 · 非独立优势 · 非推介**"。
- 所有候选必须可**自洽追溯到同一 score matrix**。

**命名约定**：模块/字段用中性研究语义——`candidate` / `market_read` / `basis="market_implied_score_matrix"` / `independent_edge=false`。**不要** `TOP_PICK` / `opportunity`（那是 Phase D，且需红线再确认）。

---

## 任务 A1 — 只读 Candidate 统一派生器

**目标**：把 1X2 / OU / AH / BTTS / score_pool 统一成一个 `Candidate` 列表。

**升级思路**：
- 现状各市场读数散落在 `market_probability_panel` / `safe_view` / `score_distribution` / `score_matrix_summary`，结构、口径不一，后续无法统一校准/比较。统一成单一数据契约，是 B/C/D 的地基。
- **关键设计**：每个 candidate 的 `raw_probability` **只能从同一 score matrix 只读派生**（复用既有 `derive_ou_from_score_matrix` / `derive_ah_from_score_matrix` / `derive_btts_from_score_matrix` / `derive_1x2_from_score_matrix` / `score_pool`），保证所有候选互相自洽、可追溯。**禁止**新建独立概率来源、禁止调 λ。
- OU/AH 的"四分之一盘"按报告 5.3.2 / 5.4.2 拆半注，输出确定性 `expected_result_score`（全赢×1 + 半赢×0.5 + 走水×0 − 半输×0.5 − 全输×1）。**这是矩阵的确定性结算口径，不是预测/命中率声明**。
- 每个 candidate 携带诚实元数据：`basis="market_implied_score_matrix"`、`independent_edge=false`、`calibrated=false`。

**输入**：现有每场 score matrix（`λ_home`/`λ_away`/`ρ`）或已派生的盘口面板 + 该场可用盘口线集合。
**输出**：每场 `candidates: [{market, selection, line|null, raw_probability, expected_result_score, basis, independent_edge:false, calibrated:false}]`。
**建议文件**：`scripts/w1_candidate_builder.py`（纯函数、只读、可被 build 与离线脚本共用）。

**红线**：只读派生；不改 engine/λ；不接 API；无 edge/投注字段。
**验收**：① 1X2 三项和≈1、OU(over+under)≈1、AH(win+push+lose)≈1（自洽）；② 每条 `independent_edge=false`、`calibrated=false`；③ 无任何 TOP_PICK / 选择逻辑；④ candidates 概率与 `score_matrix_summary` 派生一致（抽样核对）。

---

## 任务 A2 — build 集成 candidates（只读）+ 离线验证脚本

**目标**：把 A1 挂进 dashboard 数据（只读字段）；提供 128 FULL 子集上的离线研究统计。

**升级思路**：
- build 时调用 A1，把 `candidates` 作为**新增只读字段**挂到 match record（**不动**既有 λ/矩阵/recommendation_view 计算）。API 不接，所以 candidates 在 build 时从既有快照/内嵌数据离线派生。
- 新增**离线验证脚本**（如 `scripts/w1_candidate_offline_eval.py`）：对 2018+2022 的 128 FULL 子集，跑 candidate 派生，输出每市场 **raw_probability vs 实际结算** 的**研究统计**（reliability/分布），作为 Phase B 校准的输入基线。**这是研究统计，不是业务命中率，报告里不得表述为"推荐命中率"。**

**输入**：128 FULL 扩展数据集（已有）、score matrix。
**输出**：record 增 `candidates`；`reports/w1_candidate_offline_eval_v1.json`/`.md`（研究统计）。

**红线**：build 的 λ/矩阵不变；candidates 只读；不接 API；统计措辞中性（raw vs realized，非命中率推介）。
**验收**：① build 后 record 含 `candidates`，且 `check_w1_dashboard_data_binding` 等既有 checker 仍 PASS；② 离线脚本能在 128 样本跑出每市场 raw vs realized 统计；③ 确定性（同输入重跑结果一致，可入仓不 churn）。

---

## 任务 A3 — Dashboard 视图分离：Director View / Analyst Debug View（纯展示）

**目标**：把展示分成"总监一眼看结论"与"分析员追溯全量"两态。

**升级思路**：
- **Director View** = 复用已落地的 `W1_DASHBOARD_DECLUTTER_V1` 第一屏（谁占优 / 进球多少 / 首发 / 数据可信度 / 盘口异动 / 现在该干嘛 + 弱化比分行），**再加一块"市场各方向共识（校准前）"**：把 candidates 按 `raw_probability` 排序展示，**显著标注**"≈市场共识 · 未校准 · 非独立优势 · 非推介"。**不做单一高亮/TOP_PICK**。
- **Analyst Debug View** = 现有"专家视图"折叠区 + **完整 candidates 表**（含 `expected_result_score`、`basis`、各市场全量）。
- 纯展示重排，**不接 API、不改 build 计算**。

**输入**：record.candidates（A2）。
**输出**：`reports/dashboard/W1_VISUAL_DASHBOARD.html` 渲染层改动（pCore/专家区）。

**红线**：纯展示；无投注/入场/命中率语言；候选块必带"非推介/未校准/非独立优势"标注；不接 API。
**验收**：Director View 出现候选共识块且带标注；Analyst 区有完整 candidates；`check_w1_visual_dashboard` / `check_w1_recommendation_output_policy` PASS；无投注语言。

---

## 任务 A4 — Prospective Ledger 候选字段（数据结构准备，不接 API）

**目标**：为后续 B/C/D 的赛前锁定验证**预留并写入**候选快照结构。

**升级思路**：
- 在既有 prospective ledger schema 增 `candidates_snapshot`（赛前锁定时全部候选的 `raw_probability`/`expected_result_score`/`basis`），**为将来"赛前锁定 → 赛后结算 → 校准"闭环准备数据结构**。
- **本阶段只加结构 + 写入离线派生值**，**不接 API、不接实时**。保持既有 ledger 的 **write-once / lock_as_of ≤ kickoff / 无赛后字段泄漏** 约束（`check_w1_forward_prospective_run.py` 必须仍 PASS）。

**输入**：A1 候选；既有 ledger schema。
**输出**：ledger schema + 写入逻辑增 `candidates_snapshot`（gitignored runtime store 不变）。

**红线**：不接 API；无赛后泄漏；只读派生写入；不改锁定语义。
**验收**：ledger 含 `candidates_snapshot` 且可追溯当时矩阵；`check_w1_forward_prospective_run` 仍 PASS（无 hindsight）。

---

## 任务 A5 — Checker：阶段 A 守红线 + 自洽 + 非推介

**目标**：把阶段 A 的不变量写成硬断言。

**升级思路**：新增 `scripts/check_w1_opportunity_phase_a.py`（skip-safe），断言：
1. 所有 candidate `basis="market_implied_score_matrix"`、`independent_edge=false`、`calibrated=false`；**不得**出现 `calibrated=true` 或任何 TOP_PICK/选择字段（防止偷偷进入 B/D）。
2. candidates 概率自洽（1X2/OU/AH 和≈1）。
3. 源码与产物**无** edge/命中率/投注/入场/升盘 词（中性研究措辞）。
4. **红线静态守卫**：engine/`DEFAULT_RHO`/decision_policy/thresholds 未改；build 的 λ/矩阵函数未改（按既有 protected-file git diff 思路）；候选派生模块与离线脚本**无网络导入**（`requests`/`urllib`/`socket`/`web_fetch` 等）。
5. Director View 候选块带"非推介/未校准/非独立优势"标注。

**验收**：checker PASS；反向测试（注入 `independent_edge=true` 或 `calibrated=true` 或 TOP_PICK 字段）→ 正确 FAIL。注册进 §7。

---

## 任务 A6 — 文档 + 注册 + 边界声明

**目标**：留痕 + 注册 + 重申边界。

**升级思路**：写 `reports/W1_OPPORTUNITY_SELECTOR_PHASE_A_RESULT.md`（改动清单、红线确认、候选自洽证明、离线统计摘要、是否回滚、真机 commit/push 命令）；§7 注册 `check_w1_opportunity_phase_a`；重申：**W1 是研究系统；candidates ≈ 市场共识、非独立优势；不承诺命中率；不构成投注/入场建议**。

**验收**：文档齐全、边界声明在；§7 已注册。

---

## 阶段 A 总验收口径（我来做）

- 全量 `check_w1_*.py`：除既有非回归（`watcher` 沙箱路径 / 天气类缺数据 / 未暂存 git-diff 守卫 / embed_boundary 需先 commit）外，**0 新回归**；新 `check_w1_opportunity_phase_a` PASS。
- **红线**：engine/`DEFAULT_RHO`/decision_policy/thresholds/build-λ 未改；未接 API；无投注/命中率/edge 语言；候选全部 `independent_edge=false`。
- candidates 与 score matrix **自洽**；离线统计可复现（确定性、可入仓不 churn）。
- Director/Analyst 视图分离正确；候选共识块带"非推介/未校准/非独立优势"标注。
- **未做** B（校准）/ C（因子-λ）/ D（选择器）——确认本阶段边界没被越过。

---

## 阶段 A **不做**（明确划界，避免越权）

- ❌ 概率校准（Phase B，研究，需数据）
- ❌ 因子-λ 调整（Phase C，data-gated，需 walk-forward 证明 + 红线再确认）
- ❌ opportunity_score / TOP_PICK 单点选择器（Phase D，需红线再确认）
- ❌ 接 API / 抓数据 / 改引擎 / 改 `DEFAULT_RHO`

> 完成顺序建议：A1 → A2 → A3 → A4 → A5 → A6。每个任务保持"纯展示 / 只读派生 / 不接 API"。全部完成后通知我，我按上面"总验收口径"逐项核验后再确认验收。
