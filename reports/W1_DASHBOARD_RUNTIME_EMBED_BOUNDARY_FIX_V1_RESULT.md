# W1_DASHBOARD_RUNTIME_EMBED_BOUNDARY_FIX_V1_RESULT

日期：2026-06-16

## 1. 问题复现

在 `origin/main` HEAD=`3349983` 上：

- `git status` clean。
- `check_w1_visual_dashboard.py` PASS。
- `check_w1_dashboard_data_binding.py` PASS。
- `W1_DISABLE_API_ENV_BRIDGE=1 python3 scripts/build_w1_dashboard_data.py` 成功。
- 但 `reports/dashboard/W1_VISUAL_DASHBOARD.html` 变 dirty。

本轮 diff 已确认不是上一阶段的 `staleness_minutes` timestamp churn，而是 tracked HTML 的 embedded JSON 吸收了本地 runtime/environment state：

- `lineup_confirmed_utc`
- `lineups.confirmed_utc`
- `environment_context.weather_*`
- `live_refresh.modules.*.status/message`
- odds snapshot runtime message 中的 `records=...`

## 2. 根因

`W1_DASHBOARD_TEMPLATE_DATA_SPLIT` 只做了字段级 timestamp sanitizer。它解决了 build wall-clock 字段进入 embedded HTML 的问题，但没有从来源层面隔离：

- `state/` runtime overlays
- local weather cache
- live_refresh runtime state
- runtime lineup overlay

因此，只要本地 runtime state 变化，external JSON 和 tracked HTML 会共同吸收该状态。

## 3. 本阶段修复

在 `scripts/build_w1_dashboard_data.py` 中明确拆分两种 record 构造：

- runtime payload：`include_runtime_state=True`
  - 写入 gitignored `reports/dashboard/assets/w1_dashboard_data.json`
  - 可保留 weather / live_refresh / runtime lineup overlay
  - server `/dashboard-data` 路径继续读 runtime payload

- embedded payload：`include_runtime_state=False`
  - 写入 tracked `reports/dashboard/W1_VISUAL_DASHBOARD.html`
  - 不读取 weather cache
  - 不读取 live_refresh state
  - 不合并 runtime lineup overlay
  - non-manual lineup confirmed timestamps 归空
  - live_refresh 使用 stable idle baseline

tracked HTML 仍保留 file-open 能力，但只承载稳定 embedded baseline。

## 4. Checker

新增：

```text
scripts/check_w1_dashboard_runtime_embed_boundary.py
```

该 checker 验证：

- build 前 tracked HTML 必须 clean。
- 在本地 runtime/weather/lineup state 存在时运行 build。
- build 后 tracked HTML 仍 clean。
- embedded JSON 仍存在且 `match_records >= 24`。
- embedded JSON 不含 runtime weather state。
- embedded JSON 不含 live_refresh runtime status/message/timestamps。
- embedded JSON 不含 runtime overlay 派生的 non-manual lineup confirmed timestamps。
- external runtime JSON 仍可保留 runtime state。

## 5. 验证结果

阶段内已先生成一次 stable embedded baseline，并提交该稳定基线。随后从 clean HEAD 复跑：

```text
python3 scripts/check_w1_visual_dashboard.py
python3 scripts/check_w1_dashboard_data_binding.py
W1_DISABLE_API_ENV_BRIDGE=1 python3 scripts/build_w1_dashboard_data.py
git status --short reports/dashboard/W1_VISUAL_DASHBOARD.html
python3 scripts/check_w1_dashboard_runtime_embed_boundary.py
python3 scripts/check_w1_runtime_artifact_policy.py
python3 scripts/check_w1_predict_overlay_split.py
python3 scripts/check_w1_forward_prospective_run.py
```

目标状态：

- build 后 `reports/dashboard/W1_VISUAL_DASHBOARD.html` 不再 dirty。
- `check_w1_dashboard_runtime_embed_boundary.py` PASS。

## 6. 红线确认

未修改：

- `scripts/w1_score_engine.py`
- `DEFAULT_RHO`
- `config/w1_decision_policy.json`
- `config/w1_odds_movement_thresholds.json`
- 推荐比分算法
- 生产模型

未执行：

- 未抓取数据。
- 未接新模型。
- 未 untrack `W1_VISUAL_DASHBOARD.html`。
- 未放弃 file-open。
- 未接 dashboard sidecar。
- 未把 dirty HTML 直接作为 runtime 更新提交。

## 7. 阶段结论

上一阶段 deterministic embed 解决 timestamp churn。本阶段解决 runtime/environment state 被烤进 tracked HTML 的来源边界问题。

最终边界：

- tracked HTML：稳定 file-open embedded baseline。
- gitignored external JSON / state / server：runtime/weather/live_refresh state。
- dashboard 推荐比分算法未变。
- 生产模型未变。
