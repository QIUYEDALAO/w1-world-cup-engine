# W1 FiveDim 数据支持验证报告

## 0. 执行摘要

**是否支持 FiveDim Lite 第一版落地：** 部分支持，需要明确降级策略和缺失数据处理方案。

**最大数据缺口：**
1. 绝对实力面（维度一）：ELO、FIFA Ranking 字段空值、player_minutes 无数据、无 squad_average_age
2. 战术高阶指标（维度二）：xG/statistics 仅赛后可用，无赛前时序数据
3. 阵型化学反应（维度三）：player_club/player_league 不可获取，但首发阵型+伤停位置影响可进入第一版
4. 市场与热度智慧（维度四）：W1 已有充足底库，H2H 可自行计算，外部舆情暂不启用
5. 外部物理与环境（维度五）：天气/坐标/休息天数可自动计算，伤停仅表面数据，裁判无数据

**是否存在 BLOCKER：** 否。不存在阻碍 FiveDim Lite 第一版落地的真正 BLOCKER。但存在多个 WARN_ONLY 缺口，需要在第一版中明确标注"非独立计算"或"降级为 Analyst View"。

**建议落地方式：**
- 阶段 A：在 W1 现有底座上，新增只读 FiveDim 数据代理层，不做独立计算
- FiveDim Lite 第一版限定为 "W1 数据底座的分析性重组"，所有因子的概率基础必须标注 `basis=market_implied_score_matrix`
- 不能凭空声明"独立因子评估"，必须标注哪些维度实际上是市场共识的再表达

---

## 1. 验证范围

- **验证时间：** 2026-06-17 08:44 CST
- **验证人/执行环境：** main agent → w1_world_cup_engine 工作区
- **数据源：** 项目本地文件、schema 定义、match card、snapshot JSON、代码逻辑分析
- **API 计划/限制：** api-football 和 Open-Meteo 已有集成但不在此阶段外部调用；ELO/FIFA Rank 需外部源但暂不尝试获取
- **抽样赛事：** 世界杯 2026 小组赛（24 场）
  本验证覆盖 24 场 match card、snapshot、dashboard_data
- **抽样场次数：** 24 场（涵盖所有世界杯小组赛第一轮）

---

## 2. 基础比赛数据

### 字段覆盖表

| 字段 | 可获得 | 来源 | 关键字段 | 历史数据 | 赛前时间戳 | match_id关联 | 缺失率 | 更新频率 |
|------|--------|------|----------|----------|------------|-------------|--------|---------|
| match_id | ✅ | match.card.match_id | `match_id: "api-football:1489369"` | ✅ 24场 | ✅ kickoff_utc | ✅主键 | 0% | 一次性 |
| league_id | ✅ | match.competition | `"FIFA World Cup"` | ✅ | ✅ | ✅ | 0% | 一次性 |
| league_name | ✅ | match.competition | 同上 | ✅ | ✅ | ✅ | 0% | 一次性 |
| season | ✅ | match.season | `2026` | ✅ | ✅ | ✅ | 0% | 一次性 |
| round/stage | ✅ | match.round | `"Group Stage - 1"` | ✅ | ✅ | ✅ | 0% | 一次性 |
| home_team_id | ✅ | teams.home.team_id | `"fixture:1489369:home"` | ✅ | ✅ | ✅ | 0% | 一次性 |
| away_team_id | ✅ | teams.away.team_id | 同上 | ✅ | ✅ | ✅ | 0% | 一次性 |
| home_team_name | ✅ | teams.home.name | `"Mexico"` | ✅ | ✅ | ✅ | 0% | 一次性 |
| away_team_name | ✅ | teams.away.name | `"South Africa"` | ✅ | ✅ | ✅ | 0% | 一次性 |
| kickoff_time | ✅ | match.kickoff_utc | `"2026-06-11T19:00:00Z"` | ✅ | ✅ 源头字段 | ✅ | 0% | 一次性 |
| fixture_status | ✅ | result_overlay | `"finished"` / `"not_started"` | ✅ | N/A | ✅ | 0% | 赛后填充 |
| venue_id | ✅ [隐含] | match.venue.name | venue name 作 ID | ✅ | ✅ | ✅ | 0% | 一次性 |
| venue_name | ✅ | match.venue.name | `"Estadio Azteca"` | ✅ | ✅ | ✅ | 0% | 一次性 |
| venue_city | ✅ | match.venue.city | `"Mexico City"` | ✅ | ✅ | ✅ | 0% | 一次性 |
| venue_country | ✅ | match.venue.country | `"Mexico"` | ✅ | ✅ | ✅ | 0% | 一次性 |
| venue_latitude | ⚠️ match card 中为 null | 静态 venues.json | world_cup_2026_venues.json | ✅ 16场 | ✅ | ✅ | 赛前 card：34%（8/24 为 null） | 静态 |
| venue_longitude | ⚠️ match card 中为 null | 同上 | 同上 | ✅ | ✅ | ✅ | 同上 | 静态 |
| neutral_flag | ❌ 无此字段 | N/A | 需要 league 级别推断 | ❌ | ❌ | ❌ | 100% | N/A |
| final_score | ✅ | results.round1_results | `{"home":2,"away":0}` | ✅ | N/A 赛后 | ✅ | 已完赛 7 场 | 赛后写入 |
| halftime_score | ❌ 无此字段 | N/A | — | ❌ | N/A | ❌ | 100% | N/A |
| extra_time_score | ❌ 无此字段 | N/A | — | ❌ | N/A | ❌ | 100% | N/A |
| penalty_score | ❌ 无此字段 | N/A | — | ❌ | N/A | ❌ | 100% | N/A |

### 样例

```json
{
  "match": {
    "match_id": "api-football:1489369",
    "competition": "FIFA World Cup",
    "season": 2026,
    "round": "Group Stage - 1",
    "kickoff_utc": "2026-06-11T19:00:00Z",
    "venue": {
      "name": "Estadio Azteca",
      "city": "Mexico City",
      "country": "Mexico",
      "latitude": null,
      "longitude": null
    }
  },
  "teams": {
    "home": {"team_id": "fixture:1489369:home", "name": "Mexico"},
    "away": {"team_id": "fixture:1489369:away", "name": "South Africa"}
  }
}
```

### 缺口

- **neutral_flag 缺失**：世界杯大部分比赛在中立场进行，但 schema 无此字段。需从 `match.venue` 和 `teams.home.country` 推导。
- **venue 坐标在 match card 中为 null**：虽然 `data/static/world_cup_2026_venues.json` 已有完整坐标，但在 match card 构建时未写入。需要在 build 时从静态文件映射。
- **halftime_score**：无数据。api-football 有 halftime 字段，但在当前项目中未使用。
- **extra_time_score/penalty_score**：无数据。对于世界杯淘汰赛阶段需要此字段，当前项目仅覆盖小组赛。

### 结论

**适合进入 FiveDim Lite 第一版：** 基础比赛数据（除 halftime/extra_time/penalty/neutral_flag 外）均可稳定获得。

**降级方案：** 
- `venue_latitude/longitude`：可在 build 时从 `world_cup_2026_venues.json` 映射而非 match card。
- `neutral_flag`：第一版建议标记为 TBD，对于非世界杯赛事可自动从 `teams.home.country != venue.country` 推导。
- `halftime_score`：仅在 Analyst View 中保留，等有完整数据源后再启用。

---

## 3. W1 市场与概率底座

### 字段覆盖表

