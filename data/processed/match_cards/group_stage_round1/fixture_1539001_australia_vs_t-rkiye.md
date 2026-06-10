# W1 Real Fixture Card 1539001

**Match:** Australia vs Türkiye  
**Fixture:** `api-football:1539001`  
**Round:** Group Stage - 1  
**Kickoff UTC:** 2026-06-14T04:00:00Z  
**Kickoff CST:** 2026-06-14 12:00  
**Venue:** BC Place, Vancouver, Canada  
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
| 1X2 | Home=4.75 | Draw=3.65 | Away=1.70 |
| AH | Home +0.5=2.15, Away +0.5=1.67, Home +1=1.60, Away +1=2.25 |
| OU | Over 1.5=1.33, Under 1.5=3.25, Over 2.5=2.00, Under 2.5=1.80, Over 3.5=3.50, Under 3.5=1.28 |
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
