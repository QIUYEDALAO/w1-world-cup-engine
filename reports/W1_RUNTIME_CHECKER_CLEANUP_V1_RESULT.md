# W1_RUNTIME_CHECKER_CLEANUP_V1 RESULT

生成时间：2026-06-16 CST
执行口径：清理既有/运行时 checker 失败；不造绿、不改模型、不重置真实运行态。

## 1. Baseline

开工基线全量 checker：

- total: 41
- failed: 9
- skipped: 2

9 个失败项与 BOSS 确认清单一致：

1. `check_w1_click_to_predict.py`
2. `check_w1_early_prediction_mode.py`
3. `check_w1_environment_context.py`
4. `check_w1_post_match_calibration.py`
5. `check_w1_post_match_result_update.py`
6. `check_w1_report_templates.py`
7. `check_w1_round1_real_fixture_cards.py`
8. `check_w1_watcher.py`
9. `check_w1_weather_integration.py`

修复后又暴露 2 个同类旧口径交叉失败：

- `check_w1_dashboard_data_binding.py`: `result_source` 仍硬锁旧 sample source。
- `check_w1_manual_lineup_override.py`: smoke 复用固定端口/可读取本地 env bridge，等待窗口也不足。

这 2 项与本阶段目标同源，已纳入 commit 1。

## 2. 逐项分诊与处理

| checker | 分类 | 原因 | 处理方式 | 是否真实数据错误 |
|---|---|---|---|---|
| `click_to_predict` | A | `v4-football/api_keys.sh` / `v4_daily_scan.env` 是 env bridge 路径，被旧 V4 子串规则误伤；HTML 旧 token 也漂移 | 改 checker：逐行扫描，允许明确 env bridge 路径；旧系统真实入口仍 FAIL；dashboard 改为端点/关键 UI token group；smoke 加 `W1_DISABLE_API_ENV_BRIDGE=1` | 否。另发现 checker smoke 会读 env bridge，已修成离线验证 |
| `early_prediction_mode` | A | dashboard 把 `W1_PLAY_GUARD_V1` 翻译为“正式风控规则” | 改 checker：HTML 接受中文翻译形态，同时 policy 仍必须保留 canonical token | 否 |
| `post_match_result_update` | A | `Türkiye` 是合法现代拼写；result shape/source 从 manual 旧字段演进到 API sync 字段 | 改 checker：team alias 归一；actual_score 支持 dict/string；result_source 接受合法来源；不把 Türkiye 回退为 Turkey | 否 |
| `post_match_calibration` | A | build 字段已从 `auto_miss_reason_tags/auto_lesson_cn` 演进为 `miss_reason_tags/lesson_cn`；HTML “命中类型” token 漂移 | 改 checker：对齐当前字段；fixture 样本在 dashboard data 校验；hit type 校验合法枚举；HTML token group 支持 `prediction_hit_type` | 否 |
| `environment_context` | B | 实际 HTML 存在环境模块，但标签从“球场：/环境风险：/解读：”漂移为“场馆/风险/环境仅作为辅助风险” | 先查 HTML/data；确认为 token 漂移；改 checker token group。未补模板 | 否 |
| `weather_integration` | B | 实际 HTML/data/server 均有天气/环境信息；“查询比赛环境/天气”“降雨概率/降雨量”旧 token 漂移 | 先查 HTML/data/progress；确认为 token 漂移；改 checker token group。未补模板 | 否 |
| `round1_real_fixture_cards` | C | 1538999 当前 `W1_PLAY` 是真实运行态，旧 checker 固定要求 24 张全是 `W1_WAIT` | 改 checker：验证 allowed enum 与状态自洽；`W1_PLAY` 必须 confirmed lineup + `W1_PLAY_GUARD_V1`；`W1_WAIT` 必须解释等待/阻塞条件；不重置 1538999 | 否 |
| `report_templates` | C | `W1_LIVE_DASHBOARD.md` 是运行态/模板输出，不应硬锁当前 state 的 `next_run_cst` 字符串 | 改 checker：验证必需区块、字段、decision count 结构、next_refresh 格式和模板 token，不锁旧快照文本 | 否 |
| `watcher` | C | `next_run_cst` 是运行时状态；本地 repo 已配置 origin remote | 改 checker：验证 CST 格式、refresh 小时、与 last_refresh 的可解释窗口；remote 若存在必须指向当前 W1 repo；仍检查 dry-run 0 API calls 和 pushed=false | 否 |

交叉修复：

