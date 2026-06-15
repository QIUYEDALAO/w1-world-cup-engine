# W1 S1B Odds Extension V1 — RESULT

**阶段**: W1_S1B_ODDS_EXTENSION_V1  
**日期**: 2026-06-16  
**状态**: ✅ 完成

---

## 1. Commit 列表

| # | 信息 |
|---|------|
| commit 1/3 | spec + schema + checker registration |
| commit 2/3 | local OU merge + 128-match FULL pipeline replay + checkers |
| commit 3/3 | RESULT |

---

## 2. 文件清单

### 新增脚本

| 文件 | 作用 | 状态 |
|------|------|------|
| `scripts/merge_w1_odds_extension.py` | B1: 本地赔率与 S1B 数据集合并 | ✅ 128/128 FULL |
| `scripts/w1_backtest_full_pipeline.py` | B2: FULL pipeline 回测 | ✅ 128 场跑通 |
| `scripts/check_w1_odds_extension.py` | C1: 扩展数据 checker | ✅ 0 FAIL |
| `scripts/check_w1_full_pipeline_backtest.py` | C2: FULL 回测 checker | ✅ 0 FAIL |

### 产出文件

| 文件 | 内容 |
|------|------|
| `reports/w1_backtest_full_pipeline_v1.json` | FULL 回测指标 |
| `reports/w1_backtest_full_pipeline_v1.md` | FULL 回测摘要 |
| `reports/W1_S1B_ODDS_EXTENSION_V1_RESULT.md` | 本报告 |
| `data/processed/international/w1_international_dataset_extended.csv` | 合并后扩展数据集（gitignored） |
| `data/processed/international/w1_current_odds_snapshot_quality.json` | 2026 当前快照质量（gitignored） |

### 本地赔率源文件（gitignored，不入仓）

| 文件 | 行数 |
|------|------|
| `data/local_odds/world_cup_odds_2026.csv` | 12 |
| `data/local_odds/world_cup_odds_2022.csv` | 64 |
| `data/local_odds/world_cup_odds_2018.csv` | 64 |
| `data/local_odds/world_cup_odds_historical.csv` | 128 |

### 体检报告

| 文件 | 内容 |
|------|------|
| `reports/W1_LOCAL_ODDS_2026_QUALITY_CHECK.md` | 2026 快照体检 |
| `reports/W1_LOCAL_ODDS_HISTORICAL_QUALITY_CHECK.md` | 2018+2022 历史数据体检 |

---

## 3. 数据范围

| 子集 | 场次 | FULL? | 说明 |
|------|------|-------|------|
| **2018** | **64** | ✅ FULL | 全部 64 场 OU ladder 完整 |
| **2022** | **64** | ✅ FULL | 全部 64 场 OU ladder 完整 |
| **2018+2022（FULL subset）** | **128** | ✅ FULL | 完整 OU ladder → FULL pipeline |
| 2014 | 0 | ⚠️ WARN | `NO_LOCAL_ODDS_SOURCE_2014` |
| AH | 0 | ⚠️ WARN | `AH_MISSING_NO_SOURCE` |
| 2026 current | 12 | ❌ 不进历史回测 | 仅 Forward-Ledger 使用 |
| 全量 S1B | 1081 | ❌ 不外推 | 未覆盖样本保持 `1X2_ONLY` |

### 额外数据字段（合并后新增）

- `odds_1x2_home_alternate / draw_alternate / away_alternate`
- `ou_O05..U45`（10 列 OU Ladder）
- `btts_yes_alternate / btts_no_alternate`
- `ou_market_available / ou_mu_derived / mu_source`
- `odds_source_alternate / odds_scope`
- `odds_extension_covered / odds_extension_missing_reason`
- `ah_available / ah_missing_reason`

---

## 4. 主要指标（FULL subset: 128 场）

| 指标 | 值 |
|------|-----|
| 方向准确率（dir accuracy） | **0.5391** |
| mean RPS | **0.4027**（beats uniform ✅） |
| mean logloss (1X2) | **0.9787** |
| mean logloss (exact score) | **2.8762** |
| mean Brier | **0.5739** |
| Market reproduction pass rate | **0.9141**（117/128 在 <0.02 误差内） |
| Market reproduction mean abs err | **0.0091** |
| OU Over 1.5 calibration ECE | **0.0570** |
| OU Over 2.5 calibration ECE | **0.0807** |
| BTTS calibration ECE | **0.0686** |
| Walk-forward train RPS | 0.3932 |
| Walk-forward test RPS | 0.4680 |
| FULL pipeline validated | **true（仅 2018+2022 WC 子集）** |

---

## 5. 红线确认

| 红线 | 状态 |
|------|------|
| 未改 `scripts/w1_score_engine.py` | ✅ |
| DEFAULT_RHO 仍为 `-0.057766` | ✅ |
| 未改 `config/w1_decision_policy.json` | ✅ |
| 未改 `config/w1_odds_movement_thresholds.json` | ✅ |
| 未抓取新数据 | ✅ 仅读取已有本地 CSV |
| 未访问 footiqo.com | ✅ |
| 未接 API | ✅ |
| 未爬取 | ✅ |
| `data/local_odds/*.csv` 不入仓 | ✅ gitignored |
| `data/processed/international/*` 不入仓 | ✅ gitignored |
| 不外推 1081 全量 | ✅ |
| 无投注/资金/命中率表达 | ✅ |

---

## 6. WARN_ONLY

以下项目仅标记 WARN，不阻断阶段结束：

- ❌ **2014 缺失** — footiqo.com 不提供 2014 WC 赔率，`NO_LOCAL_ODDS_SOURCE_2014`
- ❌ **AH 缺失** — footiqo.com xBet 数据源不包含亚洲让球盘，`AH_MISSING_NO_SOURCE`
- ⚠️ **128 场样本偏小** — 仅供机制验证和 sanity check，**不调参**，不外推
- ⚠️ **market reproduction 11/128 场超阈值** — 需人工复核异常场次

---

## 7. 是否回滚

**否。** 所有 checker 通过，数据完整性校验通过，无需回滚。

---

## 8. 下一阶段建议

1. **扩 OU 覆盖** — 如果找到其他数据源（如 football-data.co.uk），补齐 2014 及更多国际赛 OU 数据
2. **获取本地 AH 后做 AH 校验** — 待亚洲让球数据到位后，扩展 AH 回测
3. **Forward-Ledger 持续跑** — 2026 当前赔率快照已接入，WC 2026 赛时持续使用
4. **S2 仍 prototype** — 国家队强度模型仍处原型阶段，待更大数据集验证

---

## 9. 边界声明

> W1 仍是概率建模、赛前分析、风险读数和赛后复盘系统；  
> **不是投注平台，不输出资金建议，不承诺命中率，不把模型-市场分歧表述为投注机会。**  
> `FULL pipeline validated = true` 仅对 **2018+2022 WC 128 场覆盖子集** 成立，  
> 不适用于全量 1081 行 S1B 数据集、2014 世界杯、AH 分析、或 2026 当前快照。
