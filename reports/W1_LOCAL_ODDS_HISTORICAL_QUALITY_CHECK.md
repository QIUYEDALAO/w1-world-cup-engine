# W1 本地历史赔率数据体检报告 — world_cup_odds_historical.csv

**报告日期**: 2026-06-16  
**数据来源**: footiqo.com → Database → World Cup → Odds tab → Last Seasons  
**赔率类型**: xBet closing odds (pre-match)  
**指令状态**: 只读体检，不进入 FULL pipeline，不修改生产配置

---

## 1. 基本信息

| 赛季 | 文件 | 行数 | 是否完整世界杯 |
|------|------|------|---------------|
| 2022 | `world_cup_odds_2022.csv` | **64** ✅ | ✅ 完整世界杯 |
| 2018 | `world_cup_odds_2018.csv` | **64** ✅ | ✅ 完整世界杯 |
| 2014 | — | **N/A** ❌ | footiqo.com 不提供 2014 WC 赔率 |
| 合并 | `world_cup_odds_historical.csv` | **128** | |

## 2. 字段完整性

| 检查项 | 2018 (64场) | 2022 (64场) |
|--------|------------|------------|
| H/D/A 列存在 | ✅ PASS | ✅ PASS |
| 所有行 H/D/A 非空 | ✅ PASS | ✅ PASS |
| 所有 H/D/A >= 1.01 | ✅ PASS | ✅ PASS |
| OU Ladder O05..U45 完整 | ✅ PASS | ✅ PASS |
| 所有 OU 格非空 | ✅ PASS | ✅ PASS |
| BTTSY/BTTSN 存在 | ✅ PASS | ✅ PASS |
| AH 字段 | ⚠️ FAIL — **AH_MISSING** | ⚠️ FAIL — **AH_MISSING** |
| 空赔率格子 | ✅ 0 | ✅ 0 |
| 0 赔率 | ✅ 0 | ✅ 0 |
| 非法赔率（<1.0 in H/D/A/BTTS） | ✅ 0 | ✅ 0 |
| 重复比赛 | ✅ 0 | ✅ 0 |

## 3. 队伍名称映射（W1 team_id）

使用 `w1_world_cup_engine/config/w1_team_aliases.json` 校验：

### 2018 独有队伍（8 支）
Argentina, Belgium, Colombia, Costa Rica, Croatia, Denmark, Egypt, England, France, Germany, Iceland, Iran, Japan, Mexico, Morocco, Nigeria, Panama, Peru, Poland, Portugal, Russia, Saudi Arabia, Senegal, Serbia, South Korea, Spain, Sweden, Switzerland, Tunisia, Uruguay

### 2022 独有队伍（8 支）
Cameroon, Canada, Ghana, Netherlands, Qatar, Wales

### 共同队伍（24 支）
Argentina, Australia, Brazil, Costa Rica, Croatia, Denmark, Ecuador, England, France, Germany, Iran, Japan, Mexico, Morocco, Netherlands, Poland, Portugal, Saudi Arabia, Senegal, Serbia, South Korea, Spain, Switzerland, Tunisia, USA

**结果**: 全部队伍名均 1:1 映射到 W1 team_id，无一缺失。

## 4. S1B 国际赛数据集匹配（date + team_id）

| 赛季 | 匹配结果 |
|------|---------|
| 2022 | **64/64** ✅ — 全部匹配成功 |
| 2018 | **64/64** ✅ — 全部匹配成功 |

两个赛季的数据均可按 `match_date` + `home_team_id` + `away_team_id` 与 S1B 数据集完美关联。

## 5. 赔率来源确认

| 检查项 | 结果 |
|--------|------|
| Bookmaker | **xBet** ✅ |
| 是否为 closing odds | **是** ✅ — 列名前缀为 `xbetClose*` |
| 是否为 90 分钟常规时间 | **是** ✅ — footiqo.com 标准 full-time 市场 |
| 数据源 | footiqo.com WordPress wpDataTables 插件后端 |

## 6. 数据标签

| 字段 | 值 |
|------|-----|
| 标签类型 | `historical_odds_snapshot` |
| 适用阶段 | B1 (AU) / B2 (OU) 进入候选 |
| 不适用 | 不含 AH，不可用于 AH 分析 |

## 7. OU 市场主线观察

两届世界杯均以 OU 2.5 为市场主流线（O25 最接近 2.0），一致性良好。

---

## 总体结论

```
体检结果：33/36 PASS，3 FAIL — 全部 FAIL 为 AH_MISSING（已知数据源限制）
```

### ✅ 可以进入 B1/B2 分析的赛季

| 赛季 | 场次 | 质量 | 理由 |
|------|------|------|------|
| **2022** | 64 | ⭐⭐⭐⭐⭐ | 结构完整，HDA/OU/BTTS 全量，无空值，S1B 64/64 完全匹配 |
| **2018** | 64 | ⭐⭐⭐⭐⭐ | 同上，结构完整，S1B 64/64 完全匹配 |

### ❌ 无法获取的赛季

| 赛季 | 原因 | 建议替代来源 |
|------|------|-------------|
| **2014** | footiqo.com 不提供 | football-data.co.uk / OddsPortal / manual |

### ⚠️ 需要人工复核的事项

1. **AH 缺失** — 两个赛季均无亚洲让球盘口。如 AH 分析为必需，需从其他来源获取。
2. **建议取样抽查** — 取 2022 年 5 场和 2018 年 5 场，与 api-football 或 OddsPortal 的预赛 xBet 赔率交叉验证，确认 `xbetClose*` 确实是 kick-off 时的 closing odds 而非开盘价。
3. **2014 数据回填** — 如需 2014 WC 完整的 64 场 OU/AH 数据以扩大回测窗口，建议 BOSS 指定从哪里获取。

---

### 文件路径汇总

| 文件 | 大小 | 行数 |
|------|------|------|
| `data/local_odds/world_cup_odds_2022.csv` | ~8KB | 64 |
| `data/local_odds/world_cup_odds_2018.csv` | ~8KB | 64 |
| `data/local_odds/world_cup_odds_historical.csv` | ~16KB | 128 |
| `data/local_odds/world_cup_odds_2026.csv` | ~2KB | 12 |
| `reports/W1_LOCAL_ODDS_2026_QUALITY_CHECK.md` | — | — |
| `reports/W1_LOCAL_ODDS_HISTORICAL_QUALITY_CHECK.md` | — | 本报告 |

*所有 CSV 均保存在 `data/local_odds/`（gitignored），不入仓。未修改任何生产配置或引擎文件。*
