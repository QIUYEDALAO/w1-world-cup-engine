# W1 Real Fixture Card 1539000

**Match:** Canada vs Bosnia & Herzegovina  
**Fixture:** `api-football:1539000`  
**Round:** Group Stage - 1  
**Kickoff UTC:** 2026-06-12T19:00:00Z  
**Kickoff CST:** 2026-06-13 03:00  
**Venue:** BMO Field, Toronto, Canada  
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
| 1X2 | Home=1.78 | Draw=3.50 | Away=4.50 |
| AH | Home -1=2.45, Away -1=1.50, Home -0.5=1.73, Away -0.5=2.05, Home +0=1.30, Away +0=3.25 |
| OU | Over 1.5=1.40, Under 1.5=2.90, Over 2.5=2.20, Under 2.5=1.65, Over 3.5=4.20, Under 3.5=1.22 |
| bookmaker_count | 14 |

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
