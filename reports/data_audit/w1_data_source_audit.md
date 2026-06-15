# W1 World Cup Data Source Audit

**Date:** 2026-06-10  
**Scope:** W1 World Cup Engine 数据源可用性评估  
**Method:** 实地 API 查询 + 公开文档分析  
**不使用旧系统：** V3/V4/M1 均未触碰

---

## 1. 字段覆盖矩阵

| # | Field | api-football | The Odds API | FIFA官方 | Football-Data | Elo Rating | Weather | 备注 |
|---|-------|:---:|:---:|:---:|:---:|:---:|:---:|------|
| 1 | fixtures | ✅ | ✅ | ✅ | ✅ | — | — | 所有来源均有 |
| 2 | kickoff_time | ✅ | ✅ | ✅ | ✅ | — | — | |
| 3 | venue | ✅ | ❌ | ✅ | — | — | — | api-football: ESTADIO AZTECA |
| 4 | group | ✅ | — | ✅ | — | — | — | api-football: Group Stage - 1 |
| 5 | group_standings | ✅ | — | ✅ | — | — | — | api-football: standings endpoint |
| 6 | knockout_path | PARTIAL | — | ✅ | — | — | — | api-football: round field 不含 bracket |
| 7 | odds_1x2 | ✅ | ✅ | — | ❌ | — | — | api-football: Match Winner markets |
| 8 | odds_AH | ✅ | ✅ | — | ❌ | — | — | api-football: Asian Handicap markets |
| 9 | odds_OU | ✅ | ✅ | — | ❌ | — | — | api-football: Goals Over/Under |
| 10 | opening_odds | ❌ | ❌ | — | ❌ | — | — | **未来源提供开盘赔率** |
| 11 | latest_odds | ✅ | ✅ | — | ❌ | — | — | api-football: 更新 2026-06-10T00:15 |
| 12 | odds_snapshot_time | ✅ | ✅ | — | — | — | — | api-football: `update` 字段 |
| 13 | squad_list | ✅ | — | ✅ | — | — | — | 26人完整 squad 含 position/age |
| 14 | confirmed_lineup | ❌ | — | — | — | — | — | **开赛前1h 内 lineup endpoint 可用** |
| 15 | injuries | ✅ | — | — | — | — | — | WC 2026: 0 条（尚未累积） |
| 16 | suspensions | ❌ | — | — | — | — | — | **api-football 无独立 suspension endpoint** |
| 17 | FIFA_rank | ❌ | — | ✅ | — | — | — | FIFA 页面有数据但无公开 API |
| 18 | Elo_rating | ❌ | — | — | — | PARTIAL | — | clubelo.com 有但 endpoint 不可达 |
| 19 | recent_form | ✅ | — | — | — | — | — | 通过 fixtures + team 内 last_5 |
| 20 | H2H | ✅ | — | — | ✅ | — | — | api-football h2h endpoint |
| 21 | referee | ✅ | — | ✅ | — | — | — | **WC 2026 当前 0/72 已分配** |
| 22 | weather | ❌ | — | — | — | — | ✅ | WeatherAPI.com（需 API key） |
| 23 | rest_days | — | — | — | — | — | — | 需 fixture 间隔计算 |
| 24 | travel_distance | — | — | — | — | — | — | 需 venue 坐标 + 距离计算 |
| 25 | match_importance | — | — | — | — | — | — | 需淘汰赛阶段 + group table 推导 |

**Legend:** ✅ = 可用 / PARTIAL = 部分可用 / ❌ = 不可用 / — = 不适用

---

## 2. 各数据源详细评估

### 2.1 api-football (✅ 已激活 - 已配置 API Key)

- **Historical WC results:** ✅ WC 2022 全 59 场 FT 可用
- **Historical WC odds:** ❌ 空响应（2014/2018/2022 均无赔率）
- **WC 2026 upcoming:** ✅ 72 场 fixture，含分组信息
- **WC 2026 odds:** ✅ 13+ bookmakers，含 Match Winner / AH / OU / Second Half 等市场
- **WC 2026 standings:** ✅ 13 个小组/Playoff 分组 standings
- **WC 2026 team squads:** ✅ 含 26 人名单、position、age
- **WC 2026 form/recent:** ✅ 通过 season-agnostic fixture 查询可获国家队近 10 场
- **WC 2026 referee:** PARTIAL（venue 字段存在（34/72），referee 当前为 0/72，但 endpoint 支持）
- **WC 2026 injuries:** ✅ endpoint 存在（当前 0 条）
- **H2H:** ✅ api-football 支持 `h2h=team1-team2` 接口
- **Update timing:** 赔率约每天 1 次更新
- **Cost:** 已有 Business 订阅，100 请求/天配额（当前 V4 共享）

### 2.2 The Odds API (❌ 未激活 - 需要 API Key)

- **WC 覆盖:** `soccer_fifa_world_cup` sport key 预期存在（类似 NBA/NFL）
- **字段:** event_id / commence_time / home_team / away_team / bookmakers[] / markets[] (h2h, spreads, totals) / last_update
- **Historical:** ✅ 有 historical odds endpoint（免费层保留 1 天）
- **Free tier:** 1000 请求/月，仅全价赔率
- **Paid tier:** $50/月起，含 AH/OU
- **Status:** 当前系统无 API key，需注册

