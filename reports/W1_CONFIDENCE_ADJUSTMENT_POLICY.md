# W1_CONFIDENCE_ADJUSTMENT_POLICY — 阶段 D(软用层)

**日期**: 2026-06-17
**性质**: 纯研究 · 只读 · 不接 API · **绝不改任何概率/λ** · 未接生产路径
**依据**: 阶段 C《W1_FIVEDIM_HISTORICAL_VALIDATION》——因子无独立增量,故 D 只能"软用"。

---

## 1. D 做什么 / 不做什么

| 只允许设置 | 绝不触碰 |
|---|---|
| `confidence_grade`、`risk_flags`、`data_quality_note`、`market_vs_factor`、`explanation_cn` | `λ_home/λ_away`、`score_matrix`、`raw_probability`、`pH/pD/pA`、`DEFAULT_RHO`、任何概率 |

**核心约束(由阶段 C 直接推出)**:**因子与市场一致【不】上调可信度**(一致无增量);只对**分歧**加风险提示、对**缺失**降数据质量。这与之前上线的"五维就绪度=非独立优势"口径一致。

---

## 2. 三种状态(纯函数 `adjust`,已单测 + checker 反向测试)

| market_vs_factor | 触发 | 动作(均不改概率) |
|---|---|---|
| `insufficient` | 实力/战术维数据不足 | 标"独立支撑不足";可信度至多 `C_weak`;**不上调** |
| `aligned` | 因子与市场同向 | **不加分**(仅表示无分歧);grade 仍 `C_weak` |
| `divergent` | 因子与市场背离 | 加 `RISK_MARKET_FACTOR_DIVERGENCE`(仅提示);**不改概率** |
| `factor_missing` | 市场读数都没有 | `D_insufficient` |

---

## 3. 当前世界杯 24 场的实测结果

**24 场全部 = `insufficient`。** 因为当前 match card 的实力/战术维本地无数据(见阶段 A 就绪度),D 对每场只输出:"市场读数可用;独立历史因子本地不足,**不上调可信度**,维持市场复述定位。"——诚实、保守、零概率改动。

> 即:在当前数据下,D 实际上**不会**改变任何东西,只会如实说明"没有独立支撑可加分"。这正是它该有的样子。

---

## 4. 验证

- `check_w1_confidence_adjustment.py` **PASS**:输出无任何概率/λ 字段(精确键扫描);`independent_edge=false`、`prob_unchanged=true`;状态/grade 合法;引用阶段 C;红线 git-diff clean + `DEFAULT_RHO` 未变。
- **反向测试**:① 注入概率键 → 捕获;② `aligned` 若被改成抬升 grade → 捕获;③ `divergent` 必带风险旗标;④ `adjust()` 任何分支都不返回概率字段。
- 输出 `state/w1_confidence_adjustment.json` **gitignored**;新增文件全部 **untracked**,未碰任何已跟踪文件。

---

## 5. 边界 / 未接生产

- D 目前是**离线软信号 + 政策**,**没有**接进 build / dashboard / 决策路径。
- 若要让这些 `risk_flags / data_quality_note` 显示在 dashboard 或进入 WAIT/SKIP 文案,那是一次**展示/决策接入**改动,需**你单独授权**(类似阶段 B 的做法,只动展示、仍不改概率)。

---

## 6. 红线

只读本地;不接 API;未改 `w1_score_engine`/`DEFAULT_RHO`/build λ·矩阵/受保护 config/dashboard/任何已跟踪文件;输出零概率字段;一致不加分;不声明独立优势。

---

## 7. 阶段状态

- ✅ **阶段 D 完成**(软用层:政策 + 只读模块 + checker + 本报告)。当前数据下实际为"全 insufficient、不改任何东西"。
- ⛔ **阶段 E(因子→λ)不予推进**(阶段 C 依据)。
- ⛔ **阶段 F(Primary Read Selector)** 维持封锁。
- ◐ **可选**:把 D 的软信号接进 dashboard 展示(需单独授权,仅展示、不改概率)。

**新增文件(真机提交)**:`config/w1_confidence_adjustment_policy.json`、`scripts/w1_confidence_adjustment.py`、`scripts/check_w1_confidence_adjustment.py`、本报告。`state/` 输出 gitignored。

```
git add config/w1_confidence_adjustment_policy.json scripts/w1_confidence_adjustment.py \
        scripts/check_w1_confidence_adjustment.py reports/W1_CONFIDENCE_ADJUSTMENT_POLICY.md
git commit -m "W1_FIVEDIM Stage D: soft confidence-adjustment layer (no probability change; agreement never boosts; per Stage C)"
```
