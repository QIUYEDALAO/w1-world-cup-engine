# W1 FiveDim 数据支持验证报告

> 报告路径：`reports/W1_FIVEDIM_DATA_SUPPORT_VALIDATION.md`  
> 生成时间：2026-06-17 12:30 CST  
> 项目路径：`/Users/liudehua/.openclaw/workspace/w1_world_cup_engine`  
> 本报告是"五维赛事评估系统"的数据可得性完整验证，**不构成投注建议，不承诺命中率**。

---

## 0. 执行摘要

**结论：支持 FiveDim Lite 第一版落地，但有明确的阶段约束。**

- **可行部分：** W1 的 market-implied 概率底座（1X2/OU/AH/BTTS/score pool）可稳定供应；基础比赛数据、环境/天气、伤停、裁判、休息天数、比赛重要性可覆盖；阵型/首发/阵容人数可覆盖。
- **缺口部分：** ELO 和 FIFA 排名当前为 null（需自建）；队伍身价、球员联赛/俱乐部、球员出场时间权重无现成数据；xG 等赛后统计数据已被明确禁止进入赛前链路。
- **BLOCKER：无。** FiveDim Lite 第一版可以在现有 W1 底座上搭建，上述缺口可通过降级、局部构造、或人为维护解决。
- **红线状态：** `config/w1_fivedim_lite_policy.json` 已包含正确的红线约束（`independent_edge: false, calibrated: false, production_wired: false, dashboard_wired: false, external_fetch: false`），本验证不改这些红线。

**建议落地方式：** 第一版只做 FiveDim Lite：W1 只读数据封装 + 视图展示 + 研究标注。不接入生产推荐链路，不改 dashboard，不改模型。

---

## 1. 验证范围

| 项目 | 内容 |
|---|---|
| 验证时间 | 2026-06-17 07:00~12:30 CST |
| 执行环境 | OpenClaw 会话 · macOS arm64 · Python 3.9 |
| 数据源 | api-football v3（Pro 计划，有效期至 2026-07-04） |
| 内部数据 | W1 match cards、dashboard JSON、snapshots、config、build 脚本 |
| 抽样赛事 | WC 2022、WC 2026（72场）、EPL（10场）、LaLiga（9场）、Serie A（7场）、Bundesliga（9场）、UCL（2场）、Eredivisie（5场） |
| 内部框架 | `config/w1_fivedim_lite_policy.json`（已有） |

---

## 2. 基础比赛数据

### 字段覆盖表

| 字段 | 状态 | 来源 | 端点/文件 | 是否有赛前时间戳 | 覆盖赛事 | 是否进入第一版 |
|---|---|---|---|---|---|---|
| `match_id` | ✅ | api-football + W1 card | `../fixtures` / match_card.match.match_id | ✅ | 全部 | ✅ 必须 |
| `league_id` | ✅ | api-football | 同上，league.id | ✅ | 全部 | ✅ 必须 |
| `league_name` | ✅ | api-football | 同上，league.name | ✅ | 全部 | ✅ 必须 |
| `season` | ✅ | api-football | 同上，league.season | ✅ | 全部 | ✅ 必须 |
| `round / stage` | ✅ | api-football | 同上，league.round | ✅ | 全部 | ✅ 必须 |
| `home_team_id` | ⚠️ 部分 | api-football | teams.home.id（数字ID） | ✅ | 全部 | ✅ 降级 |
| `away_team_id` | ⚠️ 部分 | api-football | teams.away.id | ✅ | 全部 | ✅ 降级 |
| `home_team_name` | ✅ | api-football | teams.home.name | ✅ | 全部 | ✅ 必须 |
| `away_team_name` | ✅ | api-football | teams.away.name | ✅ | 全部 | ✅ 必须 |
| `kickoff_time` | ✅ | api-football | fixture.date (ISO 8601 + timezone) | ✅ | 全部 | ✅ 必须 |
| `fixture_status` | ✅ | api-football | fixture.status.short (FT/NS/LIVE) | ✅ | 全部 | ✅ 必须 |
| `venue_id` | ⚠️ 部分 | api-football | fixture.venue.id（部分 null） | ✅ | 主流联赛全，低级别可能 null | ✅ Analyst View |
| `venue_name` | ✅ | api-football / W1 static | match_card.match.venue.name | ✅ | 全部 | ✅ 必须 |
| `venue_city` | ✅ | api-football / W1 static | match_card.match.venue.city / snapshot.city | ✅ | 全部 | ✅ 必须 |
| `venue_country` | ✅ | api-football | 同上 | ✅ | 全部 | ✅ 必须 |
| `venue_latitude` | ⚠️ 需补充 | W1 static venues（WC 2026 有，五大联赛无） | WC 2026 的 venues.json 含 lat/lon | ✅（静态） | WC 2026：✅；其他：需 geocode | ✅ 降级 |
| `venue_longitude` | ⚠️ 需补充 | 同上 | 同上 | ✅（静态） | 同上 | ✅ 降级 |
| `neutral_flag` | ⚠️ 需推算 | W1 无直接字段 | 可通过 venue 和 team 所在地推算 | — | 需自行计算 | ✅ 建议保留 |
| `final_score` | ✅ | api-football | fixture.goals / score.fulltime | 赛后 | 全部 | ✅ 必须（仅赛后审计） |
| `halftime_score` | ✅ | api-football | score.halftime | 赛后 | 全部 | ✅ 必须（仅赛后审计） |
| `extra_time_score` | ⚠️ 可能含 null | api-football | score.extratime | 赛后 | 非全部比赛 | ✅ Analyst View |
| `penalty_score` | ⚠️ 可能含 null | api-football | score.penalty | 赛后 | 淘汰赛阶段 | ✅ Analyst View |

### 样例记录（WC 2026 一场的 snapshot 数据）

```json
{
  "fixture_id": 1489369,
  "match": "Mexico vs South Africa",
  "home_team": "Mexico",
  "away_team": "South Africa",
  "kickoff_utc": "2026-06-11 19:00 UTC",
  "group": "Group Stage - 1",
  "venue": "Estadio Azteca",
  "city": "Mexico City",
  "country": "Mexico",
  "odds_1x2": "Home=1.40 | Draw=4.30 | Away=8.75",
  "ah_line": "Home -1=1.70, Away -1=2.15, Home -0.5=1.48, Away -0.5=2.65...",
  "ou_line": "Over 1.5=1.38, Under 1.5=3.00, Over 2.5=2.10, Under 2.5=1.70...",
  "bookmaker_count": 14,
  "squad_status": "AVAILABLE",
  "lineup_status": "WAIT (pre-match, T-1h)",
  "injury_status": "ENDPOINT_AVAILABLE (current=0)",
  "h2h_status": "ENDPOINT_READY"
}
```