| 字段 | 可获得 | 来源 | 关键字段 | 缺失率 | 备注 |
|------|--------|------|----------|--------|------|
| 1X2 odds | ✅ | markets.odds_1X2.lines[0] | home/draw/away | 0%（24/24） | 已有 devig |
| AH odds | ✅ | markets.odds_AH.lines[0].entries | line/odds | 0%（24/24） | 多线盘口 |
| OU odds | ✅ | markets.odds_OU.lines[0].entries | line/odds | 0%（24/24） | 多线盘口 |
| bookmaker_id | ❌ | N/A | — | 100% | 只保存 `bookmakers_count` |
| bookmaker_name | ❌ | N/A | — | 100% | 只保存聚合数据 |
| market_id | ❌ | N/A | — | 100% | 仅 `odds_1X2`/`odds_AH`/`odds_OU` 标记 |
| market_name | ✅ 隐含 | 同上 | `"odds_1X2"` 等 | 0% | 类型名 |
| line/handicap | ✅ | entries[].line | 如 `"Home -1"` 解析得 handicap | 0% | 已在 W1 引擎解析 |
| selection_name | ⚠️ 部分 | entries[].line | 如 `"Home"` | 部分 | 盘口引擎解析了 name |
| decimal_odds | ✅ | entries[].odds | 数值 | 0% | 原始值 |
| odds_update_time | ⚠️ 单级 | markets.odds_snapshot_time_utc | 撮级时间戳 | 0% | 非 bookmaker 级 |
| collected_at | ✅ | odds_snapshot_time_utc | W1 本地收集时间 | 0% | ✅ |
| bookmaker_count | ✅ | bookmakers_count | 整数 | 0% | 世界杯平均 14, 个别 12 |
| lambda_home | ✅ | score_matrix 计算 | 从 1X2+OU 反解 | 条件性 | 仅当 odds 完整可用 |
| lambda_away | ✅ | 同上 | 同上 | 条件性 | 同上 |
| score_matrix | ✅ | w1_score_engine | `w1_score_engine.score_matrix()` | 条件性 | ✅ 完整可计算 |
| 1X2_probability | ✅ | 从 score_matrix 派生 | `hda_from_matrix()` | 条件性 | ✅ |
| OU_probability | ✅ | 从 score_matrix 派生 | `derive_ou_from_score_matrix()` | 条件性 | ✅ |
| AH_probability | ✅ | 从 score_matrix 派生 | `derive_ah_from_score_matrix()` | 条件性 | ✅ |
| score_pool | ✅ | 从 score_matrix 派生 | top 8 + 6 paths | 条件性 | ✅ 已有 |
| odds_dispersion | ❌ | 需计算 | — | 100% | 缺少书商级数据 |
| opening_odds | ❌ | W1 政策禁止此命名 | `first_seen_odds_proxy` 替代 | 100% | 不允许叫开市价 |
| current_odds | ✅ | odds_1X2 快照 | — | 0% | 当前快照 |
| line_movement | ✅ | odds_movement_monitor | OU/AH 线变化 | 条件性 | 需要多个快照 |
| odds_movement | ✅ | odds_movement_monitor | odds_movement 模块 | ✅ | 已实现 |
| BTTS_probability | ✅ | 从 score_matrix 派生 | `derive_btts_from_score_matrix()` | 条件性 | ✅ |
| market_consensus_summary | ⚠️ | build_w1_dashboard_data.py | normal_sentence_cn | 条件性 | 已有文本描述 |
| data_quality_flags | ⚠️ | risk_flags + data_gaps | — | 0% | 已有结构 |

### 当前 W1 已有能力

W1 在 odds/概率方面是非常坚实的基础：

1. ✅ **1X2/AH/OU 解析**：`w1_score_engine.py` 中的 `parse_1x2()`、`parse_ah_ladder()`、`parse_ou_ladder()` 已覆盖全部三种盘口
2. ✅ **Score Matrix**：`score_matrix()` 函数已实现 Dixon-Coles 修正的 Poisson 分布
3. ✅ **Score Pool**：`build_score_distribution()` 输出 top 8 + 6 路径
4. ✅ **BTTS**：`derive_btts_from_score_matrix()` 从矩阵派生
5. ✅ **collected_at**：使用 `markets.odds_snapshot_time_utc`
6. ✅ **Odds Movement Monitor**：`build_w1_dashboard_data.py` 中的 `odds_movement_monitor()` 已实现
7. ✅ **Devig**：`devig_proportional()` 和 `devig_two_way()` 已实现
8. ✅ **Market Probability Panel**：已有完整实现，包含 1X2/OU/AH/BTTS/clean_sheet/goal_bands

### 需要新增的计算字段

| 字段 | 是否已有 | 方案 |
|------|---------|------|
| odds_dispersion | ❌ | 需要 bookmaker 级数据，当前只有聚合数据 |
| opening_odds | ❌ | 按 W1 政策，使用 `first_seen_odds_proxy` |
| BTTS_probability | ✅ | 已有，从 score matrix 派生 |
| market_consensus_summary | ⚠️ | 已部分有 normal_sentence_cn，可增强 |
| data_quality_flags | ⚠️ | 已有 risk_flags/data_gaps，可增强标记 |

### odds 时间戳与泄露风险

- **当前状态**：`odds_snapshot_time_utc` 是单个撮级时间戳，不是 bookmaker/market 级
- **泄露风险**：存在赛后赔率泄露风险。当前实现的 `odds_movement_monitor` 使用 `captured_at_utc` 和 `staleness_minutes`，如果赛后 snapshot 仍被当作赛前数据则会引入 hindsight bias
- **防护措施**：已在 `w1_forward_ledger` 中实现 `pre_match_view` 不可变、`lock_as_of ≤ kickoff`、无 hindsight 的写入策略
- **建议**：FiveDim Lite 第一版必须依赖 `forward_ledger` 的赛前快照，不能直接从 match card 读取赛后更新的 odds

### 是否需要 odds changelog

**需要，但非第一版 BLOCKER。**

当前只有单个快照。真正的 odds_movement 需要多时间点的对比。
W1 已实现 `w1_odds_snapshot_collector.py` 和 `odds_movement_monitor`，支持多档位的运动检测。
第一版可以接受基于两个时间点的最小 diff（已实现），但真正可靠的 changelog 需要：
1. 多轮快照采集（T-48h/T-24h/T-12h/T-6h/T-1h/T-30m）
2. bookmaker 级时间戳才能计算准确的 odds_dispersion

**第一版建议**：使用当前快照做 `market_consensus` 和 `bookmaker_count` 计算，`odds_movement` 标记为 `partial/minimal_changelog` 警告。

### 结论

市场与概率底座是 W1 的核心强项，FiveDim Lite 第一版的 **维度四（市场与热度智慧）可以直接重用 W1 的现有基础设施**。

---

## 4. 维度一：绝对实力面

### 字段覆盖表

| 字段 | 可获得 | 来源 | 是否已有 | 缺口 |
|------|--------|------|---------|------|
| 国家队 ELO | ❌ | 需外部源 | schema 字段 `elo_rating` 存在但为 null | 100% null |
| 俱乐部 ELO | ❌ | 需外部源 | N/A | N/A（非俱乐部赛事） |
| ELO 日期 | ❌ | 需外部源 | N/A | N/A |
| FIFA ranking | ❌ | 需外部源 | schema 字段 `fifa_rank` 存在但为 null | 100% null |
| league table position | ⚠️ | 需手动/API | standings 仅静态模板 | 仅世界杯小组赛赛前 |
| points | ⚠️ | 同上 | 同上 | 同上 |
| goal_difference | ⚠️ | 同上 | 同上 | 同上 |
| recent_5_results | ⚠️ | 可自行计算 | 无现成代码 | 需从历史 fixtures 计算 |
| recent_10_results | ⚠️ | 可自行计算 | 无现成代码 | 需从历史 fixtures 计算 |
| recent_5_goals_for | ⚠️ | 可自行计算 | 无现成代码 | 需从历史 fixtures 计算 |
| recent_5_goals_against | ⚠️ | 可自行计算 | 无现成代码 | 需从历史 fixtures 计算 |
| home_form | ⚠️ | 可自行计算 | 无现成代码 | 需区分主客场 |
| away_form | ⚠️ | 可自行计算 | 无现成代码 | 需区分主客场 |
| vs_same_tier_record | ❌ | 复杂 | N/A | 需 tier classification |
| team_market_value | ❌ | 需外部源 | N/A | 需 Transfermarkt 或 API |
| squad_average_age | ❌ | 需外部源 | N/A | 需 API/squad detail |
| core_player_list | ⚠️ | 部分可用 | squad 名单可有 | 数据存在但 player_id 不完整 |
| player_minutes | ❌ | 需历史统计 | N/A | 需要球员级出场数据 |
| player_goals | ❌ | 需历史统计 | N/A | 同上 |
| player_assists | ❌ | 需历史统计 | N/A | 同上 |
| player_position | ⚠️ | 部分可用 | lineup 中 grid_position 可获取 | 仅首发可用，非完整 squad |
| player_rating_last5 | ❌ | 需外部源 | N/A | 高阶场次评分不可获取 |
| salary_structure | ❌ | 需外部源 | N/A | 不可获取 |
| xT | ❌ | 需外部源 | N/A | 高阶 Pro 模型数据 |
| progressive_carries | ❌ | 需外部源 | N/A | 同上 |

