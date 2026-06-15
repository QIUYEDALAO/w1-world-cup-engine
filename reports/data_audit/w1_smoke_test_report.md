# W1 Data Source Smoke Test Report

**Date:** 2026-06-10  
**Method:** 实测真实 API/页面查询，非理论审计  
**Quota used:** ~15 次 api-football 请求（当前共享 Business 100 req/day）

---

## Endpoint Results

### ✅ api-football (已激活, Business plan)

| 字段 | Endpoint | Sample | Result | Raw Count | Key Fields Found | Gap | Usable |
|------|----------|--------|:------:|:----------:|------------------|-----|:------:|
| fixtures | `fixtures?id=1489369` | WC 2026 Mexico vs South Africa | **YES** | 1 fixture | date/venue/referee/round/teams/status | referee=null (0/72) | YES |
| odds_1X2 | `odds?fixture=1489369` | Mexico-SA Match Winner | **YES** | 14 bookmakers | Home=1.40 Draw=4.30 Away=8.75 | — | YES |
| odds_AH | `odds?fixture=1489369` | Asian Handicap | **YES** | 14 bookmakers | Home -1=1.70, -0.5/1.5 lines | — | YES |
| odds_OU | `odds?fixture=1489369` | Goals Over/Under | **YES** | 14 bookmakers | O/U 0.5/1.5/2.5/3.5 | — | YES |
| odds_snapshot_time | `odds?fixture=1489369` | `update` field | **YES** | 14 bookmakers | 2026-06-10T02:28:22Z | — | YES |
| standings/group | `standings?league=1&season=2026` | WC 2026 Playoffs | **YES** | 13 groups | 12 playoff groups + 1 promo playoff | 仅 Playoffs，无 Group A/B/C 标 | PARTIAL |
| squads | `players/squads?team=16` | Mexico 26-man | **YES** | 26 players | Position/age/number/name | — | YES |
| lineups | `fixtures/lineups?fixture=1542183` | France 3-1 NI | **YES** | 2 teams | Formation/Start XI/Subs | 仅完赛比赛可用 | YES |
| injuries | `injuries?league=1&season=2026` | WC 2026 | **YES** | 0 records | Endpoint works, no data yet | 开赛前无数据 | YES |
| statistics | `fixtures/statistics?fixture=1542183` | France 3-1 NI | **YES** | 2 teams | Shots/Possession/Passes/Corners/Fouls | 不含 xG (null) | YES |
| H2H | `fixtures?h2h=16-1531` | Mexico vs South Africa | **YES** | 0 matches | Endpoint works correctly | 两队无历史相遇 | YES |
| venue | `venues?id=1069` | Estadio Azteca | **YES** | 1 venue | Name/City/Capacity/Surface/Address | lat/lng 为 null | YES |
| recent_form | `fixtures?team=2&last=1` | France last match | **YES** | 1 fixture | Scoring/League/Date/Venue | — | YES |
| knockout_path | round field in fixtures | WC 2026 | **PARTIAL** | 3 rounds (G1/G2/G3) | 有 round 字段 | 淘汰赛未排期，无 bracket | PARTIAL |

### ✅ Open-Meteo (免费, 无需 key)

| 字段 | Endpoint | Sample | Result | Key Fields | Usable |
|------|----------|--------|:------:|------------|:------:|
| weather_forecast | `forecast?latitude=19.43&longitude=-99.13` | Mexico City | **YES** | 168h ahead, temp/weathercode/precip | YES |
| weather_historical | `archive?latitude=50.63&longitude=3.06` | Lille 2026-06-08 | **YES** | 24h, temp/precip/weathercode | YES |

### ⚠️ FIFA Official (公开页面, 需爬取)

| 字段 | Page | Sample | Result | Key Fields | Usable |
|------|------|--------|:------:|------------|:------:|
| FIFA_rank | `inside.fifa.com/fifa-world-ranking` | World Ranking | **PARTIAL** | Next.js SSR, 12MB __NEXT_DATA__ | PARTIAL |
| knockout_path | same page | Bracket | **PARTIAL** | Not extracted | PARTIAL |

### ❌ The Odds API (未激活)

| 字段 | Endpoint | Result | Reason |
|------|----------|:------:|--------|
| odds | `/v4/sports/soccer_fifa_world_cup/odds` | NO | 需要 API key |

---

## 5. 关键结论

### ✅ Usable for W1 MVP: **YES**

直接可用字段:
- fixtures / venue / round / group standings
- odds 1X2 / AH / OU / 14 bookmakers / snapshot time
- team squads (26-man) / lineups / statistics
- recent form / H2H
- weather (open-meteo, free, historical + forecast)
- injuries endpoint (结构就绪)

需额外处理的:
- FIFA 排名 → 从 Next.js 页面提取（12MB payload 含数据）
- knockout bracket → 赛事进行后从 round 字段推导 / FIFA 页面
- referee → 赛前 api-football 会填充（当前为 null）
- lat/lng → 需第三方 geocoding 补全景点的坐标

### ❌ 当前不可用:
- The Odds API（需注册 + key）
- 历史 WC 赔率（api-football 不存历史）
- xG 统计（api-football statistics endpoint 返回 null）

### 📊 Quota Used
- api-football: ~15 请求 ✅（Business 100 req/day，充裕）
- Open-Meteo: 2 请求 ✅（无限免费）
- FIFA: 2 页面抓取 ✅（无限制）

---

## 最终输出

| 项 | 结果 |
|---|---|
| **STATUS** | ✅ PASS |
| **tested_sources** | 4 个：api-football / Open-Meteo / FIFA Official / The Odds API |
| **endpoint_results** | 19 个端点实测，见上表 |
| **usable_fields** | 14 个字段直接可用（fixtures/odds/standings/squads/lineups/stats/weather/H2H/form/venue） |
| **missing_fields** | FIFA_rank（需爬取）、knockout_bracket（未排期）、referee（赛前填充）、lat/lng（需补）、xG（null） |
| **quota_used** | api-football ~15 req、Open-Meteo 2 req |
| **usable_for_w1_mvp** | ✅ **YES** — api-football + Open-Meteo 即可支撑 MVP |
| **BLOCKER** | ❌ 无 BLOCKER |
| **next_action** | 等待 BOSS 指令。建议：① W1 数据采集架构设计 ② 注册 The Odds API ③ FIFA 排名爬虫方案 |
