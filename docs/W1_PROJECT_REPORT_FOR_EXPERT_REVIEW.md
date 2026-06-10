# W1 Project Report for Expert Review

**Project:** W1 World Cup Engine  
**Status:** production-lite  
**Review purpose:** 帮助外部专家快速理解 W1 世界杯赛前分析系统的目标、数据边界、风控规则和当前运行状态。  
**Non-goal:** 本报告不是营销材料，不构成投注建议，不承诺结果。

## 1. 项目背景

W1 是为本届世界杯赛前分析建立的独立系统。项目起点是世界杯赛程临近，长期蓝图无法满足赛前正式分析需求，因此优先落地 production-lite：用已验证的数据源、固定 match card schema、明确的决策标签和本地 ledger 机制，形成可审计、可回放的赛前分析入口。

W1 当前关注的是赛前数据完整性和风控状态，而不是输出预测结论。系统把比赛拆成结构化 match card，每张卡必须包含数据来源、市场快照、阵容状态、风险标记、数据缺口和决策标签。

## 2. 为什么不沿用 V3

W1 不沿用 V3 作为主系统，主要原因是隔离性和世界杯场景差异：

- 世界杯是短周期、高关注度、跨国家队的数据场景，赛前 lineup、裁判、伤停、赛程间隔和场地天气对状态判断更敏感。
- V3 的历史上下文、数据路径和运行习惯不应直接进入 W1，以免引入旧系统假设。
- W1 需要面向每场比赛输出可审计 match card 和 ledger，而不是复用旧流程中的推荐/发布口径。
- 独立仓库、独立 schema、独立 checker 有助于专家审计和赛后复盘。

因此，W1 只把旧资产作为背景经验，不继承旧系统的数据、代码或发布机制。

## 3. W1 系统目标

W1 的目标是建立一个最小但正式的世界杯赛前分析系统：

- 对每场比赛生成结构化 match card。
- 用固定规则判断 `W1_PLAY` / `W1_WATCH` / `W1_WAIT` / `W1_PASS`。
- 把关键风险和数据缺口显式输出。
- 对进入正式赛前动作的卡片要求 ledger 记录。
- 用 watcher 监控实质变化，并避免无意义的快照、ledger 或 git 变更。
- 保持 W1 与旧系统、外部分发和承诺性表达隔离。

## 4. 数据源验证结果

已验证可用于 W1 production-lite 的主要来源如下：

| 数据源 | 验证结果 | 用途 |
|---|---|---|
| api-football | 已验证可用 | fixtures、1X2/AH/OU odds、squads、lineups、injuries、standings、stats、H2H、referee |
| Open-Meteo | 已验证可用 | venue geocoding、weather |
| FIFA rank | 可爬取或维护快照 | 国家队排名背景字段 |
| Elo | 可由国际比赛结果 CSV 本地计算 | 国家队强度背景字段 |
| first_seen_odds_proxy | 可用 | 首次观察到的赔率代理快照 |

当前 production-lite 不依赖不可验证的开盘赔率，也不把任何赔率快照称作 official opening price。

## 5. 数据字段清单

W1 match card 的核心字段包括：

| 模块 | 字段 |
|---|---|
| match | fixture_id、competition、season、round、kickoff_utc、venue、referee |
| teams | home_team、away_team、FIFA rank、Elo rating |
| data_sources | api-football、Open-Meteo、FIFA rank、Elo、local snapshots |
| markets | odds_1X2、odds_AH、odds_OU、odds_snapshot_time、first_seen_odds_proxy |
| squad | home squad status、away squad status、players_count、missing_fields |
| lineups | confirmed_lineup_available、lineup status、starting XI |
| context | standings、recent form、H2H、injuries、suspensions、weather、travel_distance |
| risk | risk_flags |
| gaps | data_gaps |
| decision | label、ledger_required、reasons、no_betting_commitment |

每场比赛必须输出 `risk_flags` 和 `data_gaps`，即使数组为空也必须显式存在。

## 6. 决策标签

| Label | 含义 |
|---|---|
| `W1_PLAY` | 数据完整，风险可接受，允许进入正式赛前观点输出；必须写 ledger |
| `W1_WATCH` | 存在非阻塞风险或观察需求，不进入正式动作 |
| `W1_WAIT` | 关键数据缺失，必须等待刷新 |
| `W1_PASS` | 数据足够但风险、价格或上下文不支持继续 |

