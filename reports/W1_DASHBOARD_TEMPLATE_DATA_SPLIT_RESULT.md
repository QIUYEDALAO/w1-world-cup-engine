# W1_DASHBOARD_TEMPLATE_DATA_SPLIT — RESULT

**阶段**: W1_DASHBOARD_TEMPLATE_DATA_SPLIT
**日期**: 2026-06-16
**状态**: ✅ 完成（采用 Option 1：确定性内嵌）
**基线 HEAD**: `89c2d30`

---

## 1. 目标与方案选择

登记时该阶段的设想是"让 tracked HTML 不再内嵌数据、改为运行时加载 gitignored JSON"，以阻止 build 反复改脏 HTML。

落地前调查发现一个**方向性约束**：内嵌数据不是意外，而是被 checker 强制的**离线 file-open 功能**——

- `check_w1_visual_dashboard.py` 两处硬断言 `<script id="w1-data" type="application/json">…</script>` 必须存在且 ≥24 条记录，注释明确写着 *"HTML must embed dashboard data for file-open use"*。
- HTML 自身的数据装载逻辑（约 25060 行）先 `fetch('/dashboard-data')`（本地服务器），失败时**回退到内嵌 JSON**，这样双击 `file://` 打开也能渲染。Chrome 禁止 `fetch()` 本地 `file://` 兄弟 JSON——正是当初内嵌的原因。

因此"把数据完全移出 HTML"会**破坏离线打开**并需要**改写 checker 断言**，属于产品取舍而非纯清理。经老板拍板，采用 **Option 1：确定性内嵌（去时间戳）**——保留内嵌与 file-open、不动任何 checker 安全断言，只让内嵌副本对 build 时钟保持确定。

---

## 2. churn 根因（实证，纠正此前假设）

此前 triage 备注称 HTML 因内嵌 `generated_at_utc` 时间戳而变脏。**实测纠正：** `generated_at_utc` 只写进**外部 gitignored JSON**（build 脚本 2600/2677 行），**从未进入内嵌副本**（`public_dashboard_data()` 的返回结构不含该字段）。

用两组实验定位真正的 churn 源：

| 实验 | 内嵌差异 | 结论 |
|---|---|---|
| 连续两次 build（同一 state，相隔 2s） | **0 处** | 内嵌对"同分钟内"的 build 已确定 |
| 一次 build vs 16h 前的 committed 基线 | 第一轮定位到 `staleness_minutes` 是纯时钟字段 | `odds_movement.liquidity.staleness_minutes` 必须从内嵌副本清除 |
| no-op build 验证（连续两次 build 后看 tracked HTML） | 进一步暴露 `lineup_updated_at`、`live_refresh.requested_at`、`live_refresh.modules.*.fetched_at` 会随 runtime state 回写改变 | sanitizer 清单不完整，必须覆盖 embedded runtime timestamp 字段集合 |

`staleness_minutes = int((now − snapshot_capture)/60)`（build 脚本 822 行），按分钟取整，所以任何"比上次提交晚 ≥1 分钟"的 build 都会改脏 tracked HTML 的这 24 个值。它是显示用派生量，把一个"距快照 N 分钟"冻结进提交物本身在重新打开时就是错的。

第一轮只处理了 `staleness_minutes`。按 no-op build 复测后，确认内嵌 payload 还包含运行时回写时间戳：行级 `lineup_updated_at`、`live_refresh.requested_at`、以及 `live_refresh.modules.*.fetched_at`。这些字段同样不应冻结在 tracked HTML 的 file-open 副本中。最终实现改为路径式 sanitizer：只在**内嵌 JSON 副本**中置 null；外部 gitignored `w1_dashboard_data.json` 和 server `/dashboard-data` 仍保留真实 runtime timestamps。

---

## 3. 改动（共 3 个被跟踪文件）

| 文件 | 改动 |
|---|---|
| `scripts/build_w1_dashboard_data.py` | 新增路径式 `strip_volatile_for_embed()`；`update_embedded_html` 内嵌前调用，将 embedded-only runtime 字段置 null：`odds_movement.liquidity.staleness_minutes`、`lineup_updated_at`、`live_refresh.*.requested_at`、`live_refresh.*.fetched_at`、`live_refresh.*.updated_at`。外部 gitignored JSON 与 `/dashboard-data` 实时路径仍保留真实值。 |
| `scripts/check_w1_visual_dashboard.py` | `assert_embed_deterministic()` 断言内嵌每条记录的 `staleness_minutes`、`lineup_updated_at`、`live_refresh` 子树 runtime timestamp 均为 null。**加断言、强化**，不弱化任何安全断言（反向测试：塞入非 null 会触发 FAIL）。 |
| `reports/dashboard/W1_VISUAL_DASHBOARD.html` | 更新内嵌 JSON 副本，使上述 runtime timestamp 字段为 `null`。file-open 离线打开仍保留 24 条 match_records 与完整 UI 数据。 |

JS 侧无需改：服务器模式下从 `/dashboard-data` 取到真实 runtime 值正常显示，离线模式下使用 deterministic embedded copy。冻结的运行时更新时间和"距快照 N 分钟"在 committed file-open 副本里本来就会过期。

---

## 4. 验证

