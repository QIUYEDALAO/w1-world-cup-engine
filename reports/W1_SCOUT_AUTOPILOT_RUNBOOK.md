# W1_SCOUT Autopilot Runbook

**阶段**: G2 Scout 自动生产闭环 + AI-first Director View  
**用途**: 让本地 W1 server 启动后自动检查未来赛程并生成缺失的 Scout AI推荐卡；无有效变化时省 DeepSeek；失败时不推进旧 call。

## 1. 日常运行

```bash
cd /Users/liudehua/.openclaw/workspace/w1_world_cup_engine
DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" \
W1_SCOUT_AUTOPILOT=1 \
python3 scripts/w1_local_predict_server.py
```

如果有 APIFOOTBALL_KEY:

```bash
APIFOOTBALL_KEY="$APIFOOTBALL_KEY" \
DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" \
W1_SCOUT_AUTOPILOT=1 \
python3 scripts/w1_local_predict_server.py
```

打开:

```text
http://127.0.0.1:8765/reports/dashboard/W1_VISUAL_DASHBOARD.html
```

注意:

- 不启动 server，就不会自动生成 AI推荐卡。
- 修改 `.env` / `.env.local` 后必须重启 server。
- `W1_SCOUT_AUTOPILOT=0` 会关闭自动周期，只保留手动强刷。
- 自动周期只处理未来 fixture，默认覆盖未来 48 小时。
- 已开赛 / 完赛比赛不补写赛前推荐，只等待赛后 audit / review / calibration。

内部 runner 仍可由 cron 调度，窗口参考 `config/w1_scout_autopilot_policy.json`:

- T-48h 到 T-24h: 每 2 小时
- T-24h 到 T-6h: 每 2 小时
- T-6h 到 T-2h: 每 1 小时
- T-2h 到开赛: 每 30 分钟

## 2. Dry-run

```bash
bash scripts/run_w1_scout_cycle.sh --dry-run
```

dry-run 只检查当前未来 fixture 选择和流程可达性:

- 不抓 api-football
- 不调用 DeepSeek
- 不写 `state/`
- 不 embed dashboard
- 不 lock

## 3. Delta Gate

runner 只对未来 fixture 的 effective scout bundle 做 hash。以下 runtime 字段被排除:

- `fetched_at_utc`
- `generated_at_utc`
- `updated_at`
- `requested_at`
- `fetched_at`

无有效变化时:

- 不调用 DeepSeek
- 不更新 `.scout_bundles.sha`
- 不 embed
- 不 lock
- 只允许 audit

但如果未来 fixture 缺少首版 read / lock，missing read 的优先级高于 no-delta，自动周期必须生成首版赛前推荐卡。

## 4. 失败语义

Analyst 非零失败时:

- 不更新 `.scout_bundles.sha`
- 不 embed dashboard
- 不 lock
- 写 `state/scout_cycle_status.json`
- 追加 `state/scout_cycle_errors.log`
- 只允许 audit
- runner 返回非零

`check_w1_scout.py` 失败时:

- 不更新 `.scout_bundles.sha`
- 不 embed
- 不 lock
- runner 返回非零

## 5. 赛前纪律

未来 fixture 才允许赛前抓因子。已开赛/完赛 fixture 只允许赛后 audit，禁止补写伪赛前因子。

`data/scout/` 与 `state/` 均为 runtime store，不入仓。

## 6. Dashboard

第一屏现在是 AI-first:

- AI推荐卡 · DeepSeek
- 运行 / 错误日志
- 操作按钮

运行卡会显示:

- 自动周期是否开启
- 上次 / 下次自动检查时间
- 待生成 fixture 数
- 已有 read 但待补上屏 fixture 数
- 本轮结果与错误状态

W1 市场读数、FiveDim、Primary Read、候选共识、score matrix、盘口面板、数据质量、环境、抓取状态全部保留在专家视图。

页面文案固定声明:

- 研究用途
- 非推介
- 非独立优势

## 7. 验收命令

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

## 8. 红线

- 不改 `scripts/w1_score_engine.py`
- 不改 `DEFAULT_RHO`
- 不改 λ / 概率 / Primary Read 决策逻辑
- 不迁移 `state/scout_*`
- 不新增 distiller
- 不把 raw `state/` 或 `data/scout/` 纳入 git；仅既定 Scout memory allowlist 可入库
- 不提交 raw prompt / raw call / API dump / secret / env
- 不对已开赛/完赛比赛补写伪赛前因子
