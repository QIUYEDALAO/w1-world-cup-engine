# W1 Production Lite

**Status:** production-lite  
**Purpose:** 本届世界杯赛前正式分析的最小入口  
**Scope:** W1 only. 不接 QQ，不写 old official/pending，不改 V3/V4/M1，不配置 remote，不调用外部 API。

## 1. What This Is

W1_PRODUCTION_LITE 是世界杯赛前分析的最小正式流程。它不承诺投注结果，不输出稳赚、命中率或保证性表达，只输出结构化 match card、决策标签、风险标记、数据缺口和必要的 ledger 要求。

产物边界：

- Match card: 每场比赛一张结构化卡片。
- Decision policy: 把数据完整性和风险转为固定决策标签。
- Ledger schema: 规定需要记录的正式分析操作。
- Checker: 本地自检 schema、策略和样例是否满足硬规则。

## 2. Decision Labels

| Label | Meaning | Use |
|---|---|---|
| `W1_PLAY` | 数据完整，风险可接受，允许进入正式赛前观点输出 | 必须 `ledger_required=true` |
| `W1_WATCH` | 可观察但不进入正式动作；存在非阻塞缺口或风险 | 可记录观察，不做承诺 |
| `W1_WAIT` | 关键数据缺失，必须等待更新 | lineup / odds / squad 等硬门槛触发 |
| `W1_PASS` | 数据足够但风险或价格不支持继续 | 可解释放弃理由 |

## 3. Hard Rules

1. `confirmed_lineup` 缺失或不是 confirmed => `W1_WAIT`
2. `odds_1X2` / `odds_AH` / `odds_OU` 任一缺失 => `W1_WAIT`
3. `squad` 缺失 => `W1_WAIT` 或降级 `W1_WATCH`，并在 `data_gaps` 说明字段缺口
4. `suspensions` / `travel_distance` 为 `PARTIAL` 不阻塞，只加入 `risk_flags`
5. `first_seen_odds_proxy` 不能写成 `opening_odds`
6. `W1_PLAY` 必须 `ledger_required=true`
7. 每场必须输出 `risk_flags`
8. 每场必须输出 `data_gaps`

## 4. Data Inputs

Minimum production-lite data:

- api-football: fixtures, odds 1X2/AH/OU, squads, lineups, injuries, standings, stats, H2H, referee
- Open-Meteo: venue geocoding / weather
- FIFA rank: crawler or snapshot
- Elo: local calculation from international match result CSV
- `first_seen_odds_proxy`: first observed W1 odds snapshot, not official opening odds

Partial inputs:

- `suspensions`: partial manual/API-derived signal, non-blocking
- `travel_distance`: partial venue/team movement estimate, non-blocking

## 5. Match Card Contract

The match card is validated by `config/w1_match_card_schema.json`.

Required top-level sections:

- `schema_version`
- `match`
- `teams`
- `data_sources`
- `markets`
- `squad`
- `lineups`
- `context`
- `risk_flags`
- `data_gaps`
- `decision`

No field named `opening_odds` is allowed. Use `first_seen_odds_proxy` only.

## 6. Decision Flow

1. Build card from local snapshots or already-collected source outputs.
2. Check hard blockers:
   - lineup confirmed?
   - 1X2/AH/OU present?
   - squad present or explicitly degraded?
3. Add non-blocking risks:
   - partial suspensions
   - partial travel distance
   - weather uncertainty
   - referee unavailable
4. Assign one of the four labels.
5. If label is `W1_PLAY`, require ledger entry.
6. Always include `risk_flags` and `data_gaps`, even when empty.

## 7. Ledger Contract

The ledger schema is in `config/w1_ledger_schema.json`.

Ledger is required for:

- every `W1_PLAY`
- any manual override
- any card promoted from `W1_WAIT`/`W1_WATCH` to `W1_PLAY`

Ledger records must not contain betting guarantees, private push routing, QQ instructions, or old official/pending status.

## 8. Self Test

Run:

```bash
python3 scripts/check_w1_production_lite.py
```

Expected result:

```text
W1_PRODUCTION_LITE self-test PASS
```