### 判断

1. **ELO 是否可稳定获取，国家队和俱乐部是否分开**
   - ❌ ELO 目前不可获取。schema 中有字段 `elo_rating` 但当前所有 match card 中为 null。
   - 国家队 ELO 可从 `eloratings.net` 爬取静态 CSV，俱乐部 ELO 需要独立的俱乐部赛事 ELO 计算或外部 API。
   - **国家队与俱乐部必须分开**，不可混用。

2. **排名/积分是否可稳定获取**
   - FIFA 排名：需要爬取或手动导入。国家队排名每月更新一次，可一次性导入。
   - fivethirtyeight SPI：2025 年已停更，不可用。
   - 联赛积分/排名：五大联赛可通过 api-football 稳定获取，世界杯/国家队赛事则每场前需要手动或 API 获取。

3. **近 5/10 场战绩是否可由 fixtures 自动计算**
   - ⚠️ 理论可行，需要历史比赛数据集
   - 当前 W1 没有完整的各队历史比赛数据。世界杯 2026 有国际赛数据集（`scripts/w1_international_dataset.py`）但不完整
   - **第一版建议**：只计算当前赛季/世界杯赛事内可用 fixtures 的近 n 场战绩，标注样本量

4. **主客场表现是否可按联赛生产**
   - ⚠️ 世界杯大部分中立场，主客场区分意义不大
   - 五大联赛中主客场区分很有价值。但当前 W1 不覆盖五大联赛。
   - 如果 FiveDim 未来扩展到联赛，则需要 W1 同时扩展联赛数据覆盖

5. **player_minutes 是否能用于推导核心球员权重**
   - ❌ 不可获取。需要完整赛季球员出场时间数据。
   - 这属于赛季级数据集，不是赛前单场可获得数据。

6. **team_market_value 是否需要外部源或自建表**
   - 需要外部源（Transfermarkt 或其他估值 API）。
   - 国家队估值更难获取，俱乐部估值相对容易。

### 第一版建议保留字段

| 字段 | 保留原因 | 实现方式 |
|------|---------|----------|
| ELO（国家队） | 核心实力指标 | 自建 ELO 爬取/导入模块 |
| recent_5_results | 近期状态基础 | 从历史 fixtures 自动计算 |
| recent_5_goals_for | 进攻效率 | 同上 |
| recent_5_goals_against | 防守效率 | 同上 |
| venue_coordinates（复用） | 主场优势/海拔 | 已有 venues.json |

### 降级为 Analyst View 的字段

| 字段 | 原因 |
|------|------|
| FIFA ranking | 月度更新，不够灵敏；国家队间差值才能反映实力差距 |
| league table position | 仅联赛有效，国家队赛事需降级 |
| home_form/away_form | 仅联赛或明确主/客区分时才有意义 |
| core_player_list | 需要 player_id 完整性，当前 squad 数据不完整 |
| vs_same_tier_record | 需要多次分类计算，第一版复杂度高 |

### 暂不启用字段

| 字段 | 原因 |
|------|------|
| player_minutes | 赛季级大数据集，单次赛前不可获取 |
| player_goals/assists | 同上 |
| team_market_value | 需要外部源 |
| squad_average_age | 需要完整球员出生日期数据 |
| salary_structure | 机密数据不可获取 |
| xT / progressive_carries | 高阶 Pro 模型数据 |

---

## 5. 维度二：战术高阶指标

### 字段覆盖表

| 字段 | 可获得 | 来源 | 是否已有 | 缺口 |
|------|--------|------|---------|------|
| xG | ❌ 赛前 | 赛后 statistics | 无赛前数据 | 赛后才有 |
| xGA | ❌ 赛前 | 赛后 statistics | 无赛前数据 | 同上 |
| shots_total | ⚠️ 赛后 | 赛后 statistics | 无赛前 | 同上 |
| shots_on_goal | ⚠️ 赛后 | 赛后 statistics | 无赛前 | 同上 |
| ball_possession | ⚠️ 赛后 | 赛后 statistics | 无赛前 | 同上 |
| formation | ✅ | lineups | `formation_home`/`formation_away` | ✅ |
| shots_off_goal | ⚠️ 赛后 | 赛后 statistics | 无赛前 | 同上 |
| shots_inside_box | ⚠️ 赛后 | 赛后 statistics | 无赛前 | 同上 |
| shots_outside_box | ⚠️ 赛后 | 赛后 statistics | 无赛前 | 同上 |
| blocked_shots | ⚠️ 赛后 | 赛后 statistics | 无赛前 | 同上 |
| corner_kicks | ⚠️ 赛后 | 赛后 statistics | 无赛前 | 同上 |
| big_chances | ❌ | 无数据源 | N/A | 需要高级数据 |
| goalkeeper_saves | ⚠️ 赛后 | 赛后 statistics | 无赛前 | 赛后才可获取 |
| goals_prevented | ❌ | N/A | N/A | 需要 PSxG 数据 |
| passes_total | ⚠️ 赛后 | 赛后 statistics | 无赛前 | 同上 |
| passes_accurate | ❌ | N/A | N/A | 同上 |
| pass_accuracy | ❌ | N/A | N/A | 同上 |
| npxG | ❌ | N/A | N/A | 需要 Opta 级数据 |
| PPDA | ❌ | N/A | N/A | 需要 Opta 级数据 |
| pressure_success | ❌ | N/A | N/A | 同上 |
| high_turnovers | ❌ | N/A | N/A | 同上 |
| xT | ❌ | N/A | N/A | 高级 Pro 数据 |
| passing_network | ❌ | N/A | N/A | 需要 Opta 事件数据 |
| progressive_carries | ❌ | N/A | N/A | 需要 Opta 事件数据 |

### xG/statistics 是否可用

**赛前不可用。** api-football 有 statistics endpoint 返回 xG/xGA/shots/possession 等数据，但全部是赛后数据——即本场比赛赛后才填充的统计值。
- 这些 statistics 在 `api-football /fixtures/statistics` 下，需要 fixture_id + 比赛结束后才可获取
- 国际友谊赛部分会有 statistics，但不稳定

### 赛前/赛后使用边界

**严格的赛后边界：**
1. 当前比赛的 xG/statistics 必须是赛后才获取，**绝对不可**混入赛前预测链路
2. 近 5/10 场的历史比赛 statistics（xG 均值）可用，但需要：
   - 有完整历史比赛的数据集
   - 明确标注 `source=historical_rolling_avg` + `is_pre_match_input=true`
   - 参赛双方的历史比赛覆盖必须完整
3. **赛后 statistics 不能用于修改本场的 λ/rho/score_matrix**
4. 本场赛后 xG 只能写入 calibration 复盘

### 可进入第一版字段