- **确定性证明**：补齐 sanitizer 后连续两次 build，`reports/dashboard/W1_VISUAL_DASHBOARD.html` 不再被 no-op build 改脏。
- **内嵌字段核对**：内嵌 24 条 `staleness_minutes`、行级 `lineup_updated_at`、`live_refresh` 子树 runtime timestamp 均为 `null`；外部 JSON 仍保留真实 runtime 值。
- **直接相关 checker**：`check_w1_visual_dashboard` / `check_w1_dashboard_data_binding` / `check_w1_runtime_artifact_policy` 全 **PASS**。
- **反向测试**：对 `assert_embed_deterministic` 注入非 null → 正确抛 `CheckError`（断言确实生效）。
- **全量 `check_w1_*.py`（沙箱）**：**39 PASS / 3 FAIL**。三处 FAIL 均为非回归：

| FAIL | 原因 | 真机是否 PASS |
|---|---|---|
| `check_w1_watcher` | `w1_watcher.sh` 硬编码 `cd /Users/liudehua/...`（沙箱无此路径） | ✅（真机 PASS） |
| `check_w1_rho_real_ou_calibration` | `git diff --name-only` 命中**未暂存**的 build 脚本改动（protected 文件复现性守卫） | ✅（`git add`/commit 后 PASS） |
| `check_w1_recommendation_accuracy_audit` | 同上，未暂存的 build 脚本改动 | ✅（`git add`/commit 后 PASS） |

> `check_w1_score_matrix` 曾因注释里的英文词含子串 "bet" 被静态扫描误判，已改写措辞，现 PASS。

---

## 5. 红线确认

| 红线 | 状态 |
|---|---|
| 未改 `scripts/w1_score_engine.py` | ✅ |
| `DEFAULT_RHO` 仍为 `-0.057766` | ✅ |
| 未改 `config/w1_decision_policy.json` | ✅ |
| 未改 `config/w1_odds_movement_thresholds.json` | ✅ |
| 未弱化 checker 安全断言（仅新增/强化） | ✅ |
| 未造假数据；未抓取/接 API/爬取 | ✅ |
| 保留 file-open 离线渲染功能 | ✅ |
| 无投注/资金/命中率表达 | ✅ |

---

## 6. 关于 2 张 match card 的说明（非本阶段改动）

跑全量 checker 时，`check_w1_click_to_predict` 与 `check_w1_manual_lineup_override` 会经 predict 路径把 `live_refresh` 写回 2 张源卡（`fixture_1489373`、`fixture_1539001`）。这是**既有的卡片回写 churn**，正是下一阶段 `W1_PREDICT_OVERLAY_SPLIT` 要根治的问题，**与本阶段无关**。已在沙箱把这两张卡恢复到 HEAD。

**交接提醒**：提交时若 `git status` 显示这两张卡被改动（因运行过 checker），请 `git checkout -- <两张卡>` 丢弃，不要纳入本阶段提交。

---

## 7. 是否回滚

**否。** 确定性达成、file-open 保留、全部安全断言保留并强化，无需回滚。

---

## 8. 本机收尾命令（沙箱 .git 锁 + SSH 限制，commit/push 在真机完成）

> 注：工作目录即真实文件夹，3 个文件已在盘上改好，真机只需提交。

```bash
cd <repo>
rm -f .git/HEAD.lock .git/index.lock; git worktree prune
# 丢弃 checker 运行时回写的源卡（如有），保证只提交本阶段 3 文件 + 文档
git checkout -- data/processed/match_cards/group_stage_round1/fixture_1489373_qatar_vs_switzerland.json \
                data/processed/match_cards/group_stage_round1/fixture_1539001_australia_vs_t-rkiye.json 2>/dev/null || true

# commit 1/2：代码 + HTML（确定性内嵌 + 强化 checker）
git add scripts/build_w1_dashboard_data.py scripts/check_w1_visual_dashboard.py reports/dashboard/W1_VISUAL_DASHBOARD.html
git commit -m "W1_DASHBOARD_TEMPLATE_DATA_SPLIT (1/2): deterministic embed, file-open intact"

# commit 2/2：文档
git add reports/W1_DASHBOARD_TEMPLATE_DATA_SPLIT_RESULT.md docs/W1_RUNTIME_ARTIFACT_POLICY_V1.md reports/W1_EXPERT_PROJECT_REPORT.md
git commit -m "W1_DASHBOARD_TEMPLATE_DATA_SPLIT (2/2): RESULT + policy/registry update"

git push origin main

# 复核（真机应全 PASS）
python3 scripts/check_w1_visual_dashboard.py
python3 scripts/check_w1_rho_real_ou_calibration.py
python3 scripts/check_w1_recommendation_accuracy_audit.py
# 验证 no-op 干净：连跑两次 build，第二次后 git status 应不含 tracked HTML
W1_DISABLE_API_ENV_BRIDGE=1 python3 scripts/build_w1_dashboard_data.py
W1_DISABLE_API_ENV_BRIDGE=1 python3 scripts/build_w1_dashboard_data.py
git status --short reports/dashboard/W1_VISUAL_DASHBOARD.html   # 期望：空
```

---

## 9. 下一阶段

"运行后 git 仍 clean" 现在只差**一处**：`W1_PREDICT_OVERLAY_SPLIT`——`predict`/`build` 仍把 `live_refresh` 写回被跟踪的源卡。治本=运行态写到单独 gitignored overlay，不碰源卡。本阶段已完成 HTML 一侧。

边界不变：概率建模与赛前/赛后研究；不是投注平台，不输出资金建议，不承诺命中率，不把模型-市场分歧表述为投注机会。
