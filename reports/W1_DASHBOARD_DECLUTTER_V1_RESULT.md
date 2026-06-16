# W1_DASHBOARD_DECLUTTER_V1 — RESULT

**类型**: dashboard 三层重排 · **纯展示层（display-only）**
**日期**: 2026-06-17
**范围**: 只改展示。**不改模型、不改 build 计算逻辑、不接 API、不改 `DEFAULT_RHO`。**

> 目标：解决"数据多到分不清有效/无效"。根因——页上 ~80% 数字是同一份市场赔率反解的不同切片。重排成三层:第一屏只放"独立信息 + 一句市场结论",其余下沉。

---

## 1. 三层结构

**第一层 · 一眼决策（`pCore`，主卡第一屏，6 块）**
1. 谁占优·多大（参考倾向 + 主胜/平/客胜 + 最可能净胜区间）
2. 进球多/少（μ 判定 + 总进球区间 + 大小球 O2.5）
3. 首发（已确认/未确认 灯）
4. **数据可信度**（灯：可用/偏弱/不可靠，来自 `odds_movement.status` + 盘口快照新旧/家数）— 这页该不该信
5. **盘口异动**（稳定/在动/异动，来自 `odds_movement`）— 唯一"市场在变"的独立信号
6. 现在该干嘛（阶段 + 动作）

+ **弱化比分行**（按老板要求保留但不做焦点）：小字「主比分 X-X（n%）· 备选比分 Y-Y（m%）— 分布峰值·参考·别当真·单格概率天然低」。
+ 风险路径摘要（开放/冷门）一行 + 一句诚实提示"本页多为同一市场判断的不同切片，真正独立的信息＝首发/数据可信度/盘口异动/进球与净胜区间"。

**第二层 · 点开看（既有"专家视图"折叠区）**：完整盘口面板 1X2/大小球/让球/BTTS、场景质量、比赛环境、阵容/战术效应、赛后校准。

**第三层 · 审计/调试（同折叠区尾部）**：完整比分矩阵、Top 8、市场 vs 模型（fit≈0，构造必然）、抓取状态、数据质量内部字段。

**左侧列表**：保留峰值比分但不裸露——`主 X-X` + `总进球 <区间>`（赛后行仍 `终 X-X` + 方向/完全命中）。

---

## 2. 改动（仅 2 个被跟踪文件）

| 文件 | 改动 |
|---|---|
| `reports/dashboard/W1_VISUAL_DASHBOARD.html` | 重写 `pCore` 为第一层一眼决策（6 块 + 弱化比分行 + 风险路径摘要 + 诚实提示）；`renderRail` 左侧加总进球区间。数据全取已有 `safe_view`/`market_probability_panel`/`odds_movement`/`score_matrix_summary`；可信度/异动复用既有 `marketStateCn`/`pMarketStateBar`。**未改 build 计算。** |
| `scripts/check_w1_visual_dashboard.py` | 新增 `assert_first_screen()`：硬断言第一屏含 谁占优/进球/首发/数据可信度/盘口异动/现在该干嘛；比分行必须带 `分布峰值`+`别当真` 标注；左侧必须含 `most_likely_band`。**加强，不弱化安全断言**（反向测试：缺块即抛 `CheckError`）。 |

---

## 3. 验证

- **渲染 JS**：`node --check`（37KB 渲染脚本）**OK**。
- **内容核对**：第一屏 6 块齐、比分行带"分布峰值·别当真"、左侧峰值比分 + 总进球区间。
- **policy token 保留**：`主比分`/`备选比分`/`风险路径摘要`/`recommendation_view`/`市场复述` 均在；`风险路径`与`推荐`之间有 `</b>` 隔断，不触发 `recommendation_output_policy` 的误判正则。
- **直接相关 checker PASS**：`check_w1_visual_dashboard`（含新断言）、`check_w1_recommendation_output_policy`、`check_w1_dashboard_data_binding`、`check_w1_runtime_artifact_policy`。
- **反向测试**：`assert_first_screen` 缺块 → 抛 `CheckError`。
- **本阶段 0 回归**。其余沙箱 FAIL（`watcher` 路径 / 天气类 `environment_context`·`weather_integration`·`click_to_predict` 缺天气-实时 token / `dashboard_runtime_embed_boundary` 要求先 commit）均为**既有非回归**，与本展示改动无关，真机有天气数据 + commit 后 PASS。

---

## 4. 红线确认

| 红线 | 状态 |
|---|---|
| 未改 `scripts/w1_score_engine.py` / `DEFAULT_RHO` | ✅ |
| 未改 `scripts/build_w1_dashboard_data.py`（build 计算逻辑） | ✅ |
| 未改 `config/*`（decision_policy / odds thresholds） | ✅ |
| 未接 API / 未抓数据 / 未做 factor lambda | ✅ |
| 未弱化 checker 安全断言（仅新增/强化） | ✅ |
| 无投注/资金/命中率表达 | ✅ |
| 改动仅 2 文件，纯展示层 | ✅ |

---

## 5. 本机收尾命令（沙箱 .git 锁 + SSH 限制，commit/push 在真机完成）

```bash
cd <repo>
rm -f .git/HEAD.lock .git/index.lock; git worktree prune
git checkout -- data/processed/match_cards/ 2>/dev/null || true          # 丢弃 checker 跑出的源卡改动(如有)
rm -f reports/W1_SCORE_OUTPUT_POLICY_V2_EMERGENCY_UI_ONLY_RESULT.md 2>/dev/null || true  # 撤回阶段的草稿,删掉

git add reports/dashboard/W1_VISUAL_DASHBOARD.html scripts/check_w1_visual_dashboard.py
git commit -m "W1_DASHBOARD_DECLUTTER_V1: three-tier main card (一眼决策 first screen), score kept as weakened reference, left list adds 形态/区间 (display-only)"

git add reports/W1_DASHBOARD_DECLUTTER_V1_RESULT.md reports/W1_EXPERT_PROJECT_REPORT.md
git commit -m "W1_DASHBOARD_DECLUTTER_V1: RESULT + registry"

git push origin main

# 复核(真机)
python3 scripts/check_w1_visual_dashboard.py
python3 scripts/check_w1_recommendation_output_policy.py
# 打开 dashboard 肉眼确认:第一屏 6 块 + 小字比分;点开"专家视图"才是完整盘口/矩阵
```

---

## 6. 后续（已登记，本次不做）

- 第二/三层若想做成**两个独立折叠块**（而非现有单一"专家视图"），可另开小阶段（纯展示）。
- 验证两天后，结合实际命中/方向/区间表现，决定第一屏要不要再调。
- 独立因子方向仍按 `W1_FACTOR_LAMBDA_DATA_INVENTORY_V1`（先盘点本地数据，无数据不硬做）/ `W1_FACTOR_LAMBDA_MODEL`（研究 prototype，跑赢市场前不动引擎）；API 暂不接。

边界不变：W1 是概率建模与赛前/赛后研究系统；不是投注平台，不输出资金建议，不承诺命中率，不把模型-市场分歧表述为投注机会。
