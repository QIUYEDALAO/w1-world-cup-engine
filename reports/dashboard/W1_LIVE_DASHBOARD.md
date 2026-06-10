# W1 Live Dashboard

**Generated from local committed W1 state:** 2026-06-10  
**Scope:** World Cup 2026 Group Stage Round 1  
**Format:** Markdown dashboard

## Decision Counts

| Decision | Count |
|---|---:|
| W1_WAIT | 24 |
| W1_WATCH | 0 |
| W1_PLAY | 0 |
| W1_PASS | 0 |

## First Match

| Field | Value |
|---|---|
| fixture_id | 1489369 |
| match | Mexico vs South Africa |
| kickoff_utc | 2026-06-11T19:00:00Z |
| current_decision | W1_WAIT |
| lineup_status | WAIT_EVENT |
| referee_status | MISSING |
| ledger_required | true |

## Runtime

| Field | Value |
|---|---|
| next_refresh | 2026-06-10 18:00 CST |
| watcher_version | v2 |
| play_guard_version | W1_PLAY_GUARD_V1 |

## Unresolved Data Gaps

| Gap | Scope | Blocks W1_PLAY | Status |
|---|---|:---:|---|
| confirmed_lineup | 24/24 first-round cards | yes | WAIT_EVENT |
| referee assignment | first-round cards | no | MISSING or WAIT_EVENT |
| suspensions | system-level | no | PARTIAL |
| travel_distance | system-level | no | PARTIAL |

## Notes

- Dashboard is read-only and does not call external APIs.
- Counts are derived from current local match cards and ledger state.
- W1_PLAY requires W1_PLAY_GUARD_V1, not just complete data.

