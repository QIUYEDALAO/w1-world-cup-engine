# W1_PREDICT_OVERLAY_SPLIT_V1 — RESULT

**阶段**: W1_PREDICT_OVERLAY_SPLIT_V1
**日期**: 2026-06-16
**状态**: ✅ 完成
**基线 HEAD**: `4b9feca`
**范围（老板拍板）**: B + results；"冻结源卡 + overlay 合并"，不清回人工原版；确认首发过滤逻辑迁到 build 内存执行。

---

## 1. 目标

predict 此前把三类运行态写回**被跟踪的源卡**，每次 predict/checker 都把卡跑脏：

- `live_refresh`（`write_live_refresh_to_card`）
- `lineups` + 确认首发时过滤 `risk_flags`/`data_gaps`/`decision.reasons`（`write_lineups_to_card`）
- 赛果 `status`/`actual_score`/…（`write_result_to_card`）

治本：predict 只写 **gitignored overlay** 和 **tracked 事实账本**；build 在内存合并；源卡冻结、永不被 predict 改。

---

## 2. 落地中确认的关键事实（让方案更安全）

- 人工确认首发的真源在**卡外**：`data/manual_lineups/*.json`（tracked，2 个），build 的 `apply_manual_lineup_override` 用稳定 `as_of_utc` 在内存覆盖卡——**已经在 build 做了** risk/gaps 的确认过滤。所以"过滤迁到 build"大半已存在，只需补 runtime overlay 路径。
- 赛果只从 overlay 读：`status_for_fixture`/`actual_score_for_fixture`/`result_source` 全部来自 `result_overlay()`（`data/results/round1_results.json`），**build 从不读卡里的 result 字段** → 清掉卡里的 result 字段绝对安全。
- build **从不读** `card["decision"]["reasons"]["counter_factors"]`（build 的 counter_factors 来自 `risk_flags`）→ predict 当年对 decision.reasons 的过滤纯属卡内 cosmetic，安全丢弃。
- live_refresh overlay 已存在（`state/w1_live_refresh_state.json`），predict 早已**双写** overlay + 卡 → 去掉卡写零损失。

---

## 3. 改动

### predict（`scripts/w1_local_predict_server.py`）
- **删** `write_live_refresh_to_card`、`write_result_to_card`（连同其 card 写）。
- `write_lineups_to_card` → **`write_lineups_overlay`**（+ 抽出 `build_lineups_runtime`）：写 gitignored `state/w1_lineup_runtime_overlay.json`（按 fixture），不写卡，不再就地改 risk/gaps/decision。
- live_refresh 收尾只保留 `write_live_refresh_state`（overlay）；赛果同步只保留 `write_result_overlay`（写 tracked `round1_results.json` 事实账本）。
- `refresh_lineups` 两处调用改 `write_lineups_overlay`；进度文案改"写 runtime overlay（不回写源卡）"。
- 实测：predict 源码已无任何 `card[...] =` 赋值、无 `write_json(path, card)`。

### build（`scripts/build_w1_dashboard_data.py`）
- 新增常量 `LINEUP_RUNTIME_OVERLAY`、`lineup_overlay_cache()`、`apply_runtime_lineup_overlay()`（镜像 `apply_manual_lineup_override` 的确认过滤；**人工源**`manual_lineup_fixture_id` 优先，仅在无人工源时合并 runtime overlay）。
- `build_record`：`apply_manual_lineup_override` 之后调用 `apply_runtime_lineup_overlay`；live_refresh 改 **overlay 优先**（`live_refresh_by_fixture.get(fid) or card.get(...) or default`）。
- `main()` 读取并下传 `lineup_overlay_by_fixture`。

### 源卡一次性清理（仅去运行时冗余，逐字段核对）
- 8 张去 `live_refresh`（纯运行时）。
- 4 张去 `status`/`actual_score`/`actual_score_display_cn`/`result_source`/`result_note`/`result_synced_at_utc`（均镜像在 tracked `round1_results.json`，dry-run 确认 0 张脱离 overlay）。
- `lineups`/`decision`/`risk_flags`/`data_gaps` **冻结不动**。
- 核验：每张改动卡 == HEAD 去掉对应键，**逐字节一致**（diff 仅这些键，无其它改动）。

### checker
- **新增** `scripts/check_w1_predict_overlay_split.py`（静态强约束 + skip-safe）：predict 无源卡写函数/写法、源卡无运行时字段、overlay gitignored、事实账本 tracked、build 有 overlay 合并接线。注册 §7。
- 更新 `check_w1_click_to_predict`（token→`write_lineups_overlay`）、`check_w1_lineup_api_binding`（断言写 overlay 而非卡）、`check_w1_post_match_result_sync`（断言赛果在 overlay、源卡**不得**带 result 字段；slice 边界改 `write_result_overlay`）。均为**强化**，未弱化安全断言。

---

## 4. 验证