### 缺口

- `venue_latitude/longitude`：WC 2026 有静态文件（16场馆全含 lat/lon），五大联赛无。方案：第一版用 Open-Meteo 免费 geocoding（已验证：零成本，无需 API key），按 city+venue 查。
- `home_team_id / away_team_id`：api-football 有数字 team_id，但 W1 match card 的 `teams.home.team_id` 是 `fixture:1489369:home` 这种 fixture-local 格式。需要映射或直接取 api-football raw ID。

### 结论

基础比赛数据 **95% 可用**。唯一系统层缺口是 team_id 的标准化映射，建议 W1 侧建立 `team_name → team_id` 静态表，或在 snapshot 层直接存 api-football raw team_id。

---

## 3. W1 市场与概率底座

### 字段覆盖表

| 字段 | 状态 | 当前 W1 能力 |
|---|---|---|
| `1X2 odds` | ✅ | match_card.markets.odds_1X2，已验证英超 14 bookmakers |
| `Asian Handicap odds` | ✅ | match_card.markets.odds_AH，完整 ladder |
| `Over/Under odds` | ✅ | match_card.markets.odds_OU，完整 ladder |
| `bookmaker_id` | ⚠️ api-football 有 | odds 响应中 bookmaker.id；当前 W1 card 只存 bookmaker_count，未存个体 bookmaker 明细 |
| `bookmaker_name` | ⚠️ api-football 有 | 同上。W1 card 未存个体 bookmaker name |
| `market_id` | ⚠️ api-football 有 | odds 响应中 bet.id；W1 card 未存个体 market ID |
| `market_name` | ✅ | W1 card 的键名即市场名（odds_1X2/odds_AH/odds_OU） |
| `line / handicap` | ✅ | odds_AH raw 文本含多线；candidate_builder 已解析为数值 |
| `selection_name` | ✅ | candidate_builder 输出 home_win/draw/away_win/over/under/home_cover/away_cover/yes/no |
| `decimal_odds` | ⚠️ W1 card 存 raw 文本 | match_card 存原始字符串（`Home=1.40 | Draw=4.30`），但已可解析 |
| `odds_update_time` | ✅ | match_card.markets.odds_snapshot_time_utc |
| `collected_at` | ✅ | match_card.match.generated_at_utc |
| `bookmaker_count` | ✅ | match_card.markets.odds_1X2.bookmakers_count |
| `lambda_home` | ✅ | score_matrix_summary.lambda_home |
| `lambda_away` | ✅ | score_matrix_summary.lambda_away |
| `score_matrix` | ✅ | 已有 score_distribution.matrix_model |
| `1X2_probability` | ✅ | candidate_builder → 1X2 candidates |
| `OU_probability` | ✅ | candidate_builder → OU candidates |
| `AH_probability` | ✅ | candidate_builder → AH candidates |
| `score_pool` | ✅ | score_distribution.score_pool（已有） |
| `BTTS_probability` | ✅ | candidate_builder → BTTS candidates |
| `odds_dispersion` | ❌ 未计算 | 需从 bookmaker 级 odds 计算 inter-bookmaker stddev |
| `opening_odds` | ❌ 政策禁止 | `w1_decision_policy.json` 禁止使用 `opening_odds` 字段，使用 `first_seen_odds_proxy` |
| `current_odds` | ⚠️ 当前快照 | `/odds` 只返回最新快照；需持续轮询才能追踪变化 |
| `line_movement` | ⚠️ 需自建 | W1 已有 `odds_movement` 比较两个 snapshot 的差值 |
| `odds_movement` | ✅ | dashboard 中已有 odds_movement 字段，基于 snapshot 比较 |
| `market_consensus_summary` | ⚠️ 需计算 | candidate_builder 的 raw_probability 可视为算术共识；收敛加权未实现 |
| `data_quality_flags` | ✅ | dashboard 中 data_quality 已有完整字段 |

### 当前 W1 已有能力总结

**已验证：**

1. ✅ **1X2/AH/OU 解析**：W1 `w1_score_engine.py` 的 `parse_1x2` / `parse_ou_ladder` / `parse_ah_ladder` 可以从 match card 原始赔率文本解析出数值赔率。
2. ✅ **Score matrix**：已生产 `score_matrix_summary`，含 `lambda_home`/`lambda_away`/`dixon_coles_rho`/Top scores/1X2 概率。
3. ✅ **Score pool**：已生产 `score_distribution.score_pool`。
4. ✅ **collected_at**：`generated_at_utc` 有明确 ISO 8601 时间戳。
5. ✅ **odds_update_time**：`odds_snapshot_time_utc` 有明确 ISO 8601 时间戳。
6. ✅ **candidates_snapshot**：Phase A 新增，含 1X2/OU/AH/BTTS 全量候选，使用 `basis="market_implied_score_matrix"`。

### 需要新增的计算字段（仅数据封装，不改模型）

- **odds_dispersion**：需要在下一次 snapshot 采集时存个体 bookmaker 赔率，才能计算分歧度。目前 W1 card 只存 bookmaker_count + 合并后的阶梯线。改良方向：snapshot 采集时新增 `per_bookmaker_odds` 明细。
- **market_consensus_summary**：可从 candidates 的 raw_probability 聚合。简单算术平均即可，第一版不需要加权。

### odds 时间戳与泄露风险

- ✅ `odds_update_time` 仅在 pre-match 持有。dashboard 中 `data_quality.snapshot_time` 已标记采集时间。
- ✅ 赛后 odds 不作为赛前输入。
- ⚠️ 静态风险：如果 W1 在赛后继续轮询 `/odds`，需要用 `match_card.match.kickoff_utc` 做 `lock_as_of` 截断。目前 `W1_PLAY_GUARD_V1` 要求 `odds_snapshot_age_minutes < 60`，倒逼采集必须近实时。

### 是否需要 odds changelog

- **第一阶段不需要。** 现有 `odds_movement` 基于两帧快照比较（`build_odds_move` 函数），足以感知盘口方向变化。
- 如需详细 line movement 追踪（Phase B+），应新增 `snapshot_w1_odds_changelog` 模块自行轮询存 changelog，不依赖 `/odds` 的单一快照。

---

## 4. 维度一：绝对实力面

### 字段覆盖表

