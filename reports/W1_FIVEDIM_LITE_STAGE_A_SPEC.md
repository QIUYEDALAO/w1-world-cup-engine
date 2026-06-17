# W1 FiveDim Lite · 阶段 A 执行规格（专家评审版）

**类型**: 阶段 A 执行规格 + 计划书评审结论
**评审对象**: 《W1 × 五维赛事评估系统升级合并项目计划书》
**日期**: 2026-06-17
**基线 HEAD**: `fe7eadd`（技术员 Phase A 候选层 + 我方 Director View 紧凑收尾）
**本规格授权范围**: **仅阶段 A（FiveDim Lite 只读数据层）**。B/C 另行授权；D/E/F **封锁**（见 §6）。

---

## 0. 评审结论（给老板/总监）

**判断：方向认可，可以执行；阶段 A 落地前必须钉死 §2 的 7 处修正。**

这版计划书比上一版 36 页报告成熟得多，且**已吸收上一轮评审**：分层不推翻 W1、`basis=market_implied` / `independent_edge=false` 标注、禁投注语言、"先只读再展示再验证再进模型"的顺序——全部对。

**已核对、属实、可用的事实：**

1. 阶段0 不是空话。`reports/W1_FIVEDIM_DATA_SUPPORT_VALIDATION.md` 与 `scripts/check_w1_fivedim_data_support_report.py` **真实存在**，且报告是**诚实的**——它自己写明："不能凭空声明'独立因子评估'，必须标注哪些维度实际上是市场共识的再表达"，结论是"**部分支持**"，不是"全面支持"。这与红线一致。
2. 维度四（市场）**已经建好**。技术员的 `scripts/w1_candidate_builder.py` 已用 `basis="market_implied_score_matrix"`、`independent_edge=False`、`calibrated=False` 产出候选，并有 checker 强制。**这就是 market_view，阶段 A 不要重写。**
3. match card 里 `elo / fifa_rank / form / h2h / injury / lineup / shots / rating / squad` 字段**存在但多数为空值**（阶段0 报告原文：ELO、FIFA Ranking 空值、player_minutes 无数据、无 squad_average_age）；`xG / possession / rest_days` **当前根本没有**。

**由此得出阶段 A 的真实定位（务必让总监理解）：**

> 阶段 A 产出的 FiveDim Lite Card，**只有 market_view 是满的**，strength/tactical/chemistry/environment **大部分是 `missing` / `degraded`**。它是一个**诚实的结构骨架**，不是"五维已经评估好了"。这正是计划书自己最担心的风险（把市场共识包装成独立优势）——所以阶段 A 的全部价值在于**把"哪些有数据、哪些没有、哪些只是市场再表达"如实结构化**，而不是凭空补满五维。

---

## 1. 命名澄清（避免技术员混淆两个 "Phase A"）

| 名称 | 是什么 | 状态 |
|---|---|---|
| **Opportunity Selector Phase A** | `w1_candidate_builder.py` 候选统一（市场隐含比分矩阵派生 OU/AH/BTTS/1X2/score_pool） | ✅ 已完成（fe7eadd） |
| **FiveDim Lite 阶段 A**（本规格） | 在候选层之上，新增只读五维数据卡：market_view **复用候选层**，其余四维如实抽取/标注缺失 | ⏳ 本次 |

**FiveDim Lite 的 market_view = 直接调用 / 包裹 `w1_candidate_builder`，不另起炉灶。**

---

## 2. 落地前必须钉死的 7 处修正（核心）

**C1 · market_view 复用候选层，不重写。**
`w1_fivedim_lite.py` 的 market_view 调用现有 `w1_candidate_builder.build_candidates(...)`，原样继承 `basis=market_implied_score_matrix` / `independent_edge=false` / `calibrated=false`。禁止平行实现一套市场派生逻辑。

**C2 · 四维"如实为空"，不得造值。**
strength/tactical/chemistry/environment 凡当前本地无值的字段，一律 `availability=missing` 或 `degraded`，**不得用占位数、不得用市场反解冒充独立因子**。环境维度里**确有**的（球场坐标可从 `data/static/world_cup_2026_venues.json` 映射、天气上下文、休息天数若可算）才标 `available`。

