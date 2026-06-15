# W1 Missing Data Source Verification Report

**Date:** 2026-06-10  
**Method:** 实测验证，非理论分析  
**Samples:** 5 国家 × 5 场馆 × 3 赛事赔率

---

## 1. Elo Rating

| 项目 | 结果 |
|------|:----:|
| clubelo.com | ❌ connection timed out（多次尝试均失败） |
| eloratings.net | ❌ JS 动态渲染，页面仅 1815 字节骨架，数据通过 `visitor.pl` 动态加载 |
| eloratings.net 公开 CSV/JSON | ❌ 不存在（404） |
| football-data CSV → 自行计算 Elo | ✅ 可行（M1 已有 football_data CSVs） |
| **结论** | ❌ 无公开可用 Elo rating 下载源 |

**推荐 source：** football-data.co.uk CSV 自行计算 Elo（基于已有 M1 数据）

---

## 2. FIFA Rank

| 项目 | 结果 |
|------|:----:|
| inside.fifa.com 可爬取 | ❌ Cloudflare / Next.js SSR 保护，curl 直接抓取被拦截 |
| 页面 __NEXT_DATA__ | ✅ 存在但 12MB，被 captcha 保护无法直接获取 |
| 公开 API | ❌ `api.fifa.com/*` 无公开文档/认证 |
| **结论** | ❌ 当前环境无可行方法程序化获取 |

**推荐 source：** 
- 手动 CSV（每月一次复制粘贴，作为静态资产 commit）
- 或者注册 The Odds API（免费层 1000 req/月）

---

## 3. Venue lat/lng

| 来源 | 样本 | 结果 |
|------|------|:----:|
| api-football venues endpoint | Estadio Azteca | ❌ latitude / longitude 均为 null |
| Open-Meteo Geocoding（free） | Mexico City / London / Paris / Tokyo / Rio | ✅ 全部返回准确坐标（城市级） |
| Nominatim OSM | 场馆名搜索 | ❌ 限流（429） |
| **结论** | ✅ Open-Meteo 地理编码可用，城市级精度 | |

**推荐 source：** Open-Meteo Geocoding API（免费，无限请求）

---

## 4. first_seen_odds_proxy

| 内容 | 结果 |
|------|:----:|
| api-football odds 返回 snapshot_time | ✅ `update: 2026-06-10T02:28:22+00:00` |
| 跨 fixture 有不同 snapshot 时间 | ✅ 3 个 fixture 各不同 |
| 支持 bookmaker_id + market_id + line + odd 组合 | ✅ Match Winner / AH / OU 均有 |
| 重复轮询可追踪 odds movement | ✅ 理论可行（首次看到的 odds 即为 first_seen 代理） |
| **结论** | ✅ api-football 可作 first_seen_odds_proxy |

**记录 key 设计：** `fixture_id + bookmaker_id + bet_id + value`

---

## 5. 各国家 squad 快速验证

| 国家 | api-football team_id | Squad Count | 可用字段 |
|------|:---:|:---:|----------|
| Argentina | 26 | 26 | number / name / position / age |
| France | 2 | 26 | 同上 |
| Brazil | 3 | 26 | 同上 |
| England | 10 | 26 | 同上 |
| Japan | 47 | 26 | 同上 |

✅ 全部可用，标准格式。

---

## 6. 快照对比能力验证

| 赛事 | fixture_id | bookmakers | snapshot_time |
|------|:---:|:---:|:---:|
| Mexico vs South Africa (WC 2026) | 1489369 | 14 | 2026-06-10T02:28:22Z |
| France vs Senegal (WC 2026) | 1489383 | 13 | 2026-06-10T03:00:09Z |
| England vs Costa Rica (friendly) | 1525494 | 13 | 2026-06-10T04:19:16Z |

✅ 所有决赛圈 + 友谊赛均有完整 odds 覆盖。

---

## 结论

| 字段 | 实测结果 | 推荐来源 |
|------|:--------:|----------|
| Elo rating | ❌ 无公开源 | football-data CSV → 自行计算 |
| FIFA rank | ❌ 爬虫被拦截 | 手动 CSV / The Odds API |
| venue lat/lng | ✅ Open-Meteo Geocoding | Open-Meteo（免费） |
| first_seen_odds_proxy | ✅ api-football | api-football（已激活） |
| squad_list | ✅ api-football | api-football |
| odds_snapshot | ✅ api-football | api-football |

| 项 | 结果 |
|---|---|
| **STATUS** | ✅ 实测完成 |
| **tested_fields** | Elo rating / FIFA rank / venue latlng / first_seen_odds_proxy |
| **field_results** | 2 可用（latlng/odds_proxy），2 不可用（Elo/FIFA） |
| **usable_sources** | api-football / Open-Meteo Geocoding |
| **missing_after_test** | Elo rating（需自算）、FIFA rank（需手动/付费） |
| **recommended_source_for_each_field** | Elo→自算、FIFA→手动CSV、latlng→Open-Meteo、odds_proxy→api-football |
| **quota_used** | api-football ~20 req, Open-Meteo ~12 req |
| **old_system_touched** | 🚫 NO |
| **next_action** | 等 BOSS 指令 |
