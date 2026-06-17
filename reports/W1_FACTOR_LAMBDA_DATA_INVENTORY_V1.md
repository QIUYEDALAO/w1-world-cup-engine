# W1_FACTOR_LAMBDA_DATA_INVENTORY_V1 — 离线历史样本盘点

**目的**: 盘点**本地已有**的历史数据，判断阶段 C（FiveDim 因子有效性历史验证）能否在**不接 API、只用本地文件**的前提下进行；并给出"组装验证样本"的离线方案、schema、防泄漏与样本外设计。
**性质**: **盘点 + 组装计划**。本文件**不动模型、不动 λ、不接 API、不爬取**；不写死任何因子系数；解锁的是阶段 C（研究），**不是** D/E/F。
**日期**: 2026-06-17

---

## 0. 一句话结论

**和阶段0给人的印象相反：本地历史数据相当充足，阶段 C 的 5 个维度里有 3 个(市场/实力/战术)基本可用本地数据验证，无需接 API。** 真正缺的是**阵型化学(无任何首发/球员级数据)**和**天气历史**。因此下一步是写一个**只读、离线**的样本组装脚本，把现有 CSV 拼成"每场一行、带赛前可得特征 + 市场隐含概率 + 真实赛果"的验证集——而不是去采购或接口。

---

## 1. 本地历史资产目录（实测）

| 资产 | 量 | 关键列 | 用途 |
|---|---|---|---|
| `data/historical/raw/football-data/*.csv` | 5 联赛(E0/D1/I1/SP1/F1)×6 季 = 30 文件，**≈10,733 场** | 结果(FT/HT)、**射门 HS/AS、射正 HST/AST、角球 HC/AC、犯规、牌、裁判**、**1X2 多家、OU 2.5、完整亚盘 AHh+收盘 AHCh** | 俱乐部联赛因子验证主力 |
| `data/historical/rho_calibration_real.csv` | **10,732 行** | match_date、teams、收盘 1X2、收盘 OU 线+赔率、goals | 已蒸馏好的"赔率+赛果"干净表(我做平局校准用过) |
| `data/processed/international/w1_international_dataset_extended.csv` | **1,081 场**(qualifier 889 / finals 192) | 1X2/OU/AH 可用标记、**home/away_xg(339 场有)**、shots/SOT、neutral_site、is_host、goals(90/ET/pen) | 国家队/世界杯因子验证 |
| `data/local_odds/world_cup_odds_historical.csv` 等 | 129 + 2018/2022 各 64 | 1X2、多线 OU、BTTS | 世界杯专项市场基线 |

> 注：football-data 的 `rho_calibration_real.csv` 已是 ≈1.07万场的清洁版；国际集 1,081 场含部分 xG。**这些都已在本地、gitignored，不需要任何网络。**

---

## 2. 五维 × 可验证性映射（核心）

| 维度 | 本地能否验证 | 数据来源 | 说明 / 泄漏注意 |
|---|---|---|---|
| **市场 market** | ✅ 完整 | 全部数据集的赔率列 | W1 既有领域；赛前收盘赔率天然赛前可得 |
| **实力 strength** | ✅ 可离线派生 | 由**历史赛果**算滚动积分/净胜/进失球；ELO 可用赛果离线迭代计算（**不接 API**） | 只能用**该场之前**的赛果；当场结果禁止入特征 |
| **战术 tactical** | ✅ 部分 | football-data 的**滚动**射门/射正/角球；国际集**滚动** xG(339 场子集) | 关键：射门/xG 是**赛后统计**，**只能取该队历史前 N 场的滚动值**，当场行的 FT 统计**严禁**作特征 |
| **阵型化学 chemistry** | ❌ 阻断 | 无 | 任何本地文件都**没有首发/球员级**数据 → 本轮无法验证 |
| **环境 environment** | ◐ 部分 | 由 match_date 派生休息天数/赛程拥挤；国际集有 neutral_site/is_host | **无历史天气**；天气维只能留空 |

**可验证的因子清单(阶段 E 候选,本轮只验证不上线)**: 滚动 xG/xGA、滚动射正率、休息天数差、ELO 差、主客/中立场、近 N 场滚动得失分。**阵型稳定性/伤停重要性 = 数据缺，暂不可验证。**

---

## 3. 防泄漏 / 时点对齐（命门，必须先定）

1. **point-in-time 规则**: 每场的特征只能用**该场 kickoff 之前**已知的信息。football-data 一行 = 一场**赛后**记录(含 FT 射门/角球) → 这些**当场**统计**永不**作该场特征，只能作为**后续**比赛的滚动历史。
2. **滚动窗口**: 每队取其 `match_date` 之前最近 N 场(N=5/10)的滚动均值/率。赛季初窗口不足 → 标 `degraded`，不补值。
3. **与现有黑名单一致**: 复用 FiveDim 的 `post_match_only_blacklist`(xg/shots/possession/corners/...)语义——这些**只能以"历史滚动"身份**进入特征，**当场值禁止**。checker 须对"当场 FT 统计是否泄漏进特征列"做硬断言 + 反向测试。
4. **赔率时点**: 用**收盘**赔率作市场基线(赛前可得)；若只有收盘价，明确标注，不假装是开盘。