| 字段 | 进入方式 | 标注 |
|------|---------|------|
| formation | ✅ 已有稳定 | lineups schema 已有 |
| xG_rolling_avg_last5 | ⚠️ 条件性 | 需要历史数据集 + 明确 pre_match_input 标签 |
| shots_total_rolling_avg | ⚠️ 条件性 | 同上 |

### 降级字段

| 字段 | 原因 |
|------|------|
| ball_possession | 赛后数据，仅历史均值可用 |
| shots_on_goal | 同上 |
| corner_kicks | 同上，且对模型贡献有限 |

### 暂不启用字段

| 字段 | 原因 |
|------|------|
| npxG | 无数据源 |
| PPDA | 无数据源 |
| pressure_success | 无数据源 |
| high_turnovers | 无数据源 |
| xT | 无数据源 |
| passing_network | 无数据源 |
| progressive_carries | 无数据源 |
| goals_prevented / PSxG | 无数据源 |
| big_chances | 无数据源 |
| passes_accurate / pass_accuracy | 无数据源 |

---

## 6. 维度三：阵型化学反应

### 字段覆盖表

| 字段 | 可获得 | 来源 | 是否已有 | 缺失率 |
|------|--------|------|---------|--------|
| confirmed_lineups_available | ✅ | lineups.schema | `confirmed_lineup_available` | 赛前才确认 |
| lineup_update_time | ⚠️ | lineups.lineup_updated_at | 字段存在但非必有 | 赛前才填充 |
| start_xi_player_id | ⚠️ | lineups.home_starting_players | 已含 number 但无独立 player_id | 只有 name 和 number |
| start_xi_player_name | ✅ | lineups.home_starting_xi | 名称列表 | 赛前才填充 |
| start_xi_position | ✅ | lineups.home_starting_players[].position | 可用 | 需 API/手动 |
| formation | ✅ | lineups.formation_home/away | 字符串 | 需确认 |
| start_xi_number | ✅ | home_starting_players[].number | 可用 | ✅ |
| grid_position | ⚠️ | lineups.home_starting_players[].grid | 可用但非必有 | ✅ |
| substitutes | ✅ | lineups.home_substitutes | 名称列表 | ✅ |
| coach_name | ❌ | N/A | 无 schema 字段 | 100% |
| player_club | ❌ | N/A | 无数据 | 100% |
| player_league | ❌ | N/A | 无数据 | 100% |
| same_club_count | ❌ | 依赖于 player_club | N/A | 100% |
| same_league_ratio | ❌ | 依赖于 player_league | N/A | 100% |
| core_axis_integrity | ❌ | 需多个数据源 | N/A | 100% |
| injury_position_impact | ⚠️ | 部分可用 | injuries 存在但限表面 | 需推导 |
| cb_pair_shared_starts | ❌ | 需历史 lineups | N/A | 100% |
| defensive_unit_shared_starts | ❌ | 同上 | N/A | 100% |
| coach_tenure_days | ❌ | 需外部源 | N/A | 100% |
| formation_history | ❌ | 需历史 lineups | N/A | 100% |
| passing_connections | ❌ | 需要 Opta | N/A | 100% |

### lineups 覆盖率

**世界杯赛事：** 
- 当前 24 场 match card 全部标注 `lineup_status: "WAIT (pre-match, T-1h)"`
- 仅 `manual_lineups/1539001.json`（Australia vs Turkey）有 manually verified 首发
- 其余场次依赖 API refresh（通过 predict server 的实时请求）
- **覆盖率取决于赛前刷新机制，非首轮卡片固定数据**

**低级别/热门一级联赛 lineups 缺失率预期：**
- api-football 的国家队和国际赛事 lineup 覆盖率通常较好
- 五大联赛 lineup 覆盖率通常高（80-90%+）
- 热门一级联赛（荷甲/葡超/土超/比甲/巴甲）覆盖率中等（60-75%）
- 更低级别覆盖率急剧下降

### lineup_update_time 是否有明确时间

- 字段 `lineup_updated_at` 在 schema 中存在，但非必需
- 对于 manual override，使用 `lineup_as_of_utc` 或 `lineup_confirmed_utc`
- W1_collected_at（`odds_snapshot_time_utc`）可替代作为时间的下限估计

### player_id 是否稳定

- ❌ 不稳定。当前 `home_starting_players` 中只有 `name`（字符串）和 `number`（号码）
- 没有独立的 `player_id`/`api_football_player_id` 字段
- 这导致：
  - 无法跨场比赛关联同一球员
  - 无法计算 cb_pair_shared_starts
  - 无法从 injuries 和 lineup 做球员身份关联

### player_club / player_league 是否可获取

- ❌ 当前完全不可获取
- api-football 的 squad 和 lineup endpoint 包含 player 的 club 信息，但 W1 当前未解析
- 如果需要 same_club_count/same_league_ratio，需要：
  1. 从 squad API 获取球员完整 profile（含所属俱乐部）
  2. 从 club API 获取俱乐部所属联赛
  3. 这是中等复杂度的工作

### 中卫搭档历史场次是否能从历史 lineups 计算

- ❌ 不能。当前没有：
  - 历史的完整 lineup 数据集
  - 球员唯一 ID 用于跨场关联
  - 需要几轮 lineup 数据积累后才可以

### 第一版是否降级为"阵型 + 首发 + 伤停位置影响"

**建议：是的。**

第一版 FiveDim Lite 的"阵型化学反应"维度限定为：
1. **confirmed_lineup_available** ✅（条件性可用）
2. **formation** ✅（两个球队的阵型字符串）
3. **position 级别伤停影响** ⚠️（基于现有 injuries 做推导）
4. **lineup_updated_at** ⚠️（时间戳）

不可在 FiveDim Lite 第一版假装拥有 `same_club_count`、`same_league_ratio`、`core_axis_integrity`。

---

## 7. 维度四：市场与热度智慧

### 字段覆盖表

| 字段 | 可获得 | 来源 | 是否已有 | 备注 |
|------|--------|------|---------|------|
| 1X2_market_consensus | ✅ | 从 odds devig 后计算 | `devig_proportional()` 后 3 个概率 | ✅ |
| OU_market_consensus | ✅ | 从 OU devig 后计算 | `devig_two_way()` 每线一个概率 | ✅ |
| AH_market_consensus | ✅ | 从 AH entries 计算 | AH ladder 解析 | ✅ |
| bookmaker_count | ✅ | `markets.odds_1X2.bookmakers_count` | ✅ | 世界杯平均 14 |
| odds_update_time | ⚠️ | `odds_snapshot_time_utc` | 单级 | 非 bookmaker 级 |
| market_depth_grade | ⚠️ | 可推算 | book_count + staleness + spread | 需自定义 |
| odds_dispersion_1X2 | ❌ | 需要书商级数据 | N/A | 无 bookmaker 级 odds |
| odds_dispersion_OU | ❌ | 同上 | N/A | 同上 |
| odds_dispersion_AH | ❌ | 同上 | N/A | 同上 |
| line_consistency | ✅ | 可计算 | `ODDS_MOVEMENT_STATUS_PRIORITY` 中 | 从 coherence 字段 |
| opening_line | ❌ | W1 政策禁止 | `first_seen_odds_proxy` | 见政策 |
| current_line | ✅ | 当前 snapshot | 市场当前线位置 | ✅ |
| line_movement | ✅ | odds_movement_monitor | 从多个 snapshot 对比 | ✅ |
| odds_movement | ✅ | 同上 | TV distance + μ drift | ✅ |
| market_volatility | ⚠️ | 可推算 | 从 movement magnitude 与频率 | 需增强 |
| H2H_results | ⚠️ | 自行计算 | 需要历史 H2H 数据集 | 当前 snapshots 标记 "ENDPOINT_READY" |
| same_tier_mapping | ❌ | 复杂 | N/A | 需 tier classification |
| Google Trends | ❌ | 外部 | N/A | 暂不做 |
| news_mentions | ❌ | 外部 | N/A | 暂不做 |
| social_sentiment | ❌ | 外部 | N/A | 暂不做 |
| forum_sentiment | ❌ | 外部 | N/A | 暂不做 |
| betting_volume | ❌ | 外部 | N/A | 暂不做 |

