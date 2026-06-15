# W1 World Cup Engine 专家评审报告 V3：全链路评审与修复清单

生成时间：2026-06-15 CST
项目路径：`/Users/liudehua/.openclaw/workspace/w1_world_cup_engine`
当前 HEAD：`7faa947`（branch=main，remote=none）
本轮验收：`check_w1_score_matrix` / `recommendation_output_policy` / `market_probability_panel` / `post_match_result_sync` / `dashboard_backend_predict_integration` / `visual_dashboard` / `rho_calibration` / `production_lite` 共 8 个 checker 实跑全部 PASS。

报告定位：供足球数据、盘口、概率模型与策略风控专家评审。本文只描述系统状态、模型假设、一致性核对与待修复项，不构成投注/下注/资金建议，不承诺命中率，不输出资金管理建议。

---

## 0. 总体判断

工程治理与"诚实度"在同类项目中属上乘：单一核心模型、显示层与模型层严格隔离、赛果只做评估不回流调参、rho 有 provenance、盘口阈值明确标注未校准且只 WARN。系统当前定位是**市场概率复述 + 多盘口一致性核对 + 可审计赛后复盘**，与设定边界完全吻合。

一个框架性结论需要先讲清：**λ 完全由市场反解，lineup/tactical 仍只是解释层、未进入 λ，因此模型的 1X2 方向 ≈ 市场方向，结构上无法跑赢市场。** 审计中 Qatar、Australia 两次方向错，本质是"市场看错、模型忠实复述"，不是模型缺陷。系统价值不在方向命中，而在多盘口自洽、风险读数与赛后校准——这点要管理预期。

---

## 1. 问题清单（按严重度）

| 级别 | 问题 | 证据 |
|---|---|---|
| 中 | `w1_score_engine.py` 头注释称"本文件不接入生产 build_w1_dashboard_data.py"，但 build 第 16 行 `import w1_score_engine as W1ENGINE` 确实接入了；docstring 写"依赖 numpy / scipy"，实际只用 numpy（金分搜索自实现） | `scripts/w1_score_engine.py:7,13` vs `scripts/build_w1_dashboard_data.py:16` |
| 中 | `odds_movement.status` 的 schema 枚举与代码实际输出不一致：schema 允许 `MARKET_STABLE/MOVING/ALERT/CONFLICT/THIN_MARKET_SKIP`，但代码输出 `HARD_THIN`/`SOFT_THIN`；另有 1 张 match card 写了 `READY`（也不在枚举内）。dashboard data 中 24 场全为 `SOFT_THIN` | `config/w1_match_card_schema.json` odds_movement.status；`build_w1_dashboard_data.py:770-778` |
| 中 | 准确率审计已过期：报告 n=4（2026-06-14 生成），但 `round1_results.json` 现有 **8** 场完赛（德国 7-1、荷兰 2-2、科特迪瓦 1-0、瑞典 5-1 为 06-15 同步） | `reports/w1_recommendation_accuracy_audit.json` vs `data/results/round1_results.json` |
| 低/设计内 | μ 取自 OU 的"中位线"却当作泊松均值使用，偏态下系统性低估总进球 | `w1_score_engine.py:fair_total_from_ou` |
| 低/设计内 | 比例去水（proportional）存在热门-冷门偏差，高估热门、低估平局/冷门 | `w1_score_engine.py:devig_proportional` |
| 低/设计内 | δ 单参数拟合 H/D/A 三目标，平局率被 μ 与 ρ 钉死；拟合误差未升级为每场 WARN | `w1_score_engine.py:solve_lambdas` |
| 低 | `collapse_mass` 命名两义：summary 中 = `blowout_prob`（\|净胜\|≥3，双向）；score_pool"防线崩盘"= 热门输球。同名不同义 | `build_w1_dashboard_data.py:1050` vs score_pool |
| 提示 | rho 在欧洲俱乐部联赛(E0/SP1/D1/I1/F1)校准，应用于国际赛/世界杯，存在域迁移；当前小样本打开局偏多（7-1/5-1/4-1），提示尾部可能偏薄 | `config/w1_rho_provenance.json` |

---

## 2. 逐条评审（对应 8 个重点问题）

### 2.1 λ / ρ / 市场隐含概率逻辑是否合理 —— 合理，标准做法，但有二阶偏差
链路（1X2 去水 + OU→μ → 金分搜索解 δ → λ → DC 矩阵）方法学站得住，ρ 作为有出处的校准常数而非每场拍权重，是对的。需记录的偏差：

- `fair_total_from_ou` 找的是去水 Over 概率 = 0.5 的**中位线**，却作为 λ_home+λ_away 的**均值**用。偏态分布下均值 > 中位，μ 被系统性低估一点，Over/总进球读数偏小。更干净的做法：用整条 OU 阶梯对模型隐含 Over 概率做最小二乘拟合 μ，顺带用上多档信息。
- 比例去水有已知热门-冷门偏差。Shin 或对数/幂（Wisdom-of-Crowds）去水更准，尤其对 1X2 平局。历史集建好后做 A/B。
- δ 一个自由参数拟合三目标，平局率实际被 μ、ρ 锁定。已用 `market_reproduction_max_abs_err < 0.02` 跟踪（很好），但平局结构异常的场次拟合误差会上升，应把它升为每场 WARN，不要静默。

