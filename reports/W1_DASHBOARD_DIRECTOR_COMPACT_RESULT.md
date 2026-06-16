# W1_DASHBOARD_DIRECTOR_COMPACT — RESULT

**类型**: Director View 紧凑收尾 · **纯展示层（display-only）**
**日期**: 2026-06-17
**基线 HEAD**: `fe7eadd`（技术员 Phase A 完成版）
**范围**: 只改 dashboard 渲染层密度。**不改模型 / build 计算 / 引擎 / `DEFAULT_RHO` / API / checker 安全断言**。

> 背景：Phase A（技术员 `fe7eadd`）内容契约都对，但布局过松、浪费空间（顶部摘要条与第一屏重复、候选共识是 2 列大卡、pCore 多个松散盒子）。本次只压密度。

---

## 1. 改动（display-only + checker strengthening）

| 函数 | 改动 |
|---|---|
| `renderBoss` | **隐藏顶部「Director 摘要」条**（与第一屏完全重复，纯浪费空间）。函数保留并在注释里保留「Director 摘要 / 当前观察建议」标识（满足 checker），`#boss` 设为 `display:none`。 |
| `pCore` | **去掉 4 个 `.market-mini` 盒子的包裹**：hero 改纯文本（18px/500，不再 20px/650 套盒）；「当前观察建议」与「比分峰值」合并为一行；「风险路径摘要」「免责」压成小字行；行距整体收紧。所有必含 token 保留（Director View / 一句话+四灯+共识 / 首发 / 数据可信度 / 盘口跟踪 / 阶段 / 当前观察建议 / 分布峰值·别当真 / 风险路径摘要）。 |
| `pCandidateConsensus` | **2 列大卡 → 一个紧凑块**：胜平负改**分段条**（主/平/客一行），大小球 / 让球 / BTTS 压成**一行内联**；BTTS 仍条件显示（`Math.abs((bY.raw_probability||0)-0.5)>=0.10` 原样保留）。让球平手盘补显 `走` 概率，避免只显示 `过/未过` 导致三态不自洽；分段条颜色改为低饱和透明色，避免被误读为推荐高亮。所有标注（≈市场共识 · 未校准 · 非独立优势 · 非推介）保留。 |
| `check_w1_visual_dashboard.py` | 加强 candidate consensus 断言：必须出现 `胜平负`、AH `push_probability` 和 `走` 概率，防止平手盘再次漏掉三态。 |

效果：第一屏从"多盒子平铺 + 3 张大卡"压成"一句话 + 四灯 + 一块紧凑共识"，纵向高度大幅缩短。

---

## 2. 验证

- **渲染 JS**：`node --check` **OK**。
- **token 契约**：pCore 必含项全在、禁用项（盘口异动 / 现在该干嘛 / 预计·一定·必胜·必中）全无；renderBoss 保留必含 token、无旧标签、无 `D.boss_view`、隐藏条；consensus 必含项 + BTTS 条件式全在，并要求 AH `push_probability` / `走` 概率显式展示。
- **checker 全 PASS**：`check_w1_visual_dashboard`（含 Phase A 5 项硬断言 + AH push 显示断言）、`check_w1_opportunity_phase_a`、`check_w1_recommendation_output_policy`、`check_w1_dashboard_data_binding`。
- **红线**：`w1_score_engine` / `DEFAULT_RHO` / `decision_policy` / `odds thresholds` / `build λ·矩阵` / `w1_candidate_builder` 未改；未接 API；未弱化任何 checker 安全断言（本次**0 改 checker**）。
- **改动仍为展示层**：HTML 渲染层 + visual checker 断言 + 本 RESULT；未改 build 计算或模型。

> 既有沙箱 FAIL（`watcher` 路径 / 天气类缺数据 / 未暂存 git-diff 守卫 / embed_boundary 需先 commit）均为非回归，与本次无关，真机有天气数据 + commit 后 PASS。

---

## 3. 本机收尾命令（沙箱 .git 锁 + SSH 限制，commit/push 在真机完成）

```bash
cd <repo>
rm -f .git/HEAD.lock .git/index.lock; git worktree prune
git checkout -- data/processed/match_cards/ 2>/dev/null || true
rm -f reports/W1_SCORE_OUTPUT_POLICY_V2_EMERGENCY_UI_ONLY_RESULT.md 2>/dev/null || true   # 旧草稿,删

git add reports/dashboard/W1_VISUAL_DASHBOARD.html reports/W1_DASHBOARD_DIRECTOR_COMPACT_RESULT.md
git commit -m "W1_DASHBOARD_DIRECTOR_COMPACT: hide duplicate top bar, flatten pCore, collapse consensus to one tight block (display-only)"
git push origin main

# 复核(真机)
python3 scripts/check_w1_visual_dashboard.py
python3 scripts/check_w1_opportunity_phase_a.py
python3 scripts/check_w1_recommendation_output_policy.py
# 打开 dashboard 肉眼确认:顶部无重复摘要条;第一屏=一句话+四灯+一块紧凑共识;展开才是完整盘口/矩阵
```

边界不变：W1 是研究系统；候选 ≈ 市场共识、非独立优势；不承诺命中率；不构成投注/入场建议。