- **零卡写实证**：对真实 `/predict`（`check_w1_manual_lineup_override` 跑 1539001、`check_w1_click_to_predict` 跑 1489373）前后，24 张卡组合 md5 **完全一致**（`74fea98…`）→ predict 确实不再碰源卡。两个 checker 均 **PASS**（端到端：predict→overlay→build→dashboard 正确，1539001 仍显示 manual_verified 确认首发，1489373 仍 verified_fallback 确认）。
- **新 checker** PASS。
- **build 对 purged 卡仍产出有效 dashboard**：24 条；8 场完赛比分来自 overlay（2-0/4-1/1-1/…）；qatar 确认首发被冻结保留（4-3-3 / 3-4-2-1）；`check_w1_dashboard_data_binding` / `check_w1_visual_dashboard` PASS。
- **全量 `check_w1_*`（沙箱，排除 2 个 server checker 单独验证）**：38 PASS / 3 FAIL，三处均为非回归：

| FAIL | 原因 | 真机 |
|---|---|---|
| `check_w1_watcher` | `w1_watcher.sh` 硬编码真机路径 | ✅ PASS |
| `check_w1_rho_real_ou_calibration` | `git diff` 命中**未暂存**的 build 脚本（复现性守卫，仅列 `build_w1_dashboard_data.py`） | ✅ commit 后 PASS |
| `check_w1_recommendation_accuracy_audit` | 同上 | ✅ commit 后 PASS |

- **上一阶段确定性内嵌未被破坏**：连续两次 build，内嵌一致、`staleness_minutes` 仍全 null。

> 说明：`git diff` 会显示 8 张卡有改动——那是**本阶段第 3 节的一次性清理**（相对 HEAD），不是 predict 弄脏；predict 前后卡 md5 不变已证明这一点。

---

## 5. 红线确认

| 红线 | 状态 |
|---|---|
| 未改 `scripts/w1_score_engine.py` | ✅ |
| `DEFAULT_RHO` 仍为 `-0.057766` | ✅ |
| 未改 `config/w1_decision_policy.json` | ✅ |
| 未改 `config/w1_odds_movement_thresholds.json` | ✅ |
| 未弱化 checker 安全断言（仅新增/强化） | ✅ |
| 未造假数据；源卡只**减运行时冗余**、未改人工内容 | ✅ |
| 未新增抓取/接 API/爬取（build 仍无网络导入） | ✅ |
| 无投注/资金/命中率表达 | ✅ |

---

## 6. 是否回滚

**否。** 零卡写已实证、dashboard 输出有效、全部安全断言保留并强化。

---

## 7. 本机收尾命令（沙箱 .git 锁 + SSH 限制，commit/push 在真机完成）

> 工作目录即真实文件夹，改动已在盘上。提交前若 `git status` 显示 HTML/`round1_results.json` 被跑脏（因运行过 server checker），按需 `git checkout --` 丢弃——本阶段不改它们。

```bash
cd <repo>
rm -f .git/HEAD.lock .git/index.lock; git worktree prune
git checkout -- reports/dashboard/W1_VISUAL_DASHBOARD.html 2>/dev/null || true   # 若被 checker 跑脏

# commit 1/3：predict + build 的 overlay 拆分 + checker（新增/更新）
git add scripts/w1_local_predict_server.py scripts/build_w1_dashboard_data.py \
        scripts/check_w1_predict_overlay_split.py scripts/check_w1_click_to_predict.py \
        scripts/check_w1_lineup_api_binding.py scripts/check_w1_post_match_result_sync.py
git commit -m "W1_PREDICT_OVERLAY_SPLIT_V1 (1/3): predict writes overlays/ledger only; build merges; cards frozen"

# commit 2/3：源卡一次性清理（仅去运行时冗余）
git add data/processed/match_cards/group_stage_round1/
git commit -m "W1_PREDICT_OVERLAY_SPLIT_V1 (2/3): purge runtime fields (live_refresh/result) from source cards"

# commit 3/3：RESULT + 政策/§7
git add reports/W1_PREDICT_OVERLAY_SPLIT_V1_RESULT.md docs/W1_RUNTIME_ARTIFACT_POLICY_V1.md reports/W1_EXPERT_PROJECT_REPORT.md
git commit -m "W1_PREDICT_OVERLAY_SPLIT_V1 (3/3): RESULT + policy/registry update"

git push origin main

# 复核（真机应全 PASS）
python3 scripts/check_w1_predict_overlay_split.py
python3 scripts/check_w1_rho_real_ou_calibration.py
python3 scripts/check_w1_recommendation_accuracy_audit.py
# 零卡写复证：跑一次 /predict 后源卡应无 diff
python3 scripts/check_w1_manual_lineup_override.py
git status --porcelain data/processed/match_cards/   # 期望：空（无新改动）
```

---

## 8. 仓库卫生收尾

两处运行态污染源已全部根治：
- HTML 内嵌时间戳 churn → `W1_DASHBOARD_TEMPLATE_DATA_SPLIT`（确定性内嵌）。
- predict 把 live_refresh/lineups/results 写回源卡 → 本阶段（overlay 拆分）。

**"任意 predict/build/checker 运行后，被跟踪的源卡与 HTML 保持 clean" 现已达成。** runtime 全部落在 gitignored overlay（`state/`）与 tracked 事实账本（`round1_results.json`，仅在有新赛果时变化）。

边界不变：概率建模与赛前/赛后研究；不是投注平台，不输出资金建议，不承诺命中率，不把模型-市场分歧表述为投注机会。