### 市场共识

W1 已能稳定计算：
- 1X2 去水概率（`devig_proportional`）
- OU 去水概率（`devig_two_way` + 插值）
- 从 score matrix 派生的完整概率分布
- **market_consensus_summary 以 normal_sentence_cn 形式存在**

### 市场分歧

- **无法直接计算**，缺少 bookmaker 级明细数据
- 可行的近似方案：
  - 用 `cross_book_spread_home_prob`（已在 `liquidity` 中定义）作为分歧代理
  - 如果 spread ≥ 0.10，标记为 `SOFT_THIN_WIDE_SPREAD`
- 第一版使用 `liquidity.cross_book_spread_home_prob` 作为分歧度量的替代

### 盘口跟踪

- `odds_movement_monitor` 已完整实现：
  - `cumulative_move`：累计赔率变化
  - `recent_move`：近期变化（60 分钟窗口）
  - `phase`：对应 T-48h/T-24h/T-12h/T-6h/T-1h/T-30m
  - `liquidity`：人数、新鲜度、离散度
- **需要 odds changelog**：当前只有 snapshot 之间的对比，缺少时序变化精细化分析

### H2H

- 在 snapshot 中标记为 `"h2h_status": "ENDPOINT_READY"`
- 实际 H2H 数据需要综合多个 fixtures 的计算
- 第一版可简单从历史结果中提取最近 n 次交锋记录

### 热度/舆情是否暂不做

**建议暂不做。**
Google Trends、news_mentions、social_sentiment、forum_sentiment、betting_volume 全部需要外部数据流或爬虫，且：
- 获取成本高
- 信噪比低
- 时效性要求高
- 不符合当前 "不做外部 API 接入" 的阶段限制

### 红线措辞检查

维度四的报告和展示层必须使用：

✅ 允许：
- "市场共识"
- "市场分歧"
- "热度风险"
- "盘口跟踪"
- "市场稳定性"
- "数据处理时间"
- "书商数量"
- "盘口一致性"
- "市场深度等级"

❌ 禁止：
- "诱盘"
- "聪明钱"
- "入场价值"
- "下注"
- "跟机构"
- "稳赚"

**当前 W1 代码已遵守此红线政策。** dashboard 的 `normal_sentence_cn` 和 `disclaimer_cn` 均使用合规表述。

---

## 8. 维度五：外部物理与环境

### 字段覆盖表

| 字段 | 可获得 | 来源 | 是否已有 | 备注 |
|------|--------|------|---------|------|
| previous_match_date_home | ⚠️ | 自行计算 | 无现成 | 需历史 fixtures |
| previous_match_date_away | ⚠️ | 自行计算 | 无现成 | 同上 |
| rest_days_home | ⚠️ | 从上推导 | 可计算 | 需 kickoff 差值 |
| rest_days_away | ⚠️ | 从上推导 | 可计算 | 同上 |
| rest_days_diff | ⚠️ | 从上推导 | 可计算 | 同上 |
| venue_coordinates | ⚠️ | venues.json | 静态但有 | match card 中为 null |
| injuries | ✅ | context.injuries | `status` + `summary` | 存在但仅表面 |
| injury_player_id | ❌ | N/A | 无 | 当前 injuries 只有文本摘要 |
| injury_player_name | ⚠️ | context.injuries.summary | 文本字符串 | 非结构化 |
| injury_reason | ⚠️ | context.injuries.summary | 同上 | 同上 |
| injury_fixture_id | ❌ | N/A | 无 | 非 injury 专属表 |
| league_stage | ✅ | match.round | `"Group Stage - 1"` | ✅ |
| standings | ⚠️ | standings 模板 | 仅静态 | 世界杯赛前全 0 |
| short_rest_flag | ⚠️ | 从 rest_days 推导 | 可计算 | ⚠️ |
| extra_time_previous_match | ❌ | N/A | 无 | 无法获取 |
| travel_distance_home | ❌ | N/A | 无 | schema 有但未填充 |
| travel_distance_away | ❌ | N/A | 无 | 同上 |
| timezone_shift_home | ❌ | N/A | 无 | 不可获取 |
| timezone_shift_away | ❌ | N/A | 无 | 同上 |
| temperature | ✅ | environment_context | `temperature_c` | ⚠️ 依赖天气刷新 |
| precipitation | ✅ | environment_context | `precipitation_mm` | ✅ Open-Meteo |
| wind_speed | ✅ | environment_context | `wind_speed_kmh` | ✅ |
| humidity | ✅ | environment_context | `humidity_pct` | ✅ |
| weather_update_time | ✅ | environment_context | `weather_snapshot_time` | ✅ |
| suspensions | ⚠️ | context.suspensions | 同上 | 表面数据 |
| injury_position | ❌ | N/A | 无 | 需 player 映射 |
| injury_importance | ❌ | N/A | 无 | 需 player_minutes |
| referee_name | ❌ | match.referee.name | null | 当前为 null |
| qualification_scenario | ❌ | N/A | 无 | 未实现 |
| match_importance | ❌ | N/A | 无 | 未实现 |
| referee_yellow_avg | ❌ | N/A | 无 | 需要历史 referee 数据 |
| referee_red_avg | ❌ | N/A | 无 | 同上 |
| referee_penalty_avg | ❌ | N/A | 无 | 同上 |
| locker_room_news | ❌ | N/A | 无 | 暂不建议 |
| yellow_card_suspension_risk | ❌ | N/A | 无 | 需要累计黄牌数据 |

### 休息天数是否能自动计算

**可以自动计算，** 条件如下：
1. 需要有各队的历史比赛日期数据集
2. 从上一场比赛的 kickoff_utc 和当前比赛的 kickoff_utc 相减得到休息天数
3. 对于世界杯小组赛，各队之间通常有完全相同的休息天数（正赛排期确定）
4. 对于五大联赛，不同比赛可能有不同的休息天数差异
5. 对没有历史数据的球队（东道主），需要 fallback 标注

**第一版建议：** 实现 `_compute_rest_days(home_team_history, away_team_history, current_kickoff)` 函数

### 天气是否能通过 Open-Meteo 根据 venue_coordinates 获取

**可以。** 
- 已实现 `w1_weather_client.py`，使用 Open-Meteo 免费 API 查询天气
- 需要 venue 的 latitude/longitude
- 当前 match card 中 venue 坐标不可用（null），但 `world_cup_2026_venues.json` 有完整 16 场坐标
- 需在 build 时从 venues.json 映射坐标并查询天气

### 伤停是否能按 fixture_id 关联

**部分可以。**
- 当前 `context.injuries` 已有 `status` 和 `summary` 字段
- 但没有结构化的 `injury_player_id` 和 `injury_position`
- 无法直接关联到比赛的首发球员

### injury_position 是否能通过 player_id/player_position 推导

**不能。** 因为：
1. 当前 injuries 没有 player_id
2. lineup 和 injuries 之间没有 player_id 关联
3. 只有文本摘要时无法程序化推导位置影响

### injury_importance 是否能由 player_minutes/core_player_weight 推导

**不能。** 因为：
1. 没有 player_minutes 数据
2. 没有 core_player_weight 或 player_rating 数据
3. 需要完整的球员评级系统才能判断重要性

### 裁判字段覆盖率

**当前为 0%。**
- 所有 24 场 match card 的 referee 状态均为 `"available": false, "name": null`
- snapshot 中标记为 `"referee_status": "MISSING (pending FIFA assignment)"`
- 世界杯裁判名单通常在赛前 48-72 小时公布

### standings 是否能用于比赛重要性判断

**部分可以。** 
- 当前 standings 只有赛前模板（全部 0 分）
- 对于联赛和已有比赛结果的赛事，standings 可以反映球队的排位压力
- 对于世界杯小组赛，standings 直到第一轮结束后才有意义