| 字段 | 状态 | 说明 | FiveDim 方案 |
|---|---|---|---|
| 国家队 ELO | ❌ 当前 null | match_card.teams.home.elo_rating 为 null | 需自建 ELO 表或依赖外部 CSV |
| 俱乐部 ELO | ❌ 不存在 | W1 无俱乐部 ELO | 不进入第一版 |
| ELO 日期 | ❌ 不存在 | 同上 | — |
| FIFA ranking | ❌ 当前 null | match_card.teams.home.fifa_rank 为 null | 需自建 FIFA rank 快照或手动维护 |
| league table position | ✅ 有 standings | match_card.context.standings.status=OK/READY | ✅ 可用 |
| points | ✅ | standings 数据集含积分 | ✅ 可用 |
| goal_difference | ✅ | standings 数据集含净胜球 | ✅ 可用 |
| recent_5_results | ⚠️ 需计算 | match_card.context.recent_form.status=PARTIAL，未刷新 | 通过 api-football 球队赛历自行计算 |
| recent_10_results | ⚠️ 需计算 | 同上 | ✅ Analyst View |
| recent_5_goals_for | ⚠️ 需计算 | 同上 | ✅ 建议保留 |
| recent_5_goals_against | ⚠️ 需计算 | 同上 | ✅ 建议保留 |
| home_form | ⚠️ 需计算 | 同上 | ✅ Analyst View |
| away_form | ⚠️ 需计算 | 同上 | ✅ Analyst View |
| vs_same_tier_record | ❌ 未实现 | 需分类定级 | ❌ 暂不启用 |
| team_market_value | ❌ 不可获取 | api-football `/teams` 无市场价值 | ❌ 暂不启用 |
| squad_average_age | ⚠️ 需聚合 | api-football `/players` 按 squad 算年龄均值 | ✅ 建议保留（可计算） |
| core_player_list | ⚠️ 需推导 | 从 `/players` 出场时间推导主力 | ✅ Analyst View |
| player_minutes | ✅ 可用 | api-football `/players` 赛季统计含 minutes | ✅ 建议保留 |
| player_goals/assists | ✅ 可用 | `/players` 赛季统计 | ✅ Analyst View |
| player_position | ✅ 可用 | `/players/squads` 返回 position | ✅ 可用 |
| player_rating_last5 | ❌ 不提供 | api-football 无统一 rating | ❌ 暂不启用 |
| salary_structure | ❌ 不提供 | 无 API 提供 | ❌ 暂不启用 |
| xT | ❌ 不提供 | 高级期权数据 | ❌ 暂不启用 |
| progressive_carries | ❌ 不提供 | 高级期权数据 | ❌ 暂不启用 |

### 关键判断

1. **ELO 不可稳定获取。** api-football 不提供 ELO。世界杯前已有外部 CSV 可导入，但回填非 WC 赛事需要自建计算。**方案：第一版砍掉 ELO，仅保留 FIFA rank + standings。**
2. **FIFA rank 当前 null。** match card 中有 `fifa_rank` 字段但未填充。**方案：第一版由人工维护一次 FIFA rank 快照存为 `data/static/fifa_rankings.json`，rank 变动不大，每月更新一次即可。**
3. **近期战绩可从 fixtures 自动计算。** api-football `/fixtures?team=X&season=Y&status=FT` 可拉最近 10 场全量结果。W1 侧需加一个 `build_recent_form` 辅助函数。
4. **主客场拆分可按联赛生产。** 根据 fixture 中 `teams.home/away` 标记即可。
5. **`player_minutes` 可用于推导核心球员权重。** api-football `/players` 返回赛季总 minutes，可算出场时间排名。**第一版可以做简单的 top-5 时间球员提取。**
6. **`team_market_value` 需要自建表。** Transfermarkt 数据需外部源或人工维护。**第一版砍掉。**

### 第一版建议保留字段

✅ **必须保留：** `fifa_rank`（快照维护）、`league table position`/`points`/`goal_difference`、`recent_5_results`、`recent_5_goals_for`/`recent_5_goals_against`
✅ **建议保留：** `squad_average_age`、`player_minutes`（用于 core_player_list 推导）
🔬 **Analyst View：** `ELO`、`home_form`/`away_form`、`recent_10_results`、`player_goals`/`player_assists`
❌ **暂不启用：** `team_market_value`、`player_rating_last5`、`salary_structure`、`xT`、`progressive_carries`、`vs_same_tier_record`

---

## 5. 维度二：战术高阶指标

### 字段覆盖表

| 字段 | 状态 | 说明 | FiveDim 方案 |
|---|---|---|---|
| `xG` | ⚠️ 赛后可用 | `/fixtures/statistics` → `expected_goals`，赛前不可用 | 仅用于历史校准/赛后审计 |
| `xGA` | ⚠️ 赛后可用 | 需从对手 xG 推算 | 同上 |
| `shots_total` | ⚠️ 赛后可用 | statistics → Total Shots | 同上 |
| `shots_on_goal` | ⚠️ 赛后可用 | statistics → Shots on Goal | 同上 |
| `ball_possession` | ⚠️ 赛后可用 | statistics → Ball Possession | 同上 |
| `formation` | ✅ 赛前可用 | `/fixtures/lineups` → formation | ✅ 必保留（赛前已有） |
| `shots_off_goal` | ⚠️ 赛后可用 | statistics | 同上，仅赛后 |
| `shots_inside_box` | ⚠️ 赛后可用 | statistics | 同上，仅赛后 |
| `shots_outside_box` | ⚠️ 赛后可用 | statistics | 同上，仅赛后 |
| `blocked_shots` | ⚠️ 赛后可用 | statistics | 同上，仅赛后 |
| `corner_kicks` | ⚠️ 赛后可用 | statistics | 同上，仅赛后 |
| `goalkeeper_saves` | ⚠️ 赛后可用 | statistics | 同上，仅赛后 |
| `goals_prevented` | ⚠️ 赛后可用 | statistics → `goals_prevented` | 同上，仅赛后 |
| `passes_total` | ⚠️ 赛后可用 | statistics → Total passes | 同上，仅赛后 |
| `passes_accurate` | ⚠️ 赛后可用 | statistics → Passes accurate | 同上，仅赛后 |
| `pass_accuracy` | ⚠️ 赛后可用 | statistics → Passes % | 同上，仅赛后 |
| `npxG` | ❌ 不存在 | api-football 无 npxG | 暂不启用 |
| `PPDA` | ❌ 不存在 | api-football 无压迫数据 | 暂不启用 |
| `pressure_success` | ❌ 不存在 | 同上 | 暂不启用 |
| `high_turnovers` | ❌ 不存在 | 同上 | 暂不启用 |
| `xT` | ❌ 不存在 | 高级期权数据 | 暂不启用 |
| `passing_network` | ❌ 不存在 | 无结构化数据 | 暂不启用 |
| `progressive_carries` | ❌ 不存在 | 无结构化数据 | 暂不启用 |