---

## 4. 分层与红线（不可外推）

- **三层严格分开，禁止互相外推**: ①俱乐部联赛(≈1.07万)、②世界杯**预选赛**(889)、③世界杯**决赛圈**(192，含历史 finals 子集)。
- **红线**: **不外推 128→1081、不外推 finals→预选赛、不外推联赛→国家队**。每层各自验证、各出结论；小样本层(决赛圈 192)只给**区间/方向性**结论，不给点估计强结论。
- xG 仅 339/1,081 国际场可得 → **不插补**，无 xG 的场该因子标 `missing`，不强行参与。

---

## 5. 提议的离线组装（阶段 C 的第一步产物）

新增**只读**脚本（不接 API、不改引擎/build/dashboard）：

```
scripts/w1_factor_sample_builder.py   # 读 CSV → 输出 leakage-safe 验证样本(gitignored)
scripts/check_w1_factor_sample.py     # 硬断言:无当场泄漏 + 分层不混 + independent_edge 概念不声明
config/w1_factor_sample_policy.json   # 窗口N、分层定义、特征→来源映射、禁泄漏列
state/w1_factor_validation_sample.parquet|csv   # 输出(gitignored)
```

**升级思路**: builder 纯函数、只读 CSV；逐场构造"赛前滚动特征 + 市场隐含概率(复用现有引擎对赔率反解) + 真实赛果"；窗口不足标 degraded；输出落 gitignored `state/`。**不训练模型、不动 λ**——只产出供阶段 C 分析的对齐表。

---

## 6. 验证样本 schema（每场一行）

```
match_id, layer(league|wc_qualifier|wc_finals), league, season, match_date,
home, away, neutral_site,
# 市场基线(赛前)
mkt_p_home, mkt_p_draw, mkt_p_away, mkt_ou_line, mkt_p_over, [mkt_ah_line, mkt_ah_home],
# 赛前滚动因子(只用历史前N场; 不足=null+degraded)
home_form_ppg_n, away_form_ppg_n, home_gd_n, away_gd_n,
home_sot_rate_n, away_sot_rate_n, home_xg_roll_n, away_xg_roll_n,   # xg 仅国际子集
elo_home, elo_away, elo_diff, rest_days_home, rest_days_away, rest_days_diff,
# 标签(赛后, 仅作 y, 严禁作特征)
y_home_goals, y_away_goals, y_result_1x2, y_total_goals,
# 元
feature_asof_utc, leakage_safe=true, basis_per_feature{...}, independent_edge=false
```

---

## 7. 样本外设计

- **按季切分**: 联赛层用 2021–2324 拟合/2425–2526 留出；国际层按届(2014/18/22 vs 2026 周期)留出。
- **对照组**: 基线=纯市场隐含概率；处理组=市场 + 各候选因子。比"加因子是否在**留出集**上稳定改善校准(log-loss/RPS)"。
- **每层各自报告**，不合并掩盖差异(对应阶段 C 验收第4条)。

---

## 8. 样本量一览

| 层 | 场次 | xG 可得 | 备注 |
|---|---|---|---|
| 俱乐部联赛 | ≈10,733（清洁版 10,732） | 否(但有射门/角球) | 因子验证主力 |
| 世界杯预选赛 | 889 | 部分 | 中等样本 |
| 世界杯决赛圈 | 192(含历史 finals) | 部分(339 国际总计) | 小样本，仅方向性 |
| 世界杯赔率档 | 129 + 2018/2022 各64 | — | 市场基线 |

---

## 9. Blocker（本地无法解决，需另议且仍不接 API）

1. **阵型化学**: 无任何首发/球员级历史 → 阶段 C 无法验证该维。要么放弃该维进 λ，要么由你提供**离线**的历史首发数据。
2. **历史天气**: 无 → 环境维的天气因子本轮不验证（休息天数/中立场仍可）。
3. **xG 覆盖**: 仅 339/1,081 国际场；联赛层无 xG（只有射门代理）。
4. **决赛圈小样本(192)**: 不足以支撑强 λ 调整，只能给区间结论——直接对应"不外推 finals"红线。

---

## 10. 验收口径 + 解锁关系

**本盘点(本文件)验收**: ①资产目录属实(已实测)；②五维可验证性映射清晰；③防泄漏规则明确；④分层红线写死；⑤组装脚本与 schema 可执行。

**解锁**: 通过后可进入**阶段 C** = 跑 `w1_factor_sample_builder` + 离线分层验证，产出《FiveDim 因子有效性审计报告》。
**仍封锁**: **D(confidence 调整)/E(因子进 λ)/F(Primary Read Selector)** —— 必须等阶段 C 在**留出集**上证明某因子稳定改善校准，且有对照/回滚/checker，才可逐个讨论；**未验证前一律不动 λ、不上 selector**（与 Plan A 一致）。

---

## 11. 红线

只读本地 CSV；不接 API/不爬取/不采购；不动 `w1_score_engine`/`DEFAULT_RHO`/build λ·矩阵/受保护 config/dashboard；不外推 128→1081、不外推 finals→预选赛、不外推联赛→国家队；不插补缺失；输出落 gitignored；本阶段不写死任何因子系数、不声明独立优势。
