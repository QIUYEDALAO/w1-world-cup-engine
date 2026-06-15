# W1_FORWARD_LEDGER_V1

阶段：`W1_FORWARD_LEDGER_AND_S2_PROTOTYPE_V1`（F 轨，最高优先级）
定位：从现在起，对**未开赛**的比赛逐场落库**赛前时点快照**。世界杯正在进行，赛前的首发/天气/盘口相位等快照事后无法追溯，必须现在开始积累——这是未来 lineup/weather/tactical 因子消融唯一干净的数据来源。

## 1. 严格边界（本阶段红线）

本阶段 F 轨**只允许**：本地已有数据、项目内已有字段、手动输入、空值占位 + 可用性标志、schema/checker/append-only 管线。

**禁止**：接外部 API、爬虫、外部数据源、采购数据。"落库赛前快照字段" ≠ "抓取"。要接外部源需单独立项确认。

## 2. 只记赛前，绝不记赛后（leakage guard）

快照**不得**包含任何赛后字段：`actual_score` / `result` / `home_goals`/`away_goals` / `finish_type` / `post_match_calibration` / `rps` / `log_loss` / 实际进球等。checker 强制断言这些键不存在。

## 3. 记录什么（赛前字段）

每条 = 一个 fixture 在一个 `as_of_utc` 的赛前快照（append-only）：

- 标识：`fixture_id`、`match`、`kickoff_utc`、`as_of_utc`(必填)、`snapshot_phase`(由 kickoff−as_of 推 T-48h/24h/12h/6h/2h/1h/closing)。
- 首发：`lineup_status`、`confirmed_lineup`、`confirmed_lineup_utc`、`home_starting_xi`、`away_starting_xi`、`home_formation`、`away_formation`、`key_absences`。
- 盘口：`odds_phase`、`odds_1x2`(home/draw/away，本地已有则记)、`odds_snapshot_utc`、`market_movement_status`。
- 环境：`weather_status`、`temperature_c`、`wind_kmh`、`precip_prob`。
- 裁判：`referee_assigned`、`referee_name`。
- 战术：`tactical_notes`。
- 可用性标志：`availability`={lineup, odds, weather, referee, tactical}，缺则 null + flag=false。
- 来源：`data_source`(local_card / manual / none)。

## 4. 存储

- `data/forward_ledger/w1_forward_ledger.jsonl`（append-only，**gitignored**，运行时累积）。
- 每次运行对未开赛 fixture 追加一行；finished/已开赛跳过。

## 5. 复现

```bash
python3 scripts/snapshot_w1_forward_ledger.py    # 对未开赛 fixture 追加赛前快照(本地数据)
python3 scripts/check_w1_forward_ledger.py       # 校验 schema / as_of / append-only / 无赛后字段
```

## 6. 边界

赛前分析与研究用途；不是投注平台、不输出资金建议、不承诺命中率。