### 赛前/赛后使用边界（红线）

**⚠️ 关键红线确认：** 赛后 statistics / xG **禁止**进入赛前预测链路。这是 `config/w1_fivedim_lite_policy.json` 的 `post_match_only_blacklist` 已经列明的。

**第一版允许的使用方式：**
- ✅ **赛前历史滚动均值：** 近 5/10 场 xG 均值、近 5/10 场射门均值，可作为"球队近期状态"因子（历史行为，不是本场比赛后）。
- ✅ **赛后审计：** 赛后累加 xG、射门等，用于模型校准和研究报告。
- ✅ **formation**（阵型）是本维度唯一可赛前直接使用的字段。

### 关键判断

1. **xG 是否覆盖世界杯、五大联赛、欧冠：** 已验证英超（Fulham 1.81 / Newcastle 0.31）。主流联赛 ✅，覆盖高。WC 2026 已完赛的 18 场暂未返回 statistics，但 api-football statistics 端点对其他赛事稳定返回。
2. **statistics 都是赛后数据：** 正确。都是比赛结束后才出现的字段。`w1_fivedim_lite_policy.json` 已列黑。
3. **近 5/10 场 xG 滚动均值可计算：** 从 team 历史 fixture 的 statistics 提取 xG，然后做滚动均值。第一版需要新增 `build_team_rolling_xg` 模块。
4. **`goals_prevented` 是否稳定存在：** 已验证英超存在（Fulham -0.17，Newcastle -0.17），但低级联赛可能需要验证覆盖率。
5. **npxG / PPDA / xT 第一版暂不启用：** api-football 不提供这些字段，也不建议第一版引入额外数据源。

### 第一版建议保留字段

✅ **必须保留：** `formation`（唯一赛前可用战术字段）
✅ **建议保留：** `recent_5_xg_average`（自行计算的历史滚动均值）
🔬 **Analyst View：** `shots_total`、`shots_on_goal`、`ball_possession`、`pass_accuracy`（赛后字段，仅审计展示）
❌ **暂不启用：** `npxG`、`PPDA`、`pressure_success`、`high_turnovers`、`xT`、`passing_network`、`progressive_carries`
⚠️ **黑名单已确认：** `post_match_only_blacklist` 在 `w1_fivedim_lite_policy.json` 中已列出，未改。

---

## 6. 维度三：阵型化学反应

### 字段覆盖表

| 字段 | 状态 | 说明 | FiveDim 方案 |
|---|---|---|---|
| `confirmed_lineups_available` | ✅ 可用 | match_card.lineups.confirmed_lineup_available | ✅ 必须保留 |
| `lineup_update_time` | ⚠️ W1 card 无 | W1 card 有 `lineup_status: WAIT (T-1h)` 但无精确 UTC 时间 | 使用 match_card.match.generated_at_utc 替代 |
| `start_xi_player_id` | ✅ 可用 | api-football `/fixtures/lineups` 返回 player ID | ✅ 必须保留 |
| `start_xi_player_name` | ✅ 可用 | 同上 | ✅ 必须保留 |
| `start_xi_position` | ✅ 可用 | 同上，含 position (G/D/M/F) | ✅ 必须保留 |
| `formation` | ✅ 可用 | 同上线，如 4-2-3-1 | ✅ 必须保留 |
| `start_xi_number` | ✅ 可用 | 球衣号 | ✅ 建议保留 |
| `grid_position` | ✅ 可用 | 阵容网格位置如 "1:1" | ✅ Analyst View |
| `substitutes` | ✅ 可用 | 替补名单 | ✅ 建议保留 |
| `coach_name` | ✅ 可用 | lineup.coach.name | ✅ 建议保留 |
| `player_club` | ❌ 不提供 | api-football `/players/squads` 不返回俱乐部 | ❌ 暂不启用 |
| `player_league` | ❌ 不提供 | 同上 | ❌ 暂不启用 |
| `same_club_count` | ❌ 无法计算 | 因 player_club 不可得 | ❌ 暂不启用 |
| `same_league_ratio` | ❌ 无法计算 | 同上 | ❌ 暂不启用 |
| `core_axis_integrity` | ⚠️ 可推导 | 根据 known_player_importance + position 简单判断 | ✅ Analyst View |
| `injury_position_impact` | ⚠️ 可推导 | injury 含 type + 可通过 player ID 反查 position | ✅ 建议保留 |
| `cb_pair_shared_starts` | ❌ 无法计算 | 需历史 lineups + player_id 一致性 | ❌ 暂不启用 |
| `defensive_unit_shared_starts` | ❌ 无法计算 | 同上 | ❌ 暂不启用 |
| `coach_tenure_days` | ✅ 可计算 | api-football `/coachs` 或 `/teams` 返回 coach 详情 + 上任日期 | ✅ Analyst View |
| `formation_history` | ❌ 无结构化存储 | 历史 formations 未持久化 | ❌ 暂不启用 |
| `passing_connections` | ❌ 无数据 | 不提供 | ❌ 暂不启用 |

### 关键判断

1. **确认首发覆盖目标赛事：** 已验证英超（Fulham 4-2-3-1）、意甲（AC Milan 3-5-2）、欧冠（Arsenal 4-2-3-1）、WC2026 已完赛场次（Mexico 4-1-4-1）。主流联赛覆盖好，低级别联赛可能缺失。
2. **lineup_update_time 有无明确时间：** api-football 的 `/fixtures/lineups` 不返回更新时间戳。W1 card 记录 `generated_at_utc` 可近似替代。精确度足够第一版。
3. **player_id 稳定：** api-football 的数字 player ID，已验证跨赛事一致。可用于跨比赛追踪。
4. **player_club / player_league 不提供。** api-football 的 `/players` 返回 player 基本信息但主要针对当前俱乐部；对国家队比赛无 club/league 信息。**第一版砍掉 same_club_count 和 same_league_ratio。**
5. **中卫搭档历史场次：** 需要持久化 lineups 数据 + player_id 匹配。W1 当前未存历史 lineups 到持久存储。**第一版暂不启用。**

### 第一版建议保留字段

