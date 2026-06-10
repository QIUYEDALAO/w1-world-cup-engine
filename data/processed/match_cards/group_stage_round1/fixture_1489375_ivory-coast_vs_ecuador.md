# W1 Real Fixture Card 1489375

**Match:** Ivory Coast vs Ecuador  
**Fixture:** `api-football:1489375`  
**Round:** Group Stage - 1  
**Kickoff UTC:** 2026-06-14T23:00:00Z  
**Kickoff CST:** 2026-06-15 07:00  
**Venue:** Lincoln Financial Field, Philadelphia, USA  
**Final Decision:** `W1_WAIT`  
**Ledger Required:** `true`

## Snapshot Status

| Field | Status |
|---|---|
| odds_1X2 | READY |
| odds_AH | READY |
| odds_OU | READY |
| squad | READY |
| standings | READY |
| H2H | READY |
| lineup_status | WAIT_EVENT |
| referee_status | MISSING |
| weather_possible | YES |

## Market Snapshot

| Market | Value |
|---|---|
| 1X2 | Home=3.45 | Draw=2.86 | Away=2.32 |
| AH | Home +0=2.35, Away +0=1.60, Home +0.5=1.62, Away +0.5=2.30 |
| OU | Over 1.5=1.62, Under 1.5=2.25, Over 2.5=2.88, Under 2.5=1.40, Over 3.5=6.00, Under 3.5=1.12 |
| bookmaker_count | 13 |

## Decision Reason

confirmed_lineup missing for this fixture, so W1 hard rules keep `W1_WAIT`. This card records fixture and market data only.

## Risk Flags

- CONFIRMED_LINEUP_MISSING
- LINEUP_WAIT_EVENT
- REFEREE_MISSING
- SUSPENSIONS_PARTIAL
- TRAVEL_DISTANCE_PARTIAL

## Data Gaps

- lineups.confirmed_lineup blocks any non-WAIT final_decision
- match.referee remains a non-blocking gap
