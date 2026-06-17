# W1 FiveDim Lite · 阶段 A 验收 + 阶段 B 结果（专家侧）

**日期**: 2026-06-17
**分工**: 阶段 A（A1–A5）由**技术员**完成；阶段 A **验收** + 阶段 B（dashboard 展示）由**我**完成。
**我改的被跟踪文件只有 2 个**：`reports/dashboard/W1_VISUAL_DASHBOARD.html`、`scripts/check_w1_visual_dashboard.py`。**未碰技术员任何 FiveDim 文件。**

---

## 1. 阶段 A 验收（技术员产物，我复核）→ PASS

技术员 04:02–04:09 完成全套并已 build：

| 产物 | 状态 |
|---|---|
| `schemas/w1_fivedim_card_schema.json` | ✅ basis/availability 枚举、leaf 形、hard_rules 齐 |
| `config/w1_fivedim_lite_policy.json` | ✅ 来源映射、`post_match_only_blacklist`、`forbidden_terms`、降级规则 |
| `scripts/w1_fivedim_lite.py` | ✅ 只读；market_view 复用 `w1_candidate_builder`；四维如实抽取/标缺失；无网络 |
| `scripts/check_w1_fivedim_lite.py` | ✅ 3 项反向测试（post_match / forbidden_term / independent_edge）+ 红线 git-diff + no-network-import |
| `reports/W1_FIVEDIM_LITE_STAGE_A_IMPLEMENTATION.md` | ✅ |
| `state/w1_fivedim_lite_cards.json` | ✅ 24 卡（gitignored，无 churn） |

**复核结果**：确定性重建 24 卡；`check_w1_fivedim_lite` **PASS**；既有 `check_w1_visual_dashboard / check_w1_opportunity_phase_a / check_w1_recommendation_output_policy` **不回归**。

**7 处修正对照**：C1 market_view 复用候选层 ✅；C2 四维如实为空不造值 ✅；C3 离线无网络 ✅；C4 post_match 黑名单硬断言+反向测试 ✅；C5 禁投注词复用+反向测试 ✅；C6 输出落 gitignored `state/`，未起平行账本 ✅；C7 全维 `independent_edge=false` ✅。

**就绪度实测（印证"只有市场维是满的"）**：

| 维度 | available | degraded | missing |
|---|---|---|---|
| market | 24 | 0 | 0 |
| strength | 0 | 0 | 24 |
| tactical | 0 | 17 | 7 |
| chemistry | 0 | 17 | 7 |
| environment | 0 | 0 | 24* |

\* environment 实际场地/海拔/顶棚字段是 available，仅天气缺——见 §4 第 2 条 bug。

---

## 2. 阶段 B（我做，纯展示，1 行）

在紧凑 Director View（chip 版 pCore）四灯下方加**一行诚实"五维就绪度"**，从记录自身字段派生，不接五维卡、不改 build：

```
五维就绪度 · 市场 ✓ 环境 ◐ 阵型 ◐ 实力 未接入 战术 未接入
```

- ✓就绪 / ◐部分 / 未接入；hover 标题写明"市场维=市场隐含再表达；非独立优势·未校准·非推介"。
- **刻意不摆五维灯**：四维大多空，五盏灰灯比不显示更糟、且有"假装有五维"之嫌——所以只用一行如实标"未接入"。
- market 由 `candidates_snapshot.items` 判；env 由 `environment_context.venue_name`+`weather_status` 判（故显 ◐，比五维卡的 missing 更准）；阵型由 `confirmed_lineup_available` 判。

**强化(只增不减)**：`check_w1_visual_dashboard.py` 的第一屏必含 token 加入 `五维就绪度`。

**验证**：render JS `node --check` **OK**（新增嵌套模板字面量合法）；`check_w1_visual_dashboard` / `check_w1_recommendation_output_policy` / `check_w1_opportunity_phase_a` **PASS**。

---

## 3. 红线确认

未改 `w1_score_engine.py` / `DEFAULT_RHO` / `build_w1_dashboard_data.py` 的 λ·矩阵 / `w1_decision_policy.json` / `odds thresholds` / 技术员 FiveDim 文件；未接 API、无网络；未弱化任何安全断言（仅 strengthen）；B 输出无投注语言。我改的被跟踪文件 = 2 个（dashboard + 其自带 checker）。

