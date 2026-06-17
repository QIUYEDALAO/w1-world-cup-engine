# W1_PRIMARY_READ_SELECTOR — 阶段 F 结果

**日期**: 2026-06-17
**性质**: 研究结论选择器 · 只读 · 离线 · **不是投注推介 selector** · 不改概率 · 未接生产
**定位**: 每场输出**一个单点研究结论**:`PRIMARY_READ / WAIT / SKIP / BLOCKED`。PRIMARY_READ = 把**既有市场隐含读数**(方向+区间)打包,附数据可信度与阶段D因子注记;**≈市场共识、非独立优势、非投注、不承诺命中**。

---

## 1. 决策门(优先级 BLOCKED > WAIT > SKIP > PRIMARY_READ)

| 决策 | 触发 |
|---|---|
| **BLOCKED** | 市场 1X2 不可用 / 概率不自洽 |
| **WAIT** | 关键赛前数据未确认(首发未确认 + W1硬风控未放行 + 仍在早盘窗口),等赛前刷新 |
| **SKIP** | 1X2 最大类概率 < 0.40(市场太均衡,无清晰倾向) |
| **PRIMARY_READ** | 以上都不触发 → 输出研究读数 |

**关键诚实点**:本数据集 24 场 `play_guard.pass` 全为 False(首发从未确认)。F **没有**把"未放行"当成硬 WAIT 一刀切,而是把它作为 PRIMARY_READ 上的**数据可信度注记**——因为 F 是**研究读数**,不是 W1_PLAY/投注;读数里明写"W1硬风控未放行(首发未确认)"。

---

## 2. 24 场决策分布

**PRIMARY_READ 9 · SKIP 2 · WAIT 13。**

- WAIT 13:仍在赛前早盘、首发未确认的场次——研究读数推迟到赛前刷新。
- SKIP 2:市场太均衡,无稳定倾向。
- PRIMARY_READ 9:已完赛或市场倾向清晰的场次。

**样例(均已完赛,审计对照):**

| 场次 | PRIMARY_READ 读数 | 实际(仅审计) |
|---|---|---|
| 墨西哥 vs 南非 | 墨西哥不败 · 主队净胜1球 · 进球区间 2-3 · 可信度偏弱 · 独立支撑不足 · 硬风控未放行 | 2:0 |
| 法国 vs 塞内加尔 | 法国不败 · 主队净胜1球 · 进球区间 2-3 · 可信度偏弱 · 独立支撑不足 · 硬风控未放行 | 3:1 |

> `actual_score` 仅作事后审计(`used_in_decision=false`),**绝不进入决策**——checker 对此有硬断言(decide() 不得引用赛后字段)。

---

## 3. 验证

- `check_w1_primary_read.py` **PASS**:每场≤1 个 PRIMARY_READ(fixture 唯一)、决策枚举合法、`independent_edge=false`、`prob_unchanged=true`、`basis=market_implied`、`is_betting_selector=false`、`audit.used_in_decision=false`。
- **无概率泄漏**:精确键扫描确认输出不含 pH/pD/pA/home_win/lambda/... 任何概率字段(读数是**文本结论**,不是新概率)。
- **无赛后泄漏**:`decide()` 源码不含 `actual_score/result`(反向测试)。
- **无投注语言**:政策禁词扫描通过。
- **反向测试**:缺 1X2→BLOCKED;均衡市场→SKIP;注入概率键→被抓。
- 红线 git-diff clean + `DEFAULT_RHO` 未变;输出 `state/w1_primary_read.json` **gitignored**;新增文件全部 **untracked**,未碰任何已跟踪文件。

---

## 4. 边界 / 未接生产

- F 是**离线研究产物 + 政策**,**未**接进 dashboard / 决策 / ledger。
- 若要把 PRIMARY_READ 显示在 Director View 或写进赛前锁定 ledger,是一次**展示/账本接入**改动,需**你单独授权**(只动展示/记录,仍不改概率、仍非投注)。

---

## 5. 红线

只读本地;不接 API;未改 `w1_score_engine`/`DEFAULT_RHO`/build λ·矩阵/受保护 config/dashboard/已跟踪文件;输出零新概率;`independent_edge=false`;非投注平台、不输出资金/命中率;不声明独立优势。

---

## 6. 阶段状态(计划书可建范围已收口)

| 阶段 | 状态 |
|---|---|
| 0 数据支持验证 | ✅ |
| A FiveDim Lite 只读层 | ✅ |
| B Director View 五维就绪度 | ✅ |
| C 历史样本验证 | ✅(否定:因子无独立增量) |
| D Confidence 软用层 | ✅(当前全 insufficient,不改任何东西) |
| **F Primary Read Selector** | ✅(研究结论选择器,非投注) |
| E 独立因子 λ | ⛔ 不予推进(C 数据依据) |
| G 长期生产 / 联赛 profile | ◐ 长期运营,非一次性 |

**计划书里能建、且该建的研究/数据/展示骨架已全部完成。** 唯一没做的 E 是被数据正确挡掉的;G 是长期运营。

**新增文件(真机提交)**:`config/w1_primary_read_policy.json`、`scripts/w1_primary_read_builder.py`、`scripts/check_w1_primary_read.py`、本报告。`state/` 输出 gitignored。

```
git add config/w1_primary_read_policy.json scripts/w1_primary_read_builder.py \
        scripts/check_w1_primary_read.py reports/W1_PRIMARY_READ_SELECTOR_RESULT.md
git commit -m "W1_FIVEDIM Stage F: research Primary Read selector (PRIMARY_READ/WAIT/SKIP/BLOCKED; not a bet; no prob change)"
```