### qualification_scenario 是否第一版需要

**建议第二阶段。** 原因是：
1. 小组赛出线形势复杂（需要多轮比赛后才可计算）
2. 数学上的出线概率计算是独立的模块
3. 第一版只需要基础排位数据即可

### locker_room_news 暂不建议第一版

同意。信息来源不可靠、不可获取、时效性差。

### 可进入第一版字段

| 字段 | 进入方式 | 标注 |
|------|---------|------|
| venue_coordinates | venues.json 映射 | `source=static_venue_db` |
| temperature / humidity / wind / precipitation | Open-Meteo | `source=open_meteo` |
| rest_days（home/away/diff） | 自行计算 | `computed=from_history_fixtures` |
| league_stage | match.round | ✅已有 |
| short_rest_flag | rest_days < 3 天时触发 | `computed` |
| injury_exists | context.injuries.status != "OK" | ⚠️ 仅二值 |
| altitude / roof_status | venues.json | ✅已有 |

### 降级字段

| 字段 | 原因 |
|------|------|
| injuries（结构化） | 当前只有文本摘要，结构化为伤停位置需要外围 API |
| suspensions | 表面数据 |
| referee | 覆盖率 0%，第一版不可用 |
| travel_distance | 无数据 |
| timezone_shift | 无数据，且世界杯横跨美加墨三时区较复杂 |
| standings | 赛前全无数据，仅赛后可用 |
| qualification_scenario | 第二阶段 |

---

## 9. 联赛覆盖差异

### ⚠️ 重要前提

**当前 W1 仅覆盖 2026 年世界杯 24 场小组赛第一轮。**
所有联赛覆盖分析基于项目的国际数据集和 odds extension 成果推断，非实际五大联赛数据验证。

### 世界杯 / 国家队大赛

| 指标 | 当前状态 |
|------|---------|
| fixtures 覆盖率 | 24/24（100%） |
| odds 覆盖率 | 24/24（1X2/AH/OU 均 100%） |
| AH 覆盖率 | 24/24（100%，多线） |
| OU 覆盖率 | 24/24（100%，多线） |
| lineups 覆盖率 | 0/24（100% 为 WAIT，需赛前刷新） |
| injuries 覆盖率 | 24/24（100% endpoint_available，但为空） |
| statistics/xG 覆盖率 | 赛后可用（未获取） |
| referee 覆盖率 | 0%（pending FIFA assignment） |
| venue/coordinates | 16/16 球场有坐标（venues.json） |
| standings 覆盖率 | 24/24（静态模板，赛前全 0） |
| bookmaker 平均数量 | 14 |
| 数据缺失 Top 问题 | 裁判、首发、坐标未写入 card |
| 是否适合长期生产 | ✅ 世界杯赛事非常适合 |
| 是否需要降级 profile | 不需要，世界杯是 W1 主战场 |

### 欧冠

| 指标 | 推断 |
|------|------|
| fixtures 覆盖率 | ⚠️ 可能高（api-football 覆盖 UCL） |
| odds 覆盖率 | ⚠️ 高，与世界杯类似 |
| lineups 覆盖率 | 高（UCL 首发通常稳定公布） |
| injuries 覆盖率 | 中（api-football 有数据） |
| referee 覆盖率 | ⚠️ 高（UEFA 提前 48 小时公布裁判） |
| 是否适合长期生产 | ✅ UCL 数据质量好 |
| 是否需要降级 profile | 不需要 |

### 五大联赛（英超/西甲/意甲/德甲/法甲）

| 指标 | 推断 |
|------|------|
| fixtures 覆盖率 | ✅ 高，api-football 全覆盖 |
| odds 覆盖率 | ✅ 高，书商覆盖齐全 |
| AH 覆盖率 | ✅ 高 |
| OU 覆盖率 | ✅ 高 |
| lineups 覆盖率 | ⚠️ 英超高（90%+），法甲略低（70-80%） |
| injuries 覆盖率 | ⚠️ 中等（各联赛更新频率不同） |
| referee 覆盖率 | ⚠️ 高（五大联赛公布裁判较早） |
| venue/coordinates | ✅ 可获取 |
| standings 覆盖率 | ✅ 高 |
| bookmaker 平均数量 | 五大联赛通常 15-25 家（比世界杯多） |
| 数据缺失 Top 问题 | 部分比赛 lineups 刷新慢、伤病更新滞后 |
| 是否适合长期生产 | ✅ 非常适合 |
| 是否需要降级 profile | 不需要 |

### 热门一级联赛（荷甲/葡超/土超/比甲/巴甲等）

| 指标 | 推断 |
|------|------|
| fixtures 覆盖率 | ✅ 高 |
| odds 覆盖率 | ⚠️ 高但书商数量可能略少（8-15 家） |
| AH 覆盖率 | ⚠️ 中高（部分比赛 AH 线较少） |
| OU 覆盖率 | ⚠️ 中高 |
| lineups 覆盖率 | ⚠️ 中等（土超/比甲 60-75%） |
| injuries 覆盖率 | ⚠️ 中低（部分联赛伤病数据不完整） |
| referee 覆盖率 | ⚠️ 低（部分联赛裁判信息不可用） |
| venue/coordinates | ✅ 可获取 |
| standings 覆盖率 | ✅ 高 |
| bookmaker 平均数量 | 8-12 |
| 数据缺失 Top 问题 | lineups/伤病/裁判质量参差不齐 |
| 是否适合长期生产 | ⚠️ 适合但需降级 profile |
| 是否需要降级 profile | **需要降级 profile，标注 tier B/C** |

### 联赛覆盖结论

| 赛事 | 类型 | 可进入 FiveDim Lite | 降级建议 |
|------|------|-------------------|---------|
| 世界杯 | 国家队大赛 | ✅ 优先 | 使用 FULL profile |
| 欧冠 | 俱乐部大赛 | ✅ | FULL profile |
| 英超 | 顶级联赛 | ✅ | FULL profile |
| 西甲 | 顶级联赛 | ✅ | FULL profile |
| 意甲 | 顶级联赛 | ✅ | FULL profile |
| 德甲 | 顶级联赛 | ✅ | FULL profile |
| 法甲 | 顶级联赛 | ✅ | FULL profile |
| 荷甲 | 一级联赛 | ⚠️ 条件性 | Tier B profile（lineup/referee 降级） |
| 葡超 | 一级联赛 | ⚠️ 条件性 | Tier B profile |
| 土超 | 一级联赛 | ⚠️ 条件性 | Tier B profile |
| 比甲 | 一级联赛 | ⚠️ 条件性 | Tier B/C profile |
| 巴甲 | 一级联赛 | ⚠️ 条件性 | Tier B profile（高海拔球队需单独处理） |

---

## 10. FiveDim Lite 第一版建议字段

### A. 第一版必须保留字段