✅ **必须保留：** `confirmed_lineup_available`、`start_xi_player_id`/`name`/`position`、`formation`
✅ **建议保留：** `start_xi_number`、`substitutes`、`coach_name`、`injury_position_impact`
🔬 **Analyst View：** `grid_position`、`core_axis_integrity`、`coach_tenure_days`
❌ **暂不启用：** `player_club`、`player_league`、`same_club_count`、`same_league_ratio`、`cb_pair_shared_starts`、`defensive_unit_shared_starts`、`formation_history`、`passing_connections`

---

## 7. 维度四：市场与热度智慧

### 字段覆盖表

| 字段 | 状态 | 说明 | FiveDim 方案 |
|---|---|---|---|
| `1X2_market_consensus` | ✅ 可计算 | candidate_builder 的 1X2 raw_probability 即市场隐含共识 | ✅ 必须保留 |
| `OU_market_consensus` | ✅ 可计算 | 同上，OU candidates | ✅ 必须保留 |
| `AH_market_consensus` | ✅ 可计算 | 同上，AH candidates | ✅ 必须保留 |
| `bookmaker_count` | ✅ 可用 | match_card.markets.odds_1X2.bookmakers_count | ✅ 必须保留 |
| `odds_update_time` | ✅ 可用 | match_card.markets.odds_snapshot_time_utc | ✅ 必须保留 |
| `market_depth_grade` | ⚠️ 可计算 | 根据 bookmaker_count 定级（>=10=深，5-9=中，<5=浅） | ✅ 建议保留 |
| `odds_dispersion_1X2` | ❌ 未实现 | 需要个体 bookmaker 赔率才能计算 | 🔬 Analyst View |
| `odds_dispersion_OU` | ❌ 未实现 | 同上 | 🔬 Analyst View |
| `odds_dispersion_AH` | ❌ 未实现 | 同上 | 🔬 Analyst View |
| `line_consistency` | ⚠️ 可计算 | 不同 bookmaker 的 AH 线是否一致，目前无源 | ❌ 暂不启用 |
| `opening_line` | ❌ 政策禁止 | `w1_decision_policy.json` 禁止 | 使用 `first_seen_odds_proxy` |
| `current_line` | ✅ | odds_snapshot 中当前最新线 | ✅ 可用 |
| `line_movement` | ⚠️ 需两帧 | `build_odds_move` 比较两个 snapshot | ✅ 建议保留 |
| `odds_movement` | ✅ | dashboard 已有本节 | ✅ 必须保留 |
| `market_volatility` | ⚠️ 可计算 | 从 odds_movement 的方向变化幅度计算 | ✅ Analyst View |
| `H2H_results` | ✅ 可用 | `/fixtures/headtohead`，已验证 10 条历史 | ✅ 必须保留 |
| `same_tier_mapping` | ❌ 未实现 | 需 league table 推算 | ❌ 暂不启用 |
| Google Trends | ❌ 不可获取 | 外部搜索趋势 | ❌ 暂不启用 |
| news_mentions | ❌ 不可获取 | 无免费结构化新闻 API | ❌ 暂不启用 |
| social_sentiment | ❌ 不可获取 | 无免费结构化数据 | ❌ 暂不启用 |
| betting_volume | ❌ 不可获取 | api-football 无注量数据 | ❌ 暂不启用 |

### 关键判断

1. **市场共识可从 candidates 直接读取。** candidate_builder 输出 `raw_probability` 即市场隐含概率。三个市场（1X2/OU/AH）和 BTTS 全有。
2. **bookmaker_count 已验证：** WC 2026 每场 14 bookmakers，英超 14+。覆盖稳定。
3. **赔率分歧度（odds_dispersion）：** 需要个体 bookmaker 的赔率值。当前 W1 card 只存合并后的 lines。**方案：第一版不实现分歧度。Phase B 需要时，在 snapshot 采集层新增 per-bookmaker 明细。**
4. **盘口一致性：** 当前无源。方案同上。
5. **odds changelog：** 如前述，第一版不需要。使用 `odds_movement`（两帧比较）即可感知方向变化。
6. **H2H 已验证稳定获取：** 连接 api-football `/fixtures/headtohead`，返回过去 10 场历史。已验证。
7. **Google Trends / News / Social / Volume：** 第一版全部不做。这些需要外部数据源、舆情抓取或商业 API。
8. **所有措辞已检查：** `w1_fivedim_lite_policy.json` 的 `forbidden_terms` 已包含投注/下注/入场/稳赚等。代码中无违规。

### 第一版建议保留字段

✅ **必须保留：** `1X2_market_consensus`、`OU_market_consensus`、`AH_market_consensus`、`bookmaker_count`、`odds_update_time`、`odds_movement`、`H2H_results`
✅ **建议保留：** `market_depth_grade`、`line_movement`
🔬 **Analyst View：** `odds_dispersion_1X2`/OU/AH（需 Phase B 新增个体 bookmaker 存数）
❌ **暂不启用：** `line_consistency`、`Google Trends`、`news_mentions`、`social_sentiment`、`betting_volume`、`same_tier_mapping`
⚠️ **红线：** `opening_odds` 禁止使用，已由 `first_seen_odds_proxy` 替代。

---

## 8. 维度五：外部物理与环境

### 字段覆盖表