### 2.2 1X2/OU/AH/BTTS 是否同源派生 —— 是，全系统最扎实部分
`derive_1x2/ou/ah/btts/clean_sheet/goal_band` 全部吃同一个由 λ_h/λ_a/ρ 重建的矩阵；Asian 四分盘拆分 (`_split_quarter_line`) 正确；`market_comparison` 把"模型读数"与"市场输入去水值"并排但分开标注；BTTS/零封/进球区间老实标注"模型隐含、未对该盘独立校准"。无意见。

### 2.3 主比分唯一 + 备选最多一个 —— 政策合理，纯显示层，不碰模型核心
一个必须讲清的语义点：`secondary_score` 是**第二可能结果桶(H/D/A)内的条件众数**，不是全局第二高比分。强热门时备选可能是 1-1（平局桶众数），即使 2-1 概率更高。设计本身好（给"另一种剧情"而非堆同方向比分），但普通页面必须讲清，别让用户把"主/备"读成"最可能的两个比分"。

### 2.4 HARD_THIN/SOFT_THIN/MARKET_MOVING/MARKET_ALERT 规则 —— 方向对，但仍是"等数据的规范"，未经真实数据验证
- 守门保守且正确：只有流动性 HARD_THIN 真正 skip；所有 movement 在 tier≠A/未校准时一律 WARN_ONLY（`hard_movement_gate = calibrated=="full" and tier=="A"`，当前恒为假）。
- 但阈值全是未校准默认值（tier C，n_positive=n_negative=0，shrinkage_w=0），MOVING/ALERT 的数字本质是猜测。
- 实战中 24 场全 SOFT_THIN（单一、偏旧快照、book 数不足），MOVING/ALERT/CONFLICT **一次都没触发过**，无法验证。
- 叠加 2.x 的枚举不一致问题。结论：在多档快照历史 + 正负样本标注积累出来之前，任何 movement 信号都不要升级为硬门槛。

### 2.5 result sync / 赛后校准是否有数据污染或调参风险 —— 隔离干净，无污染
sync（`w1_local_predict_server.py:790-814`）只写 actual_score + 来源标注，不碰 rho/阈值/权重；rho 来自独立联赛数据，非世界杯赛果；审计与报告反复强调"单场不调参"。唯一要守住的纪律：保持 results→calibration **单向**，永远别做"按赛果自动调参"。这条目前守得住。

### 2.6 dashboard 给普通用户的信息 —— 不算误导，免责清晰；两点提醒
头部只给参考倾向/比分、风险等级、现在该干嘛；专家细节（完整矩阵、全盘口阶梯、RPS）收在默认隐藏的 `#expert`（`display:none`）；顶部有"仅作研究参考，不构成收益承诺或操作指令"。两点：
- (a) 完整 payload（矩阵、所有阶梯、RPS）**全部内嵌在页面**，普通/专家之分只是前端可见性、非数据层裁剪——研究工具无妨，但别把隐藏数据当"私有"。
- (b) 把 2.3 的主/备语义、以及"参考比分≠预测保证"在普通页面再讲明白一点。

### 2.7 哪些进正式风控 / 哪些只应 WARN_ONLY
**硬门槛（可拦 W1_PLAY）—— 都是数据完整性/流动性，当前划分正确：**
首发未确认；1X2/AH/OU 任一缺失；HARD_THIN（无 1X2 或无 OU 共识）；overround > 1.12；快照 age > 60m；blocking_data_gaps > 0；AH 方向与 Elo 不一致。

**只应 WARN_ONLY：**
所有 movement 量级（tier C 期间）；SOFT_THIN（observe-only 即可）；lineup_effect/tactical_effect（未进 λ）；BTTS/零封/进球区间（未校准）；secondary_score；rho 域迁移。

**建议新增、目前却静默的 WARN：** 单场 `market_reproduction_ok=false`（拟合误差超阈）；μ/去水的模型假设标注；审计过期提示。划分本身健全，要补的是统一 schema 枚举 + 把上述静默条件显式化为 WARN。

### 2.8 下一步优先级 —— 建议排序（与现报告略有不同）
1. **P0：先做历史回测框架。** 其余一切都依赖它。没有域外国际比赛数据集（1X2+OU+AH+真实比分），无法验证去水选择、μ 提取、rho 迁移、是否需要 overdispersion、阈值 AUC——它一次性解锁第 2.1/2.3/2.4/2.8 个问题，也能用可靠性曲线做真正校准，而非在 n=8 上空谈。
2. **P1（并行，现在启动）：多档盘口快照采集。** collector 已建好且为空，阈值校准所需的正负 movement 样本只能随时间积累，受时间约束，必须现在接上每个 phase 的实时抓取。
3. **P2：盘口阈值校准。** 等 MAJOR_NEWS vs NO_NEWS 标注样本够了再做；之前保持 WARN_ONLY。
4. **P3（最后）：lineup/tactical→λ 研究。** 双重计价风险最高（市场已 price 已知首发）、边际价值最不确定、且必须靠 P0 回测证明存在"市场未吸收的残差"。在此之前保持解释层。

