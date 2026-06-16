# W1 本地赔率数据体检报告 — world_cup_odds_2026.csv

**报告日期**: 2026-06-16  
**来源**: footiqo.com → Database → World Cup → Odds tab → Current Season  
**赔率类型**: xBet closing odds (pre-match)  
**指令状态**: 只读体检，不进入 FULL backtest，不修改生产配置

---

## 1. 基本结构

| 项目 | 结果 | 说明 |
|------|------|------|
| 行数 | **PASS** — 12 | 与 WC 2026 当前已赛/即将进行的 12 场一致 |
| 列结构 | **PASS** — 22 列 | id, matchDate, Country, League, Season, homeTeam, awayTeam, H, D, A, O05, U05, O15, U15, O25, U25, O35, U35, O45, U45, BTTSY, BTTSN |
| 重复比赛 | **PASS** — 0 | 所有 matchDate+homeTeam+awayTeam 组合唯一 |

## 2. H/D/A 赔率

| 项目 | 结果 |
|------|------|
| H/D/A 列存在 | **PASS** |
| 所有行 H/D/A 非空 | **PASS** |
| 所有 H/D/A 值 > 0 | **PASS** |
| 所有 H/D/A 值 >= 1.0 | **PASS** |

## 3. OU Ladder（Over/Under 进球数阶梯）

| 阶梯 | O 列 | U 列 | 完整性 |
|------|------|------|--------|
| 0.5 | O05 | U05 | **PASS** — 全填充 |
| 1.5 | O15 | U15 | **PASS** — 全填充 |
| 2.5 | O25 | U25 | **PASS** — 全填充（市场标准线） |
| 3.5 | O35 | U35 | **PASS** — 全填充 |
| 4.5 | O45 | U45 | **PASS** — 全填充 |

12 场中 10 场的最接近市场均衡线（O≈2.0）为 **OU 2.5**，1 场为 OU 1.5（Ivory Coast vs Ecuador），1 场为 OU 4.5（Germany vs Curacao — 明显强弱悬殊）。

## 4. BTTS

| 项目 | 结果 |
|------|------|
| BTTSY 列存在 | **PASS** |
| BTTSN 列存在 | **PASS** |
| 所有 BTTSY/BTTSN 非空 | **PASS** |

## 5. AH（Asian Handicap）

⚠️ **AH_MISSING** — 此数据源不提供亚洲让球盘口赔率。

如需 Forward-Ledger 使用 AH 分析，需另行从以下渠道获取：
- api-football `/odds` endpoint（当前赛季有赔率）
- 手动 BK 数据源

## 6. 队伍名称 → W1 team_id 映射

使用 `w1_world_cup_engine/config/w1_team_aliases.json` 校验：

| 队伍名称（CSV） | W1 team_id | 结果 |
|-----------------|------------|------|
| Australia | `australia` | ✅ |
| Bosnia & Herzegovina | `bosnia_herzegovina` | ✅ |
| Brazil | `brazil` | ✅ |
| Canada | `canada` | ✅ |
| Curacao | `curacao` | ✅ |
| Czech Republic | `czech_republic` | ✅ |
| Ecuador | `ecuador` | ✅ |
| Germany | `germany` | ✅ |
| Haiti | `haiti` | ✅ |
| Ivory Coast | `ivory_coast` | ✅ |
| Japan | `japan` | ✅ |
| Mexico | `mexico` | ✅ |
| Morocco | `morocco` | ✅ |
| Netherlands | `netherlands` | ✅ |
| Paraguay | `paraguay` | ✅ |
| Qatar | `qatar` | ✅ |
| Scotland | `scotland` | ✅ |
| South Africa | `south_africa` | ✅ |
| South Korea | `south_korea` | ✅ |
| Sweden | `sweden` | ✅ |
| Switzerland | `switzerland` | ✅ |
| Tunisia | `tunisia` | ✅ |
| Turkey | `turkey` | ✅ |
| USA | `usa` | ✅ |

**结果**: 全部 24 个队名 1:1 映射到 W1 team_id，无一缺失，无一多义。

## 7. 赔率合法性

| 项目 | 结果 | 详情 |
|------|------|------|
| 空赔率 | **PASS** — 0 | 全部 12×20=240 个赔率格子均有值 |
| 0 赔率 | **PASS** — 0 | 无零值 |
| <1.0 赔率（H/D/A/BTTS） | **PASS** — 0 | 所有 H/D/A/BTTSY/BTTSN >= 1.01 |
| 数值格式错误 | **PASS** — 0 | 全部可解析为 float |

## 8. OU 市场主线选择

大多数比赛（10/12）的 O25 赔率最接近 2.0，符合 OU 2.5 是 WC 市场主流线的预期。  
唯一例外：Germany vs Curacao（OU 4.5 最接近），Ivory Coast vs Ecuador（OU 1.5 最接近）。

## 9. 分类标签

| 项目 | 结果 |
|------|------|
| 标签类型 | `odds_snapshot_current_2026` |
| 时间范围 | 2026-06-11 至 2026-06-15 |
| 是否 historical backtest | **否** — 2026 赛事进行中 |
| 适用场景 | Forward-Ledger / 当前赔率快照 |
| 不适用场景 | 2014/2018/2022 历史 192 场 OU/AH 回测 |

---

## 总体结论

```
体检结果：14/15 PASS，1 FAIL（AH_MISSING — 已知数据源限制）
```

1. ✅ **结构完整** — 12 场 2026 WC 赔率快照，含完整 1X2、OU Ladder（O05~U45）、BTTS，全部数值有效且无空值。

2. ✅ **队伍名映射零冲突** — 全部 24 个队名均能在 W1 team alias 系统中 1:1 解析，无需新增别名。

3. ⚠️ **AH 缺失** — 此数据源只提供 1X2 / OU / BTTS，不提供亚洲让球盘。如需 AH 数据需另行获取。

4. 🛑 **不是历史回测数据** — 本文件标记为 `odds_snapshot_current_2026`，属于 Forward-Ledger 级数据，**不能**填入 2014/2018/2022 的 192 场历史回测 pipeline。

5. 🛑 **不继续抓取 Last Seasons** — 等待 BOSS 后续指令。

---

*报告由 OpenClaw 生成，只读审计，未修改任何生产文件。*