| 字段名 | 来源 | 用途 | 是否已有 | 缺口 |
|--------|------|------|---------|------|
| fixture_id | match_id | 所有维度关联键 | ✅ | 无 |
| kickoff_utc | match.kickoff_utc | 时间戳 | ✅ | 无 |
| league_name | match.competition | 联赛分类 | ✅ | 无 |
| home_team_name | teams.home.name | 维度一/二/三 | ✅ | 无 |
| away_team_name | teams.away.name | 同上 | ✅ | 无 |
| home_team_id | teams.home.team_id | 关联 | ✅ | 无 |
| away_team_id | teams.away.team_id | 关联 | ✅ | 无 |
| venue_name | match.venue.name | 维度五 | ✅ | 无 |
| venue_latitude/longitude | venues.json 映射 | 维度五 | ⚠️ 需映射 | match card 中 null |
| kickoff_local_time | 计算 | 维度五 | ⚠️ 需计算 | 有时区无数据 |
| 1X2 去水概率 | w1_score_engine | 维度四基础 | ✅ | 无 |
| OU 去水概率 | w1_score_engine | 维度四 | ✅ | 无 |
| AH 去水概率 | w1_score_engine | 维度四 | ✅ | 无 |
| lambda_home/away | w1_score_engine | 模型基础 | ✅ | 条件性 |
| score_matrix | w1_score_engine | 多维概率基础 | ✅ | 条件性 |
| bookmaker_count | markets.*.bookmakers_count | 维度四 | ✅ | 无 |
| formation | lineups.formation_home/away | 维度三 | ⚠️ 需刷新 | 赛前才可用 |
| confirmed_lineup_available | lineups. | 维度三 | ⚠️ 需刷新 | 赛前才可用 |
| temperature_c | environment_context | 维度五 | ✅ 条件性 | 需刷新 |
| precipitation_mm | environment_context | 维度五 | ✅ | ⚠️ 需刷新 |
| wind_speed_kmh | environment_context | 维度五 | ✅ | ⚠️ 需刷新 |
| humidity_pct | environment_context | 维度五 | ✅ | ⚠️ 需刷新 |
| rest_days_home/away | 计算 | 维度五 | ❌ 需实现 | 需历史数据 |
| short_rest_flag | 计算 | 维度五 | ❌ 需实现 | 同上 |
| venue_city/country | match.venue | 维度五 | ✅ | 无 |
| league_stage | match.round | 维度五 | ✅ | 无 |

### B. 第一版建议保留字段

| 字段名 | 来源 | 用途 | 是否已有 | 缺口 |
|--------|------|--------|---------|------|
| recent_5_results | 历史 fixtures | 维度一 | ❌ 需计算 | 需历史数据集 |
| recent_5_goals_for/against | 历史 fixtures | 维度一 | ❌ 需计算 | 同上 |
| ELO（国家队） | 外部源/导入 | 维度一 | ❌ 外部源 | 字段为空 |
| home_starting_xi | lineups | 维度三 | ⚠️ 赛前 | 需刷新 |
| away_starting_xi | lineups | 维度三 | ⚠️ 赛前 | 需刷新 |
| home_starting_players（含 position） | lineups | 维度三 | ⚠️ 赛前 | 需刷新 |
| lineup_updated_at | lineups | 维度三 | ⚠️ 赛前 | 需填充 |
| injury_exists_flag | context.injuries | 维度五 | ⚠️ 二值 | 非结构化 |
| altitude_m | venues.json | 维度五 | ✅ 静态 | 映射到 card |
| roof_status | venues.json | 维度五 | ✅ 静态 | 映射到 card |
| odds_movement_status | odds_movement_monitor | 维度四 | ✅ | 需 changelog 增强 |
| liquidity.cross_book_spread | odds_movement_monitor | 维度四分歧 | ✅ | 可用 |
| BTTS_probability | score_matrix | 维度四 | ✅ | 无 |
| H2H_recent_results | 历史 fixtures | 维度四 | ❌ 需计算 | 需历史数据集 |

### C. 仅 Analyst View 字段

| 字段名 | 原因 |
|--------|------|
| FIFA ranking | 月度更新不灵敏，仅作为赛季级背景参考 |
| league table position | 仅联赛有效；世界杯赛前无用 |
| home_form/away_form | 仅联赛有效；国家队赛事大部分中立 |
| core_player_list | player_id 不完整，无法可靠关联 |
| player_position（全部 squad） | 仅首发可用，无法覆盖换人 |
| venue_lat/lon（未映射前） | 映射后提升为第一版字段 |
| standing（赛前） | 赛前无意义，赛后才有价值 |
| formation_history | 需要多赛季 lineup 数据积累 |

### D. 暂不启用字段

| 字段名 | 原因 |
|--------|------|
| halftime_score | 无数据源，且非赛前因子 |
| extra_time/penalty_score | 无数据源 |
| neutral_flag | 方案明确但需实现 |
| player_minutes | 赛季级大数据集，不可赛前获取 |
| player_goals/assists | 同上 |
| squad_average_age | 缺少球员出生日期 |
| team_market_value | 需外部源 |
| salary_structure | 机密 |
| xG（赛前） | 赛后才能获取 |
| npxG/PPDA/pressure_success | 无数据源 |
| passes_accurate/pass_accuracy | 无数据源 |
| big_chances | 无数据源 |
| goals_prevented / PSxG | 无数据源 |
| xT / passing_network / progressive_carries | 都无数据源 |
| player_club / player_league | 当前不可获取 |
| same_club_count / same_league_ratio | 依赖于 player_club/league |
| core_axis_integrity | 需要多数据源 |
| cb_pair_shared_starts | 需历史 lineup + player_id |
| coach_name | 无 schema |
| coach_tenure_days | 无数据 |
| passing_connections | 需要 Opta 事件 |
| odds_dispersion（1X2/OU/AH） | 缺 bookmaker 级 odds |
| opening_odds | W1 政策禁止此命名 |
| Google Trends | 外部数据，非第一版 |
| news_mentions | 外部，高噪音 |
| social_sentiment | 外部，不可靠 |
| forum_sentiment | 外部，不可靠 |
| betting_volume | 外部，不可获取 |
| extra_time_previous_match | 无可获取路径 |
| travel_distance | 无数据，需计算 |
| timezone_shift | 无数据 |
| qualification_scenario | 第二阶段 |
| referee_name | 当前覆盖率 0% |
| referee stats（yellow/red/penalty） | 依赖于 referee_name |
| locker_room_news | 不可获取 |
| yellow_card_suspension_risk | 需要累计数据 |

### E. 未来增强字段

| 字段名 | 依赖条件 |
|--------|----------|
| ELO 国家队自动计算 | eloratings.net 静态 CSV 导入 + W1 ELO 模块 |
| ELO 俱乐部自动计算 | 外部源或自建 ELO 引擎 |
| player_minutes 赛季分析 | api-football player statistics + squad detail |
| xG 滚动平均 | 历史比赛 statistics 数据集 |
| odds_dispersion | odds_snapshot_collector 多轮采集 + per-bookmaker 数据 |
| odds_changelog | 同上 + 时间序列管理 |
| lineup_history | 多轮 API 刷新 + lineup 数据积累 |
| injury_position | player_id 映射 + 位置数据库 |
| qualification_scenario | standings 累积 + 出线数学模块 |
| PPDA / pressure_success | Opta/StatsBomb 级数据源订阅 |

---

## 11. 风险与 BLOCKER

### BLOCKER

**无。** FiveDim Lite 第一版没有真正的 BLOCKER。

以下都不是 BLOCKER：
- ELO 不可获取：可以用场均进球差替代
- xG 不可赛前获取：第一版暂不启用即可
- 球员数据不可获取：精简阵容维度

### 数据缺失风险

| 风险 | 级别 | 影响 | Mitigation |
|------|------|------|-----------|
| lineups 赛前缺失 | MEDIUM | 维度三无法计算 | 标注 `lineup_status=WAIT` 并跳过 |
| standings 赛前空表 | LOW | 维度五部分缺口 | 赛后自动填充即可 |
| ELO 字段空值 | MEDIUM | 维度一核心数据缺失 | 用 mu_total_goals 降级替代 |
| injuries 只有摘要 | LOW | 伤停影响无法量化 | 标注 `injury_structured=false` |

### 时间戳风险

| 风险 | 级别 | Mitigation |
|------|------|-----------|
| odds_snapshot_time_utc 是单级时间戳 | LOW | 标注 `odds_timestamp_precision=single_snapshot` |
| 赛后 odds 被误用作赛前数据 | MEDIUM | 依赖 forward_ledger 的赛前快照策略 |
| lineup_updated_at 可能缺失 | LOW | 使用 collected_at 作为下限估计 |

### 赛后数据误用风险