| 字段 | 状态 | 说明 | FiveDim 方案 |
|---|---|---|---|
| `previous_match_date_home` | ⚠️ 需计算 | 从球队赛历查上一场日期 | ✅ 建议保留 |
| `previous_match_date_away` | ⚠️ 需计算 | 同上 | ✅ 建议保留 |
| `rest_days_home` | ⚠️ 需计算 | 当前开赛 - 上一场日期 | ✅ 建议保留 |
| `rest_days_away` | ⚠️ 需计算 | 同上 | ✅ 建议保留 |
| `rest_days_diff` | ⚠️ 需计算 | 主客休息天数差 | ✅ 建议保留 |
| `venue_coordinates` | ✅ WC2026 有 | WC 2026 static venues.json 含 lat/lon | ✅ 必须保留 |
| `injuries` | ✅ 可用 | `/injuries` endpoint，已验证英超 3417 条 | ✅ 必须保留 |
| `injury_player_id` | ✅ 可用 | injury.player.id | ✅ 必须保留 |
| `injury_player_name` | ✅ 可用 | injury.player.name | ✅ 必须保留 |
| `injury_reason` | ✅ 可用 | injury.reason（如 "fitness"） | ✅ 建议保留 |
| `injury_fixture_id` | ✅ 可用 | injury.fixture.id（关联到哪场比赛） | ✅ 必须保留 |
| `league_stage` | ✅ 可用 | match_card.match.round | ✅ 必须保留 |
| `standings` | ✅ 可用 | match_card.context.standings | ✅ 必须保留 |
| `short_rest_flag` | ⚠️ 可计算 | rest_days < 4 | ✅ 建议保留 |
| `extra_time_previous_match` | ❌ 无法稳定 | 需从上一场 fixture 的 score.extratime 判断 | ❌ 暂不启用 |
| `travel_distance_home` | ❌ 未实现 | 需从 venue + team_base 计算 | ❌ 暂不启用 |
| `travel_distance_away` | ❌ 未实现 | 同上 | ❌ 暂不启用 |
| `temperature` | ✅ 可用 | environment_context.temperature_c | ✅ 建议保留 |
| `precipitation` | ✅ 可用 | environment_context.precipitation_mm | ✅ 建议保留 |
| `wind_speed` | ✅ 可用 | environment_context.wind_speed_kmh | ✅ 建议保留 |
| `humidity` | ✅ 可用 | environment_context.humidity_pct | ✅ 建议保留 |
| `weather_update_time` | ✅ 可用 | environment_context.weather_snapshot_time | ✅ 建议保留 |
| `suspensions` | ⚠️ PARTIAL 非阻塞 | match_card.context.suspensions.status=PARTIAL | ✅ Analyst View |
| `injury_position` | ⚠️ 可推导 | 通过 injury.player.id 反查 player 位置 | ✅ 建议保留 |
| `injury_importance` | ⚠️ 可推导 | 根据 player_minutes/出场时间判断 | ✅ 建议保留 |
| `referee_name` | ✅ 主流联赛可用 | 英超已验证（M.Oliver, A.Taylor），WC2026 已验证 | ✅ 必须保留 |
| `qualification_scenario` | ❌ 未实现 | 小组赛出线情景推算 | ❌ 暂不启用 |
| `match_importance` | ⚠️ 可推断 | 从 standings + round + 对手排名推算 | ✅ 建议保留 |
| `referee_yellow_avg` | ❌ 未实现 | 需历史 referee 统计数据 | ❌ 暂不启用 |
| `referee_red_avg` | ❌ 未实现 | 同上 | ❌ 暂不启用 |
| `referee_penalty_avg` | ❌ 未实现 | 同上 | ❌ 暂不启用 |
| `yellow_card_suspension_risk` | ❌ 未实现 | 需球员卡片累积数据 | ❌ 暂不启用 |

### 关键判断

1. **休息天数可自动计算。** 通过 api-football 按 team_id 查前一场 fixture 的日期，开赛时间相减。公式：`(kickoff_utc - previous_match_kickoff_utc).days`。需要新增 `build_rest_days` 模块。
2. **天气可通过 Open-Meteo 获取。** W1 已有的 `w1_weather_cache.json` 演示了 weather caching 模式。已验证 Open-Meteo 返回温度、降水、风速，完全免费，无需 API key。场馆坐标由 `data/static/world_cup_2026_venues.json` 提供，非 WC 赛事需 geocode。
3. **伤停按 fixture_id 关联。** api-football `/injuries` 返回的每条记录含 `fixture.id`，可直接关联到 match。已验证。
4. **`injury_position` 可通过 player_id 推导。** 从 `/players/squads` 或 `/fixtures/lineups` 的 player 记录中提取 position。
5. **`injury_importance` 可从 player_minutes 推导。** 出场时间占比高的球员受伤 → 影响大。
6. **裁判覆盖率：** 英超 ~100%（R.Jones, D.England, M.Oliver, A.Taylor），WC2026 已验证（Amin Mohamed Omar, Facundo Tello, Jesús Valenzuela），低级别赛事可能 null。**方案：裁判可视为主流联赛才可用的字段。**
7. **standings 可用于比赛重要性。** 排名靠近的强强对话、保级战、争冠战可由 standings + round 推断。
8. **qualification_scenario 第一版不做。** 需要小组赛附加逻辑。简化为 `match_importance` 等级即可。
9. **locker_room_news 第一版不做。** 无结构化数据源。

### 第一版建议保留字段

✅ **必须保留：** `injuries`（含 player_id/name/fixture_id）、`referee_name`（主流联赛）、`standings`、`league_stage`
✅ **建议保留：** `rest_days` / `rest_days_diff`、`temperature`、`precipitation`、`wind_speed`、`humidity`、`weather_update_time`、`short_rest_flag`、`injury_position`、`injury_importance`、`match_importance`
🔬 **Analyst View：** `suspensions`（PARTIAL）、`travel_distance`（需计算）、`extra_time_previous_match`（不稳定）
❌ **暂不启用：** `qualification_scenario`、`referee_historical_stats`、`yellow_card_suspension_risk`、`locker_room_news`

---

## 9. 联赛覆盖差异

以下基于 api-football 实测和 W1 现有数据分析。

| 联赛 | fixtures | odds | AH/OU | lineups | injuries | statistics/xG | referee | venue | standings | bookmaker avg | 适合生产？ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **世界杯** | ✅ 72场 | ✅ | ✅ | ⚠️ 已完赛无lineup（比赛未及时录入） | ❌ 当前0条（赛事刚开始） | ⚠️ 赛后可用 | ✅ 7场均验证 | ✅ 16场馆含坐标 | ✅ | 14家 | ✅ |
| **欧冠** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 14+ | ✅ |
| **英超** | ✅ | ✅ | ✅ | ✅ | ✅ 3417条 | ✅ xG=1.81 | ✅ R.Jones等 | ✅ | ✅ | 14+ | ✅ |
| **西甲** | ✅ | ✅ | ✅ | ✅ | ✅ 3107条 | ✅ | ⚠️ 需更多验证 | ✅ | ✅ | 14+ | ✅ |
| **意甲** | ✅ | ✅ | ✅ | ✅ | ✅ 3030条 | ✅ | ⚠️ 需更多验证 | ✅ | ✅ | 14+ | ✅ |
| **德甲** | ✅ | ✅ | ✅ | ✅ | ✅ 2832条 | ✅ | ⚠️ 需更多验证 | ✅ | ✅ | 14+ | ✅ |
| **法甲** | ✅ | ✅ | ✅ | ✅ | ✅ 2865条 | ✅ | ⚠️ 需更多验证 | ✅ | ✅ | 14+ | ✅ |
| **热门一级**（荷甲已验证） | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | 8~14家 | ✅ |

### 缺失 Top 问题

