# W1 Real Fixture Card 1489382

**Match:** Austria vs Jordan  
**Fixture:** `api-football:1489382`  
**Round:** Group Stage - 1  
**Kickoff UTC:** 2026-06-17T04:00:00Z  
**Kickoff CST:** 2026-06-17 12:00  
**Venue:** Levi's Stadium, San Francisco Bay Area, USA  
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
| 1X2 | Home=1.30 | Draw=5.10 | Away=9.60 |
| AH | Home -1=1.45, Away -1=2.75, Home -1.5=1.91, Away -1.5=1.90 |
| OU | Over 1.5=1.20, Under 1.5=4.33, Over 2.5=1.62, Under 2.5=2.25, Over 3.5=2.55, Under 3.5=1.50 |
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