**C3 · 阶段 A 离线only，不碰外部源。**
计划书第四节架构图把 `api-football / Open-Meteo / ELO表 / 历史赔率库` 画成数据源——**那是远期愿景，不是本阶段授权**。阶段 A 只读：现有 match card、`w1_dashboard_data.json`、`data/static/*`、`config/*`。**禁止任何网络调用**；checker 加 `no-network-import` 静态守卫（复用现有同类守卫）。

**C4 · `post_match_only` 必须是硬断言（最重要的安全项）。**
policy 里维护一份**本场赛后统计字段黑名单**（本场 `xg / shots / possession / corners / final stats / halftime/fulltime score 等`）。checker 硬断言：这些字段**绝不能出现在 FiveDim Lite Card 的赛前视图字段里**；命中即 FAIL。允许的是**历史滚动**（近 5/10 场）——但当前本地无此数据，故阶段 A 这部分一律 `missing`。这是防"赛后数据污染赛前"的命门。

**C5 · 红线词 checker 复用、只强化。**
禁投注词检查复用现有红线词守卫机制，**只增不减**；新增 `redline_flags` 字段不得弱化任何既有断言。反向测试：塞入投注词必须 FAIL。

**C6 · 账本扩展，不另起平行账本。**
计划书 8.1 的 `prospective_ledger.jsonl` **不要新建**与现有账本并行的文件。现有 ledger 已有 `candidates_snapshot`（技术员 Phase A）。FiveDim 快照应作为**现有账本的扩展字段**，阶段 A 暂不强制（属阶段 C/F 闭环），本阶段只保证 Card 可复现生成。

**C7 · independent_edge 全维 false，无例外。**
阶段 A 每一个维度、每一条字段，`independent_edge=false`。任何"这维是我们独立算的"表述，都要等阶段 C 历史验证给出证据后才允许讨论——而那是 D/E 的事，已封锁。

---

## 3. 阶段 A 任务卡（含升级思路，供技术员执行）

> 总原则：**schema 先行 → policy 配置化 → builder 纯只读 → checker 强化 → 报告如实**。builder 只产出自己的 gitignored 输出，不写任何被跟踪文件。

### A1 · Schema `schemas/w1_fivedim_card_schema.json`
定义 FiveDim Lite Card 结构：`metadata / source_summary / market_view / strength_view / tactical_view / chemistry_view / environment_view / availability_flags / missing_fields / degraded_fields / basis_tags / redline_flags / independent_edge`。
**每个叶子字段统一形如 `{value, source, basis, availability}`。**
**升级思路**：schema 先定，builder 与 checker 都对着同一份 schema，避免"产出和校验对不上"。`basis` 取值受限枚举：`market_implied / historical_observed / manual_context / missing / degraded / post_match_only`。

### A2 · Policy `config/w1_fivedim_lite_policy.json`
声明：①每个维度各字段的**本地来源映射**（取自 match card 哪个路径 / dashboard_data / static）；②`post_match_only` **字段黑名单**（C4）；③禁投注词清单（复用现有，C5）；④降级规则（值为 null → degraded 还是 missing）。
**升级思路**：把"数据从哪来、哪些禁用"放进 config，将来本地接入新历史数据只改 config、不动 builder。**新增 config 文件，绝不改 `w1_decision_policy.json` / `w1_odds_movement_thresholds.json`。**

### A3 · Builder `scripts/w1_fivedim_lite.py`
对每张 match card 生成一张 FiveDim Lite Card：market_view 委托 `w1_candidate_builder`（C1）；其余四维按 policy 映射抽取本地字段，无值则如实标 `missing/degraded`（C2）；全程 `independent_edge=false`（C7）。**纯函数、只读输入；输出写到 gitignored 路径**（如 `state/` 或 `data/processed/` 下，沿用现有 runtime artifact 政策，避免改脏被跟踪文件）。
**升级思路**：遇缺失**绝不抛错**，只标注（计划书验收第2条）。不 `import` 任何网络库（C3）。输出对同一输入**确定性**（无运行时时间戳混入被校验内容）。