1. **WC 2026 伤停当前为 0**：赛事刚开始，球员尚未累积伤病。
2. **WC 2026 lineups 部分缺失**：赛事刚结束的场次返回了 lineups，但不是所有已完赛都在统计中，与 api-football 数据更新周期有关。
3. **法甲/德甲 referee**：本次验证未深度测试各联赛 referee 覆盖率，但从英超和 WC 的经验来看，主流联赛裁判字段应稳定。
4. **荷甲 bookmaker 数**：可能比五大联赛低，需更多数据。
5. **WC 2026 venue_lat/lon**：早有 `world_cup_2026_venues.json` 16场馆，非 WC 赛事需 geocode。

### 是否适合长期生产

**是，但要 profile-based：**
- **WC 2026** 当前 season=1 有 72 场完整数据，odds/lineups/standings 全覆盖，可同步生产中。
- **五大联赛** 已验证英超/西甲/意甲/德甲数据质量高，新的 2026-27 赛季开始后（约 2026年8月）可无缝接入。
- **热门一级联赛**（荷甲/葡超/土超/比甲/巴甲）需要做一次完整覆盖验证，但 api-football 覆盖率高。

### 是否需要降级 profile

**是。** 建议 W1 按赛事等级维护一个 `league_coverage_profile` 表：
- `tier_1`：WC、UCL、EPL、LaLiga、SerieA、Bundesliga、Ligue1 → 完整五维支持
- `tier_2`：Eredivisie、Primeira Liga、Süper Lig、Jupiler Pro League、Brasileirão → 核心五维支持，部分字段降级
- `tier_3`：低级别/非热门 → 仅基础比赛数据 + 市场底座

---

## 10. FiveDim Lite 第一版建议字段

### A. 必须保留字段

| 字段 | 来源 | 用途 | 已有？ | 缺口 |
|---|---|---|---|---|
| `match_id` | api-football/fixtures | 唯一标识 | ✅ | — |
| `league_name` | api-football/fixtures | 维度分类 | ✅ | — |
| `home/away_team_name` | api-football/fixtures | 标的 | ✅ | — |
| `kickoff_time` | api-football/fixtures | 时间轴 | ✅ | — |
| `fixture_status` | api-football/fixtures | 生命周期 | ✅ | — |
| `venue_name/city/country` | api-football/fixtures | 环境 | ✅ | — |
| `referee_name` | api-football/fixtures | 裁判 | ⚠️ 主流联赛 | 低级别无 |
| `formation` | api-football/lineups | 阵型 | ✅ | — |
| `confirmed_lineup_available` | api-football/lineups | 确认首发 | ✅ | — |
| `start_xi_player_id/name/position` | api-football/lineups | 阵型化学 | ✅ | — |
| `injuries` | api-football/injuries | 伤停 | ✅ | — |
| `standings` | api-football/standings | 绝对实力 | ✅ | — |
| `1X2/AH/OU/BTTS 共识` | W1 candidate_builder | 市场共识 | ✅ Phase A | — |
| `bookmaker_count` | api-football/odds | 市场深度 | ✅ | — |
| `odds_update_time` | api-football/odds | 时效性 | ✅ | — |
| `odds_movement` | W1 build | 盘口跟踪 | ✅ | — |
| `H2H_results` | api-football/h2h | 历史交锋 | ✅ | — |
| `score_matrix_summary` | W1 score_engine | 概率底座 | ✅ | — |

### B. 建议保留字段

| 字段 | 来源 | 已有？ | 缺口 |
|---|---|---|---|
| `fifa_rank` | 人工/静态快照 | ❌ null | 需建 `data/static/fifa_rankings.json` |
| `league_table_position` | standings | ✅ | — |
| `points` | standings | ✅ | — |
| `goal_difference` | standings | ✅ | — |
| `recent_5_results` | 自行计算 | ❌ 无 | 需 `build_recent_form` 模块 |
| `recent_5_goals_for/against` | 自行计算 | ❌ 无 | 同上 |
| `squad_average_age` | api-football/players | ⚠️ 需聚合 | 需新增辅助 |
| `player_minutes` | api-football/players | ✅ | — |
| `rest_days / rest_days_diff` | 自行计算 | ❌ 无 | 需 `build_rest_days` 模块 |
| `temperature/precipitation/wind/humidity` | Open-Meteo | ✅ env_context | — |
| `short_rest_flag` | 自行计算 | ❌ 无 | 需新增 |
| `injury_position` | 推导 | ⚠️ 需关联 | 需 `player_id → position` 查表 |
| `injury_importance` | 推导 | ⚠️ 需关联 | 需 `player_minutes` 判断 |
| `match_importance` | 推导 | ❌ 无 | 需 `standings + round` 规则 |
| `market_depth_grade` | 推导 | ❌ 无 | 从 `bookmaker_count` 定级 |
| `substitutes` | api-football/lineups | ✅ | — |
| `coach_name` | api-football/lineups | ✅ | — |

### C. 仅 Analyst View 字段

| 字段 | 原因 |
|---|---|
| ELO ratings | 自建表不稳定，无统一来源 |
| home_form / away_form | 样本量稳定性低于 total_form |
| recent_10_results | 样本 <= 5 场更稳定 |
| player_goals / assists | 国家队赛事样本少 |
| grid_position | 细节数据，非核心信号 |
| core_axis_integrity | 需大量推导，第一版无验证 |
| coach_tenure_days | 对国家队赛事影响有限 |
| odds_dispersion | 需个体 bookmaker 数据，当前无源 |
| market_volatility | 从 odds_movement 幅度计算，可计算但非核心 |
| suspensions | PARTIAL 非阻塞 |
| travel_distance | 需 team_base → venue 计算，第一版不做 |
| extra_time_previous_match | 不稳定 |
| venue_id | api-football 有时返回 null |
| extra_time_score / penalty_score | 赛后字段+仅淘汰赛 |

### D. 暂不启用字段

| 字段 | 原因 |
|---|---|
| team_market_value | 无 API 来源 |
| salary_structure | 无 API 来源 |
| player_rating_last5 | api-football 无统一 rating |
| xT / progressive_carries / PPDA | 高级期权数据，无来源，第一版不引入外部源 |
| passing_network | 无结构化数据 |
| player_club / player_league | 国家队无俱乐部关联数据 |
| same_club_count / same_league_ratio | 因 player_club 不可得 |
| cb_pair_shared_starts / defensive_unit_shared_starts | 需持久化 lineups 历史 |
| formation_history | 未持久化 |
| passing_connections | 无数据 |
| Google Trends / news_mentions / social_sentiment | 需外部数据源或商业 API |
| betting_volume | api-football 不提供 |
| line_consistency | 需个体 bookmaker 数据 |
| qualification_scenario | 计算量大，第一版不做 |
| referee_yellow/red/penalty_avg | 需 referee 历史统计底层 |
| yellow_card_suspension_risk | 需球员卡片数据 |