| checker | 分类 | 原因 | 处理方式 | 是否真实数据错误 |
|---|---|---|---|---|
| `dashboard_data_binding` | A | post-match source 已可来自 API sync，不再只来自旧 sample source | 改 checker：source 域放宽为合法来源，比分和 calibration 字段仍严格验证 | 否 |
| `manual_lineup_override` | A | smoke 使用固定端口并可能复用已有 server；未禁用 env bridge，等待窗口偏短 | 改 checker：使用临时端口、禁用 env bridge、清 key env、延长等待；仍验证 manual lineup source 和 11 人首发 | 否 |

## 3. B 类实物检查结论

- `environment_context`: `reports/dashboard/W1_VISUAL_DASHBOARD.html` 中存在 `比赛环境`、`场馆`、`城市`、`天气`、`温度`、`湿度`、`风速`、`海拔`、`environment_context`；不是元素缺失，是中文标签 token 漂移。
- `weather_integration`: HTML/data/server/progress 中存在天气接入、Open-Meteo、温度/湿度/风速/海拔/降雨概率等结构；不是元素缺失，是 token 漂移。
- 最终处理：均为改 checker；没有补模板；没有删除核心检查。

## 4. Checker PASS 汇总

修复后全量实跑：

```text
total=41 failed=0 skipped=2
```

全量 checker 0 FAIL。保留的 WARN/SKIP 为既有 report-only/数据覆盖说明，不是失败：

- `check_w1_odds_extension.py`: 2014 FULL 缺本地 odds、AH 缺源，WARN。
- `check_w1_host_no_qualifier_history.py`: host qualifier history report-only WARN。
- `check_w1_backtest_spine.py` / `check_w1_ou_coverage.py` 等按现有 artifact 状态 PASS 或安全 SKIP。

## 5. 是否重置运行产物

否。

未把 1538999 从 `W1_PLAY` 改回 `W1_WAIT`；未把 `Türkiye` 改回 `Turkey`；未重置 watcher state 到旧值。运行时/dashboard/data 脏文件保持工作区真实状态，未纳入 commit 1。

## 6. 是否弱化 checker

否。

本阶段把旧快照硬编码改成真实安全意图：

- 旧系统引用仍被禁止；只允许明确 env bridge 路径。
- API smoke 现在强制离线，避免 checker 读取本地 key 外联。
- post-match 仍要求比分、RPS/log-score、calibration 字段完整。
- `W1_PLAY` 仍要求 confirmed lineup 和 `W1_PLAY_GUARD_V1` 自洽。
- watcher 仍要求 dry-run 0 API calls、CST 时间格式、schedule 可解释、`pushed=false`。

## 7. 红线确认

- 未改 `scripts/w1_score_engine.py`。
- 未改 `DEFAULT_RHO`。
- 未改 `config/w1_decision_policy.json`。
- 未改 `config/w1_odds_movement_thresholds.json`。
- 未改 FULL pipeline 结论。
- 未改 anomaly review 结论。
- 未引入 draw calibration。
- 未实现 per-match rho。
- 未造假数据。
- 未把真实 `W1_PLAY` 重置为 `W1_WAIT`。
- 未把 `Türkiye` 改回 `Turkey`。
- 未删除 checker 核心安全断言。
- 未把 FAIL 全部降级为 WARN。
- 最终 checker smoke 禁用 env bridge，不接 API。
- 未 push；未 force push。
- 无投注、资金、命中率承诺表达。

## 8. 是否回滚

否。没有需要回滚的代码改动。

说明：开工时工作区已有运行时/产物脏文件；验证过程中的 smoke 也会刷新 dashboard/progress。按本阶段“不重置真实运行态”口径，未回滚这些产物，也未将其混入 cleanup commit。

## 9. 修改文件清单

commit 1:

- `scripts/check_w1_click_to_predict.py`
- `scripts/check_w1_dashboard_data_binding.py`
- `scripts/check_w1_early_prediction_mode.py`
- `scripts/check_w1_environment_context.py`
- `scripts/check_w1_manual_lineup_override.py`
- `scripts/check_w1_post_match_calibration.py`
- `scripts/check_w1_post_match_result_update.py`
- `scripts/check_w1_report_templates.py`
- `scripts/check_w1_round1_real_fixture_cards.py`
- `scripts/check_w1_watcher.py`
- `scripts/check_w1_weather_integration.py`
- `scripts/w1_local_predict_server.py`

commit 2:

- `reports/W1_RUNTIME_CHECKER_CLEANUP_V1_RESULT.md`

## 10. 下一阶段建议

1. 单独立项清理/归档运行时脏文件：dashboard、progress、match card runtime、results overlay、local odds quality reports。
2. 给所有 smoke checker 统一加离线模式约定，默认禁用 env bridge，避免验证时外联。
3. 将 checker runner 固化成一个脚本，输出 machine-readable summary，减少手写循环带来的口径漂移。
4. 把 source alias / team alias / allowed runtime state enum 抽成共享 helper，避免 checker 间重复维护。
