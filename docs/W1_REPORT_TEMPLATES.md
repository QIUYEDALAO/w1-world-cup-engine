# W1 Report Templates

These templates standardize W1 reporting without changing match cards, ledger rows, or watcher scheduling. They are intentionally concise and audit-oriented.

## 1. No-Change Watcher Status Report

Use when watcher v2 detects no substantial change.

```markdown
# W1 Watcher Status

**Snapshot time:** <SNAPSHOT_TIME_CST>  
**Watcher version:** <WATCHER_VERSION>  
**Substantial change:** NO  
**Next refresh:** <NEXT_REFRESH_CST>

## Checked Inputs

| Input | Status |
|---|---|
| fixtures | <READY/MISSING> |
| odds_1X2 | <READY/MISSING> |
| odds_AH | <READY/MISSING> |
| odds_OU | <READY/MISSING> |
| lineup | <WAIT_EVENT/READY> |
| referee | <MISSING/READY> |
| injury | <READY/PARTIAL/MISSING> |

## Result

No substantial change detected. No match cards, ledger rows, or git commit were written.
```

## 2. Match Update Report

Use when watcher v2 detects a substantial change in odds, lineup, referee, or injury data.

```markdown
# W1 Match Update

**Snapshot time:** <SNAPSHOT_TIME_CST>  
**Fixture:** <FIXTURE_ID>  
**Match:** <HOME_TEAM> vs <AWAY_TEAM>  
**Change type:** <ODDS_1X2/AH/OU/LINEUP/REFEREE/INJURY>

## Before / After

| Field | Previous | Current |
|---|---|---|
| odds_1X2 | <previous> | <current> |
| odds_AH | <previous> | <current> |
| odds_OU | <previous> | <current> |
| lineup_status | <previous> | <current> |
| referee_status | <previous> | <current> |
| injury_status | <previous> | <current> |

## Decision Impact

| Field | Value |
|---|---|
| current_decision | <W1_WAIT/W1_WATCH/W1_PLAY/W1_PASS> |
| play_guard_version | W1_PLAY_GUARD_V1 |
| ledger_required | <true/false> |
| blocking_data_gaps | <count> |

## Action

<Describe the card and ledger update performed, or explain why no decision label changed.>
```

## 3. Formal Pre-Match W1 Report

Use after confirmed lineup is available and PLAY_GUARD inputs are ready.

```markdown
# W1 Pre-Match Report

**Fixture:** <FIXTURE_ID>  
**Match:** <HOME_TEAM> vs <AWAY_TEAM>  
**Kickoff UTC:** <KICKOFF_UTC>  
**Generated at:** <GENERATED_AT_UTC>

## Data Readiness

| Input | Status |
|---|---|
| confirmed_lineup | <READY/MISSING> |
| odds_1X2 | <READY/MISSING> |
| odds_AH | <READY/MISSING> |
| odds_OU | <READY/MISSING> |
| squad | <READY/MISSING> |
| standings | <READY/MISSING> |
| H2H | <READY/MISSING> |

## Market Signal

| Guard Field | Value |
|---|---|
| odds_snapshot_age_minutes | <minutes> |
| odds_1X2_overround | <value> |
| AH_direction_consistent_with_elo | <true/false> |
| supporting_factors.count | <count> |
| counter_factors.count | <count> |

## Risk And Gaps

| Item | Count / Status |
|---|---|
| risk_flags.count | <count> |
| blocking_data_gaps | <count> |
| unresolved_data_gaps | <list> |

## Decision

| Field | Value |
|---|---|
| decision | <W1_WAIT/W1_WATCH/W1_PLAY/W1_PASS> |
| play_guard_version | W1_PLAY_GUARD_V1 |
| ledger_required | <true/false> |

## Rationale

- Supporting factor: <factor>
- Supporting factor: <factor>
- Counter factor: <factor>
```

## 4. Stage-End Summary

Use at the end of a round, matchday block, or group-stage phase.

```markdown
# W1 Stage-End Summary

**Stage:** <STAGE_NAME>  
**Date range:** <START> to <END>  
**Cards reviewed:** <count>

## Decision Distribution

| Decision | Count |
|---|---:|
| W1_WAIT | <count> |
| W1_WATCH | <count> |
| W1_PLAY | <count> |
| W1_PASS | <count> |

## Data Quality

| Metric | Value |
|---|---|
| confirmed_lineup_ready | <count>/<total> |
| odds_ready | <count>/<total> |
| referee_ready | <count>/<total> |
| injury_ready | <count>/<total> |
| unresolved_data_gaps | <count> |

## Calibration Notes

- What improved:
- What stayed partial:
- What should change before the next stage:

## Ledger Review

| Metric | Value |
|---|---|
| ledger_rows | <count> |
| play_guard_version | W1_PLAY_GUARD_V1 |
| calibration_cycle | <cycle_id> |
```