### 2.3 FIFA Official (✅ 公开可访问 - 但无稳定 API)

- **FIFA/Coca-Cola World Ranking:** ✅ 公开页面（inside.fifa.com），需 JS/Next.js 渲染爬取
- **FIFA API:** 部分内部 API 存在（`api.fifa.com/api/v3/...`）但无公开文档
- **Official WC fixture/schedule:** ✅ 可页面获取
- **Referee assignments:** ✅ 官网会发布裁判安排，但非结构化
- **Cost:** 免费
- **Update timing:** 排名月更

### 2.4 Football-Data World Cup Historical (❌ 不可用)

- 确认结论：api-football `/odds?fixture={id}` 对历史 WC 返回空
- Football-Data 不提供 WC 专用 CSV
- 历史 WC 赔率只能从 OddsPortal / football-data.co.uk 的 CSV 中找（足球数据包含 WC 比赛结果但 **不包含赔率**）
- **Status:** 对 W1 当前阶段不可用

### 2.5 Elo Rating / FIFA Rank (PARTIAL)

- **clubelo.com:** Elo 数据存在但 api.clubelo.com endpoint 无法连通（connection timed out）
- **eloratings.net:** 页面展示 JS 动态渲染，无公开 CSV/JSON 下载
- **FIFA ranking:** 仅 website（Next.js），需爬取
- **建议方案:** football-data.co.uk CSV 跑自定义 Elo 计算，或爬取 eloratings.net
- **Cost:** 免费（手动/爬虫）

### 2.6 Weather (✅ 可选 - 需 API key)

- **WeatherAPI.com:** 免费层 100 请求/天，含历史天气
- **字段:** temp_c / condition / humidity / wind_kph
- **定位:** 通过 venue city/coordinates
- **Cost:** 免费层可用

---

## 3. 最佳数据源组合 (Best Source Combo)

### W1 核心数据层

```
api-football (已激活)
  ├── fixtures + venue         → 赛程、球场
  ├── league + standings       → 分组排名
  ├── odds                     → Match Winner / AH / OU（仅当前赛季）
  ├── squads                    → 球队名单
  └── fixtures (team filter)   → 近期状态 / H2H

FIFA Official (爬虫)
  └── World Ranking            → FIFA 排名（逐月）

FIFA API (内部)
  └── knockout bracket         → 淘汰赛路径
```

### 缺失层（需额外方案）

```
Historical odds (WC 2014/2018/2022)
  → OddsPortal scraping / football-data.co.uk 足球包 CSV 手动回填

Elo Rating
  → 自定义计算（基于 football-data CSV 匹配结果）

Weather
  → WeatherAPI.com（免费注册）

Referee / Lineups / Suspensions
  → 赛前 1h api-football 获取
```

---

## 4. 仍缺失字段

| # | 字段 | 严重性 | 替代方案 |
|---|------|--------|----------|
| 1 | **opening_odds** | HIGH | api-football odds 首次快照可替代（但非官方开盘） |
| 2 | **historical WC odds** | HIGH | OddsPortal 手动 / 放弃仅用当前赛季 |
| 3 | **FIFA_rank (programmatic)** | MEDIUM | 爬取 FIFA 页面 / 手动 CSV |
| 4 | **confirmed_lineup** | MEDIUM | 赛前 1h api-football `lineups` endpoint |
| 5 | **suspensions** | MEDIUM | 赛前 injury endpoint + manual check |
| 6 | **referee (for history)** | LOW | 赛前即可；历史数据无 |
| 7 | **weather (for history)** | LOW | WeatherAPI History API |
| 8 | **travel_distance** | LOW | 通过 venue coordinates 计算 |
| 9 | **match_importance** | LOW | 通过 group standing + KO stage 推导 |

---

## 5. Cost & Limit 汇总

| 数据源 | 当前状态 | 成本 | 限制 | 建议 |
|--------|----------|------|------|------|
| api-football | ✅ 已激活 | Business 计划 | 100 req/day | 共享 V4，WC 期间需注意配额 |
| The Odds API | ❌ 需注册 | $0-$50/月 | 免费 1000 req/月 | 建议注册用于赔率交叉验证 |
| FIFA Official | ✅ 免费 | 0 | 无 API 限流 | 需爬虫方案 |
| Football-Data | ✅ 免费 | 0 | — | CSV 覆盖 K1/B1 联赛数据 |
| ClubElo | ❌ 不可达 | 0 | 超时 | EloRating.net 备选 |
| WeatherAPI | ❌ 需注册 | $0-$12/月 | 免费 100 req/天 | 建议注册 |

---

## 6. 结论

**usable_for_w1:** ✅ **yes** — 基于 api-football + FIFA 页面即可构建 W1 核心功能

**关键缺口:**
1. **历史 WC 赔率** — 目前仅 2026 赔率可用，历史回测需 OddsPortal
2. **FIFA 排名** — 无公开 API，需爬取
3. **Elo 排名** — 自定义计算或不可达

**推荐立即动作:**
1. 注册 The Odds API（免费层）用于赔率交叉验证
2. 设计 FIFA 排名爬虫
3. 确认历史 WC 赔率需求范围