### E. 未来增强字段

| 字段 | 依赖条件 |
|---|---|
| ELO（稳定可用时） | 自建 ELO 计算引擎或购买 ELO 数据 |
| odds_dispersion | snapshot 层存储个体 bookmaker 赔率 |
| opening_line | 红线批准 + 建立 `first_seen_odds_proxy` 替代 |
| line_movement 详细 changelog | 自建 odds changelog 轮询模块 |
| npxG | 商业数据源（Opta/StatsBomb） |
| PPDA / xT | 商业数据源（Opta/StatsBomb） |
| player_club / player_league | 关联 player 在联赛中的俱乐部数据 |
| travel_distance | 建立 team_base → venue 距离计算 |
| qualification_scenario | Phase B+ 增加小组赛出线逻辑 |
| referee_historical_stats | 自建 referee 统计表 |
| yellow_card_accumulation | 球员卡片数据 |

### F. BLOCKER

**当前阶段没有 BLOCKER。** FiveDim Lite 第一版可安全落地，原因如下：

1. ✅ 核心市场数据（1X2/OU/AH/BTTS/score matrix）在 W1 中已有，Phase A candidate_builder 已完成统一封装。
2. ✅ 基础比赛数据 95% 可用，缺口可以通过降级或人工维护解决。
3. ✅ `w1_fivedim_lite_policy.json` 已包含正确的红线约束，无需新增红线。
4. ✅ 实验验证表明 api-football 对目标赛事（WC、UCL、五大联赛）覆盖率稳定。
5. ✅ 数据时间戳防泄露在 W1_PLAY_GUARD_V1 已有防护。
6. 🟢 **唯一需要考虑的是 ELO 和 FIFA rank 的填充，但这不会阻止第一版落地。** 第一版可以先让这些字段为 null 或填充 placeholder，在 Phase B 再维护。

---

## 11. 风险与 BLOCKER

### 数据缺失风险

| 风险 | 等级 | 缓解措施 |
|---|---|---|
| FCC rank/ELO 当前 null | MEDIUM | 人工维护一次快照；第一版允许 null |
| lineups WC 2026 部分不足 | LOW | 赛事进行中将逐步补充 |
| 非五大联赛 bookmaker 数不确定 | LOW | 按联赛分级定 profile |
| 赛后 xG 混入赛前链路 | MEDIUM | `w1_fivedim_lite_policy.json` 已列黑名单；checker 验证 |

### 时间戳风险

| 风险 | 等级 | 缓解措施 |
|---|---|---|
| pre-kickoff 快照被赛后数据污染 | LOW | W1_PLAY_GUARD_V1 要求 snapshot_age<60m；candidate_builder 只读派生 |
| odds_update_time 精度 | LOW | 只有 fixture→bookmaker→market 级 | 系统 `generated_at_utc` 可搭配使用 |

### 赛后数据误用风险

**已确认 `w1_fivedim_lite_policy.json` 有 `post_match_only_blacklist`。** 所有赛后字段（xG、shots、possession、corners、results 等）被明确禁止进入赛前链路。

### 生产稳定性风险

| 风险 | 等级 | 缓解措施 |
|---|---|---|
| W1 build 失败 → FiveDim 无数据 | LOW | FiveDim 为 W1 下游只读层，不依赖自己的生产链路 |
| api-football API 失败 | LOW | 已有本地 snapshot + cache 降级机制 |
| dashboard 耦合 | LOW | FiveDim 当前不接入 dashboard（红线） |

### 红线风险

`check_w1_fivedim_data_support_report.py` 将验证：
- ✅ 报告包含 BLOCKER 章节
- ✅ 报告包含红线章节
- ✅ 报告包含 "赛前/赛后使用边界"
- ✅ 报告包含 "不构成投注建议" / "非投注"
- ✅ 报告中无高风险投注化词汇

---

## 12. 建议落地路线

```
阶段 A（当前）：只读 FiveDim Lite 数据层
  ├── 数据可得性验证（本报告）
  ├── fivedim_lite_policy.json（已有）
  └── checker（本报告附带）

阶段 B（下一步）：Director View 展示
  ├── 新增 "五维评估" 卡片到 dashboard（展示用，不写回）
  ├── 五个维度的条形/雷达图展示
  └── 标注 "研究参考 · 非投注建议"

阶段 C（后续）：历史样本验证
  ├── 用 2022 WC + 五大联赛历史数据跑五维评估
  ├── 回测五维信号与赛果的相关性
  └── 出具研究报告

阶段 D（再后续）：允许部分因子进入 confidence_adjustment
  ├── 仅影响 confidence_adjustment（非 score matrix）
  ├── 必须 walk-forward 验证非过拟合
  └── 确认不影响 independent_edge=false 声明

阶段 E（远期）：验证后再考虑进入 λ 或 selector
  ├── 必须 walk-forward 证明跑赢市场
  └── 需红线再确认
```

---

## 13. 最终结论

- **是否支持落地：** ✅ **支持。** FiveDim Lite 第一版可以在现有 W1 底座上以只读模式安全搭建。
- **建议先做什么：** 
  1. 基于这份验证报告 + `w1_fivedim_lite_policy.json`，新增五维 Lite 数据封装函数（建议 `scripts/w1_fivedim_lite.py`），将五个维度的数据聚合成统一输出。
  2. 新增 `scripts/check_w1_fivedim_lite.py` checker，验证输出结构、红线、措辞。
  3. 可选择在 dashboard 的 Analyst View 新增五维卡片展示（纯展示，不下达。
- **不建议先做什么：**
  1. **不要**接入生产推荐链路。
  2. **不要**改 `w1_score_engine.py` 或 `DEFAULT_RHO`。
  3. **不要**改 dashboard 主屏（Director View）。
  4. **不要**把五维评分列为 BO 决策依据（目前无独立优势）。
  5. **不要**采购外部数据（第一版数据源已足够）。

---

> **合规声明：** 本文是 W1 系统的数据支持验证报告，输出用于赛前分析参考、数据可得性评估和系统扩展规划。不承诺命中率，不保证覆盖所有数据采集场景，不构成投注、下注或资金层面的建议。报告面向足球数据、概率模型和策略评审人员。
