# W1_SCOUT Scheduler Runbook

## 定位

W1 Scout Scheduler 是赛前 AI 推荐卡的生产入口。dashboard 只负责展示结果；手动强刷只作兜底，不是主流程。

Scheduler 按比赛 kickoff 自动检查这些时间窗：

- 早盘参考：T-48h / T-24h
- 赛前观察：T-12h / T-6h / T-2h
- 正式判断：T-1h
- 最终版：T-30m

已开赛或完赛后不得补写赛前 read；赛后只进入 audit / review / calibration。

## 手动单次运行

```bash
DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" \
APIFOOTBALL_KEY="$APIFOOTBALL_KEY" \
python3 scripts/w1_scout_scheduler.py --once
```

## 常驻运行

```bash
DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" \
APIFOOTBALL_KEY="$APIFOOTBALL_KEY" \
python3 scripts/w1_scout_scheduler.py --daemon --interval 60
```

## Dry-run / 时间模拟

```bash
python3 scripts/w1_scout_scheduler.py --dry-run
python3 scripts/w1_scout_scheduler.py --dry-run --now-override "2026-06-20T02:00:00+08:00"
python3 scripts/w1_scout_scheduler.py --dry-run --fixture-id 1539006 --stage official_1h --now-override "2026-06-20T02:00:00+08:00"
```

Dry-run 不抓取 Football-API，不调用 DeepSeek，不写 `state/`，只打印 due queue。

## macOS launchd 示例

保存为 `~/Library/LaunchAgents/com.w1.scout.scheduler.plist`，按本机路径调整 `ProgramArguments` 和环境变量来源。不要把 key 写入 git。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.w1.scout.scheduler</string>
  <key>WorkingDirectory</key><string>/Users/liudehua/.openclaw/workspace/w1_world_cup_engine</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/env</string>
    <string>python3</string>
    <string>scripts/w1_scout_scheduler.py</string>
    <string>--once</string>
  </array>
  <key>StartInterval</key><integer>60</integer>
  <key>StandardOutPath</key><string>/tmp/w1_scout_scheduler.out.log</string>
  <key>StandardErrorPath</key><string>/tmp/w1_scout_scheduler.err.log</string>
</dict>
</plist>
```

启动：

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.w1.scout.scheduler.plist
launchctl kickstart -k gui/$(id -u)/com.w1.scout.scheduler
```

## 运行状态

- 阶段配置：`config/w1_scout_schedule_policy.json`
- 调度状态：`state/w1_scout_scheduler_status.json`，runtime，不入 git
- AI read：`state/w1_scout_calls.json`，runtime，不入 git
- dashboard 上屏：`python3 scripts/w1_scout_embed.py`

## 红线

- 不改 `scripts/w1_score_engine.py`
- 不改 `DEFAULT_RHO`
- 不改 λ / 概率算法 / Primary Read
- 不提交 `.env` / secret / raw API dump
- 不提交 `state/w1_scout_calls.json` / `state/w1_scout_bundles.json` / `data/scout/`
- kickoff 后不补写赛前 read
- dashboard 不是生产器，只是结果查看器
