# W1_SCOUT_REFRAME_READ_REVIEW_RESULT

日期: 2026-06-17

## 结论

W1_SCOUT 已从"预测器/追 edge"口径收敛为"五维理解 + 赛后复盘 + 自我校准"工具。

本阶段不改 W1 市场底座、不改 `w1_score_engine.py`、不改 `DEFAULT_RHO`、不改 lambda / 概率 / Primary Read。Scout 仍只在上层读取赛前 bundle、输出研究解读，并通过 checker 闸门后才写入 runtime / dashboard embedded copy。

## 已完成

1. G1 prompt / schema 改口径
   - `scripts/w1_scout_analyst.py` 改为"把这场球读透"。
   - 输出 schema 改为 `read{tilt_cn, score_band_cn, watch_points_cn, risks_cn, vs_market_cn}`。
   - `honesty_label` 改为 `AI 解读·非预测·非推介·可能错`。
   - 砍掉旧 `outcome_lean / scoreline_lean / confidence / stance / conviction` 主口径。

2. G2 赛后复盘
   - 新增 `scripts/w1_scout_review.py`。
   - 复盘只读取 immutable lock + 本地赛果。
   - 输出 `state/scout_reviews.jsonl`，保持 gitignored runtime；本阶段不是 tracked memory。
   - `prematch_read_digest` 与 lock 计算值一致才通过 checker。
   - 新 lock digest 使用 canonical JSON 的 sha256；旧 lock 若无 digest 仅做 legacy 兼容，不回写原文。

3. G3 多联赛参数化入口
   - `config/w1_scout_policy.json` 增加 `leagues`。
   - `scripts/w1_scout_bundle.py` 不再硬编码唯一世界杯 season，优先读取记录/配置。
   - `scripts/w1_scout_fetch_api_football.py` 增加 `--league / --season` 过滤入口；赛前防泄漏不变。

4. G4 dashboard 改为解读 + 复盘
   - Scout 卡标题改为 `本场解读 · DeepSeek`。
   - 展示强弱倾向、比分区间、看点、风险、与市场差异(讨论点)、数据就绪度。
   - 新增 `赛后复盘` 卡。
   - `w1_scout_embed.py` 同步嵌入 Scout reads / reviews / calibration。

5. G5 自我校准
   - 新增 `scripts/w1_scout_calibration.py`。
   - 输出 `state/scout_calibration.json`，保持 gitignored runtime；本阶段不是 tracked memory。
   - dashboard 学习状态显示解读数、审计数、复盘数、平均就绪度。
   - 明确: 这是自我体检与校准，不是战胜市场的证据。

## 当前本机状态

- 当前已转换本机 `state/w1_scout_calls.json` 为新 read schema，但该文件仍是 gitignored runtime，不入库。
- 当前 `state/scout_reviews.jsonl` 仍可为空；`scripts/w1_scout_review.py --dry-run` 显示已有已完赛锁定样本可复盘，真正生成需 DeepSeek key。该文件仍是 gitignored runtime，不属于 tracked memory allowlist。
- 当前 `state/scout_calibration.json` 已由本地脚本生成，仍是 gitignored runtime，不属于 tracked memory allowlist。
- 后续是否将 review/calibration 纳入 tracked memory，需要单独阶段决策；本阶段不扩大 allowlist。

## Checker

已通过:

- `python3 scripts/check_w1_scout.py`
- `python3 scripts/check_w1_visual_dashboard.py`
- `python3 scripts/check_w1_scout_autopilot.py`
- `python3 scripts/check_w1_runtime_artifact_policy.py`
- `python3 scripts/check_w1_dashboard_data_binding.py`
- `python3 scripts/check_w1_primary_read.py`
- `python3 scripts/check_w1_confidence_adjustment.py`
- `python3 scripts/check_w1_fivedim_lite.py`
- `python3 scripts/check_w1_recommendation_output_policy.py`
- `python3 scripts/check_w1_opportunity_phase_a.py`
- `python3 scripts/check_w1_safe_view.py`
- `python3 scripts/check_w1_production_lite.py`
- `bash scripts/run_w1_scout_cycle.sh --dry-run`

## 红线确认

- 未改 `scripts/w1_score_engine.py`
- 未改 `DEFAULT_RHO`
- 未改 lambda / 概率
- 未改 Primary Read 决策逻辑
- 未把 raw bundle / raw call / reviews / calibration 入库
- 未提交 API key / raw prompt / API dump
- 未使用投注化展示文案

## 下一步

1. 如需真实赛后复盘，配置 DeepSeek key 后运行:
   `python3 scripts/w1_scout_review.py`
2. 复盘完成后运行:
   `python3 scripts/w1_scout_calibration.py`
3. 再运行:
   `python3 scripts/w1_scout_embed.py`
4. 最后跑:
   `python3 scripts/check_w1_scout.py`
   `python3 scripts/check_w1_visual_dashboard.py`
