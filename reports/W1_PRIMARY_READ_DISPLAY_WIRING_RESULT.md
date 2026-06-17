# W1 Primary Read 接入展示 — 结果(纯展示层)

**日期**: 2026-06-17
**类型**: 把阶段 F 的"研究结论"接进 Director View · **display-only** · 不改概率 · 不改 build · 不接 API
**我改的被跟踪文件只有 2 个**:`reports/dashboard/W1_VISUAL_DASHBOARD.html`、`scripts/check_w1_visual_dashboard.py`。未碰技术员/F 任何后端文件。

---

## 1. 改了什么

Director View 第一屏(hero 下方)新增**一行"研究结论"**:

```
研究结论  单点读数 / 等待 / 跳过 / 阻断   · {原因}   （研究用途·非推介）
```

- 颜色:单点读数=绿、等待=琥珀、跳过=灰、阻断=红。
- 逻辑:render JS 新增 `primaryRead(r)`,**与 F 的 `decide()` 同款逻辑就地派生**(BLOCKED>WAIT>SKIP>PRIMARY_READ;skip 阈值 0.40;未放行作注记不作硬 WAIT)。不依赖 F 的 JSON、不改嵌入数据、不接 build——和阶段 B 一样的纯展示派生。
- D 的"独立支撑不足"已含在 hero/读数语境里;F 决策标签是这次新增的关键信息(本场到底有没有形成稳定读数)。

---

## 2. 逻辑一致性(已证)

同一套 JS 逻辑跑 **F 的外部数据源**(`reports/dashboard/assets/w1_dashboard_data.json`)→ **PRIMARY_READ 9 / SKIP 2 / WAIT 13**,与 F 的 Python 输出**完全一致**,证明前端派生 = 后端 F。

> dashboard 内嵌快照(`<script id="w1-data">`)比外部 JSON 略旧一场,故页面就地渲染可能出现 8/2/14 之类 ±1 的差异——这是**数据新鲜度**,非逻辑差异;页面从实时 `/dashboard-data` 加载时用最新数据,自洽。

---

## 3. 验证

- render JS `node --check` **OK**(新增 `primaryRead` + 嵌套模板字面量合法)。
- **强化(只增不减)**:`check_w1_visual_dashboard` 第一屏必含 token 加入 `研究结论`。
- 用词避坑:dashboard 禁用 `投注/下注/资金/稳赚/必胜/保证命中/盈利`;改用"（研究用途·非推介）",不含禁词。
- **全 checker PASS**:`check_w1_visual_dashboard` / `check_w1_recommendation_output_policy` / `check_w1_opportunity_phase_a` / `check_w1_fivedim_lite` / `check_w1_primary_read`。
- 红线:未改 `w1_score_engine`/`DEFAULT_RHO`/build λ·矩阵/受保护 config;无概率改动;无投注语言;改动仅 2 个被跟踪文件。

---

## 4. 真机提交

```
git add reports/dashboard/W1_VISUAL_DASHBOARD.html scripts/check_w1_visual_dashboard.py \
        reports/W1_PRIMARY_READ_DISPLAY_WIRING_RESULT.md
git commit -m "W1_FIVEDIM: wire research Primary Read (F) into Director View (display-only, no prob change)"
# 复核
python3 scripts/check_w1_visual_dashboard.py
python3 scripts/check_w1_primary_read.py
# 打开 dashboard 看 hero 下方多一行"研究结论 · 单点读数/等待/跳过/阻断"
```

---

## 5. 边界 / 还可选

- 已接**展示**;**未**接赛前锁定 ledger(把每场 PRIMARY_READ + 时间戳写进账本做赛后审计闭环)——那是账本/记录改动,需你单独授权。
- 仍未接 API;E(因子→λ)维持封锁;一切仍是"市场复述 + 诚实研究读数",非投注。