### A4 · Checker `scripts/check_w1_fivedim_lite.py`
硬断言（计划书 10.5 的 7 条 + 我方强化）：
1. 五个维度键都在；2. 每个字段有 `availability`；3. 每个字段有 `basis`；4. market_view `basis=market_implied` 且 `independent_edge=false`；5. **`post_match_only` 黑名单字段不得进赛前视图（C4，反向测试）**；6. 无投注词（C5，反向测试）；7. 任何维度不得 `independent_edge=true`；8. **no-network-import 静态守卫（C3）**；9. 不读 `round1_results` 等赛后结果作赛前输入。
**升级思路**：**只增不减**，每条断言配反向测试（注入坏值必 FAIL）。不修改任何现有 checker，只新增本文件。

### A5 · 实施报告 `reports/W1_FIVEDIM_LITE_STAGE_A_IMPLEMENTATION.md`
含：**维度覆盖表**（每维 available / degraded / missing 的字段数，照实写"四维大部分空"）；红线确认；本机 commit/push 命令；非范围声明。
**升级思路**：报告必须**如实呈现空洞**，不得用"五维已就绪"之类表述误导总监。

---

## 4. 阶段 A 验收口径（我方复核）

1. 24 张 match card 均能生成 FiveDim Lite Card，缺失字段**不报错**。
2. 每个字段都有 `source / basis / availability`；market_view `independent_edge=false` 且 `basis=market_implied`。
3. **`post_match_only` 黑名单字段在赛前视图中为零**（抽查 + checker 反向测试通过）。
4. 四维 `missing/degraded` 比例与阶段0 报告**一致**（不得凭空变满）。
5. `check_w1_fivedim_lite` PASS 且每条断言反向测试有效；**现有全部 checker 不回归**。
6. 仅新增文件；**未改** `w1_score_engine.py` / `build_w1_dashboard_data.py` / dashboard / `w1_decision_policy.json` / `round1_results.json` / `DEFAULT_RHO`；**无网络**。

---

## 5. 红线（不变）

不改引擎 / `DEFAULT_RHO=-0.057766` / build 的 λ·矩阵 / 受保护 config；不抓取/不接 API/不爬取/不采购；不造假数据；不弱化任何 checker 安全断言（只增/强化）；不外推；`data/local_odds/*`、`data/processed/*` 维持 gitignored；非投注平台、不输出资金/命中率、不把模型-市场分歧表述为投注机会。

---

## 6. 明确**不做**（封锁项，越界即停）

- **阶段 B（Director View 接五维）**：不在本规格。要做也须**复用刚压缩好的 Director View**，且"五维信号摘要"块**只在该维真有数据时才显示**——四维全空时**不得**摆一个全是"数据不足"的五维灯，否则比不显示更糟、且有"假装有五维"之嫌。
- **阶段 C（历史样本验证）**：**门控**。当前本地**没有**世界杯/五大联赛的历史样本与赛前时间戳数据，`w1_fivedim_historical_validation` **无数据可跑**。须先有一次**离线、本地、gitignored** 的历史样本盘点（即此前登记的 `W1_FACTOR_LAMBDA_DATA_INVENTORY_V1`）才能谈验证。不得用"已验证"措辞而无样本外证据。
- **阶段 D / E / F（confidence 调整 / λ 因子 / Primary Read Selector）**：**全部封锁**。这些触碰"独立优势"边界——老板已拍板 Plan A：接受当前 selector ≈ 市场共识、不声称独立优势、API 不接生产路径。未经历史验证（C）给出证据 + 你新的明确授权，**一律不动 λ、不上线 selector**。

---

## 7. 推荐授权边界（请确认）

- **现在**：授权 **阶段 A**（本规格，技术员执行 / 或交我直接实现）。
- **其后**：阶段 A 验收通过 → 再单独授权 **阶段 B**（展示，按 §6 约束）。
- **研究门控**：阶段 C 需先补"历史样本盘点"才有意义。
- **封锁**：D/E/F 维持封锁直至 C 出证据 + 新授权。

> 一句话：**按计划书走，但只放行到"如实结构化"为止；任何"声称独立优势/动 λ/上 selector"都卡在历史验证后面。**
