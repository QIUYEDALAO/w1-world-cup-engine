# W1 Match Card Sample

**Match:** Mexico vs South Africa  
**Competition:** FIFA World Cup 2026  
**Fixture:** `api-football:1489369`  
**Decision:** `W1_WAIT`

## Why This Is WAIT

Confirmed lineups are not available in the sample snapshot. W1_PRODUCTION_LITE hard rules require `W1_WAIT` whenever `confirmed_lineup` is missing.

The sample still includes required market coverage:

- `odds_1X2`: available
- `odds_AH`: available
- `odds_OU`: available
- `first_seen_odds_proxy`: available and explicitly not treated as official opening odds

## Risk Flags

| Code | Severity | Meaning |
|---|---:|---|
| `REFEREE_MISSING` | LOW | Referee not yet assigned in source snapshot |
| `REFEREE_UNASSIGNED` | LOW | Referee assignment is unavailable in the source snapshot |
| `SUSPENSIONS_PARTIAL` | MEDIUM | Suspensions are partial and require manual review |
| `TRAVEL_DISTANCE_PARTIAL` | LOW | Travel distance is estimated from partial assumptions |

## Data Gaps

| Field | Blocks Play | Meaning |
|---|:---:|---|
| `lineups.confirmed_lineup` | true | Confirmed starting lineups are missing |
| `match.referee` | false | Referee missing is tracked as risk, not a blocker |

## Ledger

`ledger_required=false` for this sample because the decision is `W1_WAIT`.

For any future `W1_PLAY`, `ledger_required` must be `true` and a ledger entry must validate against `config/w1_ledger_schema.json`.

## PLAY_GUARD_V1

This sample remains `W1_WAIT`, so `W1_PLAY_GUARD_V1` cannot pass. The sample still includes the new guard inputs:

- `odds_movement`
- `market_signal`
- `decision.reasons.supporting_factors`
- `decision.reasons.counter_factors`

`W1_PLAY` is allowed only when all quantitative guard rules pass; data completeness alone is not enough.

## Boundary

This sample does not call external APIs, does not connect QQ, does not write old official/pending status, and does not make any betting commitment.