---

## 4. 交给技术员的 2 件事（你转他；我没并发改他的文件）

**① `check_w1_fivedim_lite.py` 把 dashboard 移出红线清单。**
该 checker 的 `REDLINE_PATHS` 含 `reports/dashboard/W1_VISUAL_DASHBOARD.html`（Stage A 假设"不改 dashboard"）。阶段 B 合法地改了它，故现在该 checker 报 `redline file has local diff: …W1_VISUAL_DASHBOARD.html`。
- 处理：从 `REDLINE_PATHS` 删掉这一行。dashboard 仍由 `check_w1_visual_dashboard.py` 守护（且现在也要求 `五维就绪度` token）。
- 注：**B 提交后** `git diff` 对 HEAD 自然 clean，该 checker 即使不改也会 PASS；删这行是为了将来 dashboard 合法变更不再被 Stage A checker误拦。

**② `environment_view` 就绪度被低报。**
24 场全标 `missing`，但 `venue_name/city/country/altitude_m/roof_status` 实为 `available`（仅 `weather`/`rest_days` 缺）。应为 `degraded`（或在 schema `availability_enum` 加 `partial` 后用 `partial`）。属低报真实数据，非红线问题。B 的就绪度条已用同源字段正确显示 环境 ◐。

---

## 5. round1_results.json 是真实赛果，**不要还原**

working tree 里 `data/results/round1_results.json` 被改动，内容是**新增 fixture 1489383 法国 3:1 塞内加尔（finished，今日 00:06Z 同步）**——就是你截图那场。这是正常赛后回填，**保留**，建议**单独一条 commit**，别混进 FiveDim 提交。

---

## 6. 本机收尾命令（沙箱 .git 锁 + SSH 限制，真机提交）

```bash
cd <repo>
rm -f .git/HEAD.lock .git/index.lock; git worktree prune
rm -f reports/W1_SCORE_OUTPUT_POLICY_V2_EMERGENCY_UI_ONLY_RESULT.md 2>/dev/null || true   # 旧草稿

# commit 1：真实赛果（单独）
git add data/results/round1_results.json
git commit -m "data: sync round1 result France 3-1 Senegal (fixture 1489383)"

# commit 2：FiveDim Lite 阶段A（技术员产物 + 阶段0）
git add schemas/w1_fivedim_card_schema.json config/w1_fivedim_lite_policy.json \
        scripts/w1_fivedim_lite.py scripts/check_w1_fivedim_lite.py \
        scripts/check_w1_fivedim_data_support_report.py \
        reports/W1_FIVEDIM_DATA_SUPPORT_VALIDATION.md reports/W1_FIVEDIM_LITE_STAGE_A_IMPLEMENTATION.md \
        reports/W1_FIVEDIM_LITE_STAGE_A_SPEC.md
git commit -m "W1_FIVEDIM_LITE Stage A: read-only five-dim card + checker (market wraps candidate builder, 4 dims honest-missing)"

# commit 3：阶段B 展示 + checker 强化 + 验收报告
git add reports/dashboard/W1_VISUAL_DASHBOARD.html scripts/check_w1_visual_dashboard.py \
        reports/W1_FIVEDIM_LITE_STAGE_B_RESULT.md
git commit -m "W1_FIVEDIM_LITE Stage B: honest five-dim readiness strip in Director View (display-only)"

git push origin main

# 真机复核
python3 scripts/check_w1_fivedim_lite.py          # 删了 dashboard 红线行 → PASS；或提交后本就 PASS
python3 scripts/check_w1_visual_dashboard.py       # PASS（含 五维就绪度）
python3 scripts/check_w1_opportunity_phase_a.py    # PASS
# 打开 dashboard 肉眼确认：四灯下方多一行"五维就绪度"，市场✓ 其余部分/未接入
```

---

## 7. 边界与下一步

边界不变：W1 是研究系统；FiveDim Lite 仅市场维满、其余如实为空；非独立优势·未校准·非推介。
**封锁项仍封锁**：阶段 C（历史验证，需先离线历史样本盘点）、D（confidence 调整）、E（λ 因子）、F（Primary Read Selector）——未经历史验证 + 新授权不动。