| 风险 | 严重性 | 规则 |
|------|--------|------|
| 本场赛后 statistics 被纳入赛前预测 | **HIGH** | 必须禁止 |
| 历史比赛的 statistics 滚动平均 | 低（但需标注） | 允许，须标注 `source=historical_rolling_avg` |
| 赛后 odds 被当作赛前快照 | MEDIUM | 使用 forward_ledger 不可变快照 |

**W1 当前策略：** `forward_ledger` 的 `pre_match_view` 不可变，`lock_as_of ≤ kickoff`，无 hindsight 写入。为 FiveDim Lite 提供了正确的赛前数据隔离。

### 生产稳定性风险

| 风险 | 级别 | 说明 |
|------|------|------|
| 无五大联赛实际数据验证 | MEDIUM | 当前仅世界杯 24 场，需要更多抽样 |
| lineups 刷新依赖赛前 API | MEDIUM | 断网或 API 故障时无效 |
| odds 刷新窗口 | LOW | 聚合数据的更新频率需要明确 |
| 联赛降级 profile 方案未实现 | MEDIUM | 荷甲/葡超需要 Tier B 配置 |

### 红线风险

| 风险 | 级别 | 说明 |
|------|------|------|
| "诱盘" 表述 | ❌ 禁止 | 当前代码无此表述 |
| "聪明钱" 表述 | ❌ 禁止 | 当前代码无此表述 |
| "跟机构走" | ❌ 禁止 | 当前代码无此表述 |
| "入场价值" | ❌ 禁止 | 当前代码无此表述 |
| "投注建议" | ❌ 禁止 | 已使用 "non_final_disclaimer_cn" |
| "命中率承诺" | ❌ 禁止 | 已有 RPS/log loss 非承诺性评估 |
| "竞彩推荐" | ❌ 禁止 | 当前代码无此表述 |

**红线风险状态：安全。** 当前 W1 代码没有高风险表述。

---

## 12. 建议落地路线

### 阶段 A：只读 FiveDim Lite 数据层

**优先级：最高**

- 创建 `w1_fivedim_lite.py`，只读读取 W1 现有数据
- 不修改任何引擎、build 函数或 dashboard
- 输出一个五维标准化 JSON，每个因子标注 `basis=market_implied_score_matrix` 和 `independent_edge=false`
- 维度四直接重用 W1 的 market_probability_panel 数据
- 维度五重用 W1 的 environment_context 和 venues 数据
- 维度一/二/三标记为"部分可用"，对缺失字段标注 `missing_reason`
- 所有输出含 disclaimer：非独立因子评估层，不构成独立优势判断

### 阶段 B：Director View 展示

**优先级：中**

- 在 Director View 中展示五维数据摘要（以非投注表达方式）
- 五维的条形雷达图（棒球卡风格），每个维度的评分为 0-10
- 每个维度显示几条关键数据引用
- 不输出"五维总分"或"五维推荐"

### 阶段 C：历史样本验证

**优先级：中**

- 对 2018/2022 世界杯 + 近几赛季五大联赛，回算五维各维度与赛果的关联性
- 不是为了"找最佳权重"，而是验证现有数据定义的合理性
- 输出 RPS/log loss 对比：用五维信息 vs 只用 W1 基线

### 阶段 D：允许部分因子进入 confidence_adjustment

**优先级：低**

- 仅经过阶段 C 验证通过、且不引入事后 bias 的因子
- 每个因子需要单独的低影响度测试
- 不允许大权重调整

### 阶段 E：验证后再考虑进入 λ 或 selector

**优先级：极低**

- 需要大量的历史验证和独立优势证明
- 当前五维因子大部分只是 W1 市场底座的再表达，**不是独立因子**
- 在不存在真正独立优势的情况下，不应进入 λ（反解参数）或 selector

---

## 13. 最终结论

### 是否支持 FiveDim Lite 第一版落地

**✅ 支持，但有条件：**

1. **维度四（市场与热度智慧）完全可用**，W1 已有充足的 odds 基础、市场共识计算、盘口跟踪和 H2H 数据准备
2. **维度五（外部物理与环境）基本可用**，天气 Open-Meteo + coordinates + rest_days 可覆盖大部分
3. **维度一（绝对实力面）部分可用**，ELO/FIFA 排名缺口大，但可降级使用近期战绩和 lambda
4. **维度二（战术高阶指标）仅使用 formation**，xG 等赛后数据不可作为赛前输入
5. **维度三（阵型化学反应）仅使用 lineup + formation + 伤停**，player_club/league 等高级字段不可用

### 建议先做什么

1. 编写 `w1_fivedim_lite.py`（只读数据代理层）
2. 从 venues.json 映射 venue 坐标到 match card
3. 实现 rest_days 计算函数
4. 编写近期战绩自动计算函数
5. 将 ELO/FIFA Rank 字段的缺口明确标注 `missing_reason="需外部源"` 和 `fallback="mu_total_goals"`

### 不建议先做什么

1. ❌ 不要编写独立 ELO 计算模块
2. ❌ 不要引入 xG 赛前滚动平均（覆盖率不足）
3. ❌ 不要实现 player_club/player_league 查询
4. ❌ 不要做五维排名或评级的 dashboard 展示（阶段 B 的内容）
5. ❌ 不要修改 w1_score_engine、DEFAULT_RHO、decision_policy
6. ❌ 不要调用外部 API（阶段 C 在做回测前不需要 API）
7. ❌ 不要承诺"独立优势"或"超越市场"的结论

---

## 附录 A：数据源与依赖

| 依赖 | 类型 | 当前状态 |
|------|------|---------|
| api-football fixture detail | API | 已有集成（不在此阶段调用） |
| api-football odds | API | 同上 |
| api-football lineup | API | 同上 |
| api-football injuries | API | 同上 |
| api-football H2H | API | 同上 |
| Open-Meteo weather | API（免费） | 已集成 w1_weather_client.py |
| venues 静态坐标 | 静态数据 | `data/static/world_cup_2026_venues.json` |
| 历史比赛结果 | 静态/CSV | `data/historical/` |
| FIFA 排名 | 需爬取/导入 | ❌ 未实现 |
| ELO 排名 | 需爬取/导入 | ❌ 未实现 |

## 附录 B：文件依赖图

```
w1_score_engine.py                    ← 概率计算核心
    ↓
build_w1_dashboard_data.py            ← 整合所有数据
    ↓
w1_dashboard_data.json               ← 赛前数据底座
    ↓
w1_fivedim_lite.py [NEW]             ← 只读五维代理层
    ↓
FiveDim Lite 输出 JSON               ← 评估数据包
```

**关键原则：w1_fivedim_lite.py 只能读取，不能修改。**

## 附录 C：红线检查结果

检查 `reports/`、`scripts/`、`config/`、`docs/` 中的表述：

- "投注": ❌ 不存在（仅用于 disclaimer 否定句）
- "下注": ❌ 不存在
- "稳赚": ❌ 不存在
- "诱盘": ❌ 不存在
- "聪明钱": ❌ 不存在
- "入场价值": ❌ 不存在
- "跟机构": ❌ 不存在
- "命中率": ❌ 不存在（注意 `W1_RECOMMENDATION_ACCURACY_AUDIT.md` 中使用了 "命中率" 作为评估指标，但该文件的上下文是"非承诺性的校准评估"）
- "betting": ❌ 不存在
- "资金管理": ❌ 不存在
- "不构成投注建议": ✅ 出现在关键文件中

**发现一个 WARN_ONLY**：`W1_RECOMMENDATION_ACCURACY_AUDIT.md` 的 `hit_type` 术语（`main_hit/pool_hit/miss`）在 V2 版已标注为 `deprecated_hit_type_warning`。这些术语虽然不违法红线策略，但建议在本阶段报告中列为降级术语。

---

*本报告基于 W1 项目代码静态分析生成，不涉及外部 API 调用。所有推断未在实际五大联赛数据上验证。本报告不构成投注建议，不承诺命中率。所有结论仅供研究参考。*
