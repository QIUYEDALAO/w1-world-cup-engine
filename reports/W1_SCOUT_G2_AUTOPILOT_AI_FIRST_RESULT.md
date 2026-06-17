# W1_SCOUT_G2_AUTOPILOT_AI_FIRST_RESULT

**阶段**: G2 Scout 自动生产闭环 + AI-first Director View  
**结论**: 本地实现已完成，完整 checker 验证 PASS；未 push，等待验收。

## 1. 固定格式验收表

| 项目 | 结果 | 说明 |
|---|---:|---|
| autopilot policy | PASS | 新增 `config/w1_scout_autopilot_policy.json`，覆盖 schedule windows、delta、skip、failure、dry-run、赛前纪律。 |
| runner dry-run | PASS | `scripts/run_w1_scout_cycle.sh --dry-run` 不抓取、不调 AI、不写 state、不 embed、不 lock。 |
| future fixture discipline | PASS | runner 只选择未来 fixture 抓赛前因子；无未来 fixture 时 audit only。 |
| delta gate | PASS | future effective bundle 无变化时不调用 DeepSeek、不 embed、不 lock，只 audit。 |
| analyst failure gate | PASS | analyst 非零时不更新 sha、不 embed、不 lock，写 status/error log，只 audit 后非零退出。 |
| cycle status/error log | PASS | runtime 输出到 `state/scout_cycle_status.json` 与 `state/scout_cycle_errors.log`，均不入仓。 |
| AI-first Director View | PASS | 首屏改为 AI 分析师卡 + 运行/错误日志 + 操作按钮。 |
| W1 expert fold | PASS | W1 市场读数、FiveDim、Primary Read、候选共识、score matrix、盘口面板保留并折叠进专家视图。 |
| dashboard Scout embedded JSON | PASS | checker 解析 `w1-scout-calls` 与 `w1-scout-cycle-status`。 |
| no old call advanced | PASS | 新 checker 动态验证 analyst failure 不推进旧 call 的 sha/embed/lock。 |
| forbidden wording/leakage | PASS | 沿用 `check_w1_scout.py` 与 dashboard 禁词/防泄漏检查。 |

## 2. 修改文件

- `config/w1_scout_autopilot_policy.json`
- `scripts/run_w1_scout_cycle.sh`
- `scripts/check_w1_scout_autopilot.py`
- `scripts/check_w1_visual_dashboard.py`
- `scripts/check_w1_safe_view.py`
- `reports/dashboard/W1_VISUAL_DASHBOARD.html`
- `reports/W1_SCOUT_AUTOPILOT_RUNBOOK.md`
- `reports/W1_SCOUT_G2_AUTOPILOT_AI_FIRST_RESULT.md`

## 3. 未触碰红线

| 红线 | 是否触碰 |
|---|---:|
| `scripts/w1_score_engine.py` | 否 |
| `DEFAULT_RHO` | 否 |
| λ / 概率 | 否 |
| Primary Read 决策逻辑 | 否 |
| `state/scout_*` 路径迁移 | 否 |
| distiller | 否 |
| `state/` 或 `data/scout/` 入仓 | 否 |
| 新 API | 否 |
| raw prompt / raw call / API dump / secret/env 入仓 | 否 |
| 已开赛/完赛伪赛前补因子 | 否 |

## 4. 验收命令

```bash
bash -n scripts/run_w1_scout_cycle.sh
python3 scripts/check_w1_scout.py
python3 scripts/check_w1_scout_autopilot.py
python3 scripts/check_w1_visual_dashboard.py
python3 scripts/check_w1_dashboard_data_binding.py
python3 scripts/check_w1_primary_read.py
python3 scripts/check_w1_confidence_adjustment.py
python3 scripts/check_w1_runtime_artifact_policy.py
python3 scripts/check_w1_fivedim_lite.py
python3 scripts/check_w1_recommendation_output_policy.py
python3 scripts/check_w1_opportunity_phase_a.py
python3 scripts/check_w1_safe_view.py
python3 scripts/check_w1_production_lite.py
bash scripts/run_w1_scout_cycle.sh --dry-run
```

本轮已执行上述命令，全部 PASS。

## 5. 下一步

验收通过后再决定是否提交与 push。生产机器只需要配置 `APIFOOTBALL_KEY` 与 `DEEPSEEK_API_KEY`，再按 runbook 挂 cron。
