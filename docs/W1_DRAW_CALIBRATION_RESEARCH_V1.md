# W1_DRAW_CALIBRATION_RESEARCH_V1 — 研究 SPEC

**类型**: 纯研究 / prototype / diagnostic backtest
**production_wired**: false · **research_only**: true · **prototype**: true
**日期**: 2026-06-16

> 本阶段**只研究、不修生产**。不改 `w1_score_engine.py`、不改 `DEFAULT_RHO`、不接 dashboard/predict/build、不调任何生产参数、不抓新数据、不外推到 1081/预选赛。

---

## 1. 研究问题

当前生产引擎是 **market-implied Dixon-Coles**：1X2 devig → OU 反解 μ → 固定 `DEFAULT_RHO = -0.057766`、单参数 δ（supremacy）经黄金分割拟合复现市场 1X2。`W1_FULL_PIPELINE_ANOMALY_REVIEW_V1` 已确认：128 场 FULL 子集里 **11/128** market-reproduction 超阈值，**全部为 `DRAW_RATE_TENSION`**，`data_bug_found=false`——根因是"μ 固定、ρ 固定、单 δ 拟合 H/D/A"时**平局自由度不足**，复现误差落在 Draw。

**问题**：是否存在一种比 fixed-rho DC **更稳定的 draw calibration 方案**，能解释并（可能）改善这 11/128 的 Draw 残差集中——且在 walk-forward 下**对样本外仍成立**、不牺牲其它指标？

**关键区分（研究核心）**：
- "market reproduction" = 模型多大程度**复述市场 1X2**（与赛果无关）。
- "outcome skill" = 模型对**真实赛果**的概率质量（RPS/logloss/Brier）。
引擎本质是市场再表达，复述误差变小**未必**等于预测赛果更准。本研究要把这两件事**分开度量**。

---

## 2. Baseline

- `B0 = fixed-rho market-implied DC`（生产现状）：`solve_lambdas(p1x2, μ, ρ=DEFAULT_RHO)` → `score_matrix` → model H/D/A。
- 复用 `scripts/w1_backtest_full_pipeline.py` 完全相同的 128 场 FULL 子集、输入解析与指标口径；引擎只读 `import`。

---

## 3. Candidate methods

### C1 — diagnostic draw-fit rho（oracle_like / market_reconciliation_only=true）
每场在 ρ 网格上搜索 `rho_draw_fit`，使 `model_draw` 尽量贴近 `market_draw`（δ 仍由 `solve_lambdas` 内部拟合）。
- **仅作上界/诊断**：用赛前可得的 `market_draw` 反推，揭示"ρ 需要怎样逐场变化才能吸收 Draw 残差"以及"复现误差→0 时 outcome skill 改善多少"。
- 标记 `oracle_like=true`，**不可作为生产候选**（逐场后验、不具泛化形式）。

### C2 — simple draw calibration layer（research_only）
对 baseline score matrix 做**后处理**：把对角线（Draw mass）缩放到目标 `market_draw`，非对角线按比例缩放到 `1−market_draw`，**保持总概率=1、保持 home/away 非平局相对比例**。
- 确定性后处理，不引入逐场自由参数；仅研究，不接线上。

### C3 — parametric walk-forward rho model（唯一具泛化形式的候选）
用**仅赛前可得特征**拟合 ρ：`μ`、`market_home/draw/away`、`favorite_strength=max(home,away)`、`knockout/neutral flag`、`total-goal level`。
- 目标量 = C1 的 `rho_draw_fit`；用**线性回归**（小样本、低自由度，抗过拟合）。
- **必须 walk-forward**：按 `match_date` 时序切分，train 拟合 → val/test 预测 → 仅以**test（样本外）**判定是否 beats baseline。
- **禁止**：用赛后结果逐场调参；**禁止**全样本拟合后再报全样本成绩冒充泛化；ρ 预测值 clip 到安全区间避免退化矩阵。

---

## 4. 指标（每个候选都输出）

1X2 **RPS** / **logloss** / **Brier**；**draw calibration ECE**；**draw-specific logloss / Brier**（Draw vs not-Draw 二分类）；**exact-score logloss**；**OU ECE**（O1.5 / O2.5）；**BTTS ECE**；**market reproduction error**（mean / pass-rate@0.02）；**train/val/test 分段**；**beats_baseline**（逐指标）；**tradeoff 标记**（Draw 变好但 exact-score/OU/BTTS 变差）。

---

## 5. Walk-forward 设计

- 按 `match_date` 升序，chronological **60/20/20**（train/val/test），无未来泄漏（与 baseline 回测一致）。
- C1/C2 为 in-sample reconciliation（非泛化），其指标仅作上界/诊断对照。
- C3 在 train 上拟合、在 **test** 上评估泛化；同时报 train vs test 差距作为过拟合诊断。

---

## 6. 过拟合风险

- 128 场、finals-only、含 knockout/neutral-site，结构特殊、样本小 → 任何"改善"都可能是噪声。
- C1 是逐场后验上界，**天然乐观**，不可当泛化证据。
- C3 用线性、低维特征、walk-forward + train/test gap 控制过拟合；若 test 不稳定或 train≫test，判为过拟合、不推荐。

---

## 7. 不接生产边界（红线）

不改 `scripts/w1_score_engine.py`、`DEFAULT_RHO`、`config/w1_decision_policy.json`、`config/w1_odds_movement_thresholds.json`；不接 dashboard/predict/build；不调生产参数；不抓数据/不接 API/不爬取/不采购；不外推 1081/预选赛；无投注/资金/命中率表达。所有产物为研究报告，**不得直接上线**。

---

## 8. 失败条件（命中即停并如实回报）

- 候选必须改生产引擎才能跑。
- 本地 FULL 子集数据缺失无法复现。
- walk-forward 指标不稳定。
- Draw 改善但 RPS/logloss/exact-score 显著变差（tradeoff）。
- checker 需要降低标准才通过。
- 任何生产红线文件出现 diff。

---

## 9. 产物

- `scripts/w1_draw_calibration_research.py`（研究脚本，只读输入）
- `scripts/check_w1_draw_calibration_research.py`（研究 checker）
- `reports/w1_draw_calibration_research_v1.json` / `.md`（指标）
- `reports/W1_DRAW_CALIBRATION_RESEARCH_V1_RESULT.md`（结论 + 是否推荐 `W1_DRAW_CALIBRATION_PROTOTYPE_V2`；**不得直接推荐生产接入**）