当前系统状态下，首轮 24 场全部为 `W1_WAIT`，原因是 confirmed lineup 尚未出现。

## 7. 硬风控规则

W1 production-lite 的硬规则：

- lineup 缺失 => `W1_WAIT`
- odds 1X2 缺失 => `W1_WAIT`
- AH 缺失 => `W1_WAIT`
- OU 缺失 => `W1_WAIT`
- squad 缺失 => `W1_WAIT` 或降级 `W1_WATCH`，必须说明 data gap
- suspensions 为 `PARTIAL` 不阻塞，只加入 risk flag
- travel_distance 为 `PARTIAL` 不阻塞，只加入 risk flag
- `W1_PLAY` 必须 `ledger_required=true`
- `first_seen_odds_proxy` 不能写成 `opening_odds`
- 不输出结果承诺或命中率承诺

## 8. 自动刷新 Watcher

当前 watcher 版本为 v2。

刷新计划：

- 常规刷新：00/06/12/18 CST
- 首场 Mexico vs South Africa：赛前 2h / 1h / 30m 特调

v2 实质变化定义：

- odds_1X2
- odds_AH
- odds_OU
- lineup
- referee
- injury

v2 忽略的非实质变化：

- next_refresh_time
- snapshot filename
- runtime log

watcher v2 使用 `SNAPSHOT_TS` 作为文件名时间源，并要求内部 `snapshot_time` 与同次运行时间对齐。dry-run 模式不调用外部 API。

## 9. 当前运行状态

当前首轮 Group Stage - 1 已生成真实 fixture match cards：

| 项 | 状态 |
|---|---|
| 首轮真实卡 | 24 场已生成 |
| ledger rows | 24 |
| 当前决策分布 | `W1_WAIT=24`, `W1_PLAY=0`, `W1_WATCH=0`, `W1_PASS=0` |
| 首场比赛 | Mexico vs South Africa |
| 首场 fixture_id | 1489369 |
| 首场 kickoff_utc | 2026-06-11T19:00:00Z |
| watcher | v2 READY |

当前 `W1_WAIT=24` 是预期状态：赔率、AH、OU、squad、standings、H2H 已就绪，但 confirmed lineup 尚未出现。

## 10. 数据缺口

当前明确缺口：

- suspensions: `PARTIAL`
- travel_distance: `PARTIAL`
- opening_odds: 不可用；系统只使用 `first_seen_odds_proxy`
- historical WC odds: 不可用
- referee: 当前首轮多场仍未分配或未进入可用状态
- confirmed lineup: 赛前窗口才会出现，是当前 `W1_WAIT` 的核心原因

这些缺口被分为阻塞和非阻塞。confirmed lineup 与核心赔率市场缺失是阻塞项；suspensions 和 travel_distance 当前为非阻塞风险项。

## 11. 系统边界

W1 明确边界：

- 不接 QQ
- 不写 old official/pending
- 不改 V3/V4/M1
- 不承诺命中率
- 不输出保证性结论
- 不把 `first_seen_odds_proxy` 伪装成开盘赔率
- 不在无实质变化时写入 match cards、ledger 或 git

这些边界是系统设计的一部分，不是临时运行约束。

## 12. 后续计划

短期计划：

- confirmed lineup 出现后，刷新对应 match card。
- 满足硬规则后，才允许从 `W1_WAIT` 进入其他标签评估。
- 若出现 `W1_PLAY`，必须写 ledger。

赛后计划：

- 用 ledger 验证赛前数据、决策标签和赛后结果之间的关系。
- 小组赛期间滚动校准字段权重、risk flag 表达和 data gap 分类。
- 保留每次实质变化快照，支持专家复盘和赛后审计。

## 13. 验收文件

当前核心文件：

- `docs/W1_PRODUCTION_LITE.md`
- `config/w1_match_card_schema.json`
- `config/w1_decision_policy.json`
- `config/w1_ledger_schema.json`
- `data/processed/match_cards/group_stage_round1/`
- `data/processed/ledger/w1_ledger_group_stage_round1.csv`
- `scripts/w1_watcher.sh`
- `scripts/check_w1_production_lite.py`
- `scripts/check_w1_round1_real_fixture_cards.py`
- `scripts/check_w1_watcher.py`

本报告只用于专家评审，不替代 schema、policy 或 checker。