关于 overdispersion：小样本里打开局偏多、mean actual_score_probability 仅 0.069，**提示**矩阵尾部可能偏薄；但 n 太小不能下结论。等回测框架建好，再对比"负二项/过散边际"或"轻度抬高高总进球尾部" vs 纯 DC 的 log-score；别在能证明之前先加复杂度。

---

## 3. 修复清单（可勾选）

### P0 一致性与文档（低风险，建议本阶段就清）
- [ ] 修正 `w1_score_engine.py` 头注释：删除"不接入生产 build"的陈述，改为"生产 build_w1_dashboard_data.py 已 import 本引擎"。
- [ ] 修正 `w1_score_engine.py` docstring 依赖说明：`numpy / scipy` → `numpy`（确认无 scipy 运行期依赖）。
- [ ] 统一 `odds_movement.status` 口径：二选一——(a) schema/docs 升级为 `HARD_THIN`/`SOFT_THIN` 细分枚举；或 (b) 代码对外 status 收敛回 `THIN_MARKET_SKIP`，把 HARD/SOFT 降为 `status_reason_code`。
- [ ] 排查并修正写了 `odds_movement.status="READY"` 的那张 match card（READY 属 market_signal，不属 odds_movement）。
- [ ] 增加一个 schema 校验 checker，对 dashboard data 与 match cards 的 `odds_movement.status` 做枚举断言，防止再次漂移。
- [ ] 统一 `collapse_mass` 语义：summary 的 `collapse_mass`(=blowout) 与 score_pool"防线崩盘"(=热门输球)改用不同字段名或加注释。

### P0 评估刷新
- [ ] 重跑 `audit_w1_recommendation_accuracy.py`，把样本从 n=4 更新到 n=8（含德国 7-1、荷兰 2-2、科特迪瓦 1-0、瑞典 5-1）。
- [ ] 在审计报告头部加"样本 as-of 时间 + 与 results 文件一致性校验"，避免再次过期未察。

### P1 模型显式化 WARN（不改核心，只增可见性）
- [ ] 把单场 `market_reproduction_ok=false`（拟合误差超阈）升为面板可见 WARN。
- [ ] 在专家面板标注 μ 取自 OU 中位线的假设，并加 TODO：用整条 OU 阶梯最小二乘拟合 μ。
- [ ] 在普通面板补一行说明主/备比分语义（"备选=另一种结果方向的代表比分，非第二可能比分"）。

### P1 数据积累（受时间约束，越早越好）
- [ ] 接通 `w1_odds_snapshot_collector.py` 到每个 phase 的实时抓取，开始逐场积累多档共识盘口快照（book_count / staleness / spread / 主线变化）。
- [ ] 为 movement 样本设计 MAJOR_NEWS vs NO_MAJOR_NEWS 标注流程（标注新闻，不标注赛果）。

### P2 历史回测（解锁后续一切校准）
- [ ] 构建国际比赛回测集：fixture、球队、开赛时间、中立场、1X2/AH/OU、实际比分、首发/裁判可用性。
- [ ] 在回测集上 A/B：proportional vs Shin/对数去水；中位 μ vs 阶梯拟合 μ；纯 DC vs 过散/负二项尾部。以 log-score / RPS / 可靠性曲线为准。
- [ ] 用回测集复核 rho 域迁移：国际赛 rho 是否与联赛 rho 显著不同。

### P2 盘口阈值校准（依赖 P1 样本）
- [ ] 正负样本够后做 Tier A/B 校准：minor/medium 用 NO_NEWS 90 分位，medium/major 用 max(NO_NEWS 97 分位, Youden opt)；AUC < 0.65 的指标降级 WARN_ONLY。
- [ ] 校准完成前，`calibrated` 保持 none、movement 保持 WARN_ONLY。

### P3 研究类（回测就绪后再做）
- [ ] lineup/定位球/高点对 λ 的小幅修正研究；重点验证是否存在稳定、低幅度、不与市场重复计价的修正项。

---

## 4. 合规与边界

- 本系统仅做赛前/赛后数据分析研究，用于概率读数、一致性核对、风控门槛判断与赛后复盘。
- 不构成投注/下注/资金建议，不承诺命中率，不输出资金管理建议。
- API 凭据仅在后端环境变量使用（predict server 绑定 127.0.0.1，/health 不回传 key），不进入前端与报告。
- 本评审聚焦数据链路、概率模型、校准方法与风险控制，不应被解释为任何交易或资金操作依据。

---

## 5. 阶段末状态

STATUS：review V3 generated
HEAD：`7faa947`（remote=none）
checker：本轮 8/8 实跑 PASS
DEFAULT_RHO：`-0.057766`（provenance 已校准）
odds movement thresholds：tier C / uncalibrated（WARN_ONLY，THIN 流动性门除外）
完赛样本：8（审计文件仍记 4，待重跑）
BLOCKER：none
next_stage 建议：P0 一致性清理 + 审计重跑 → P1 盘口快照采集（并行启动）→ P2 历史回测框架
