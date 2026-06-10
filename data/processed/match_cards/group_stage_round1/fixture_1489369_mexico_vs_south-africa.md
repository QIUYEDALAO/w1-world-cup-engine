# W1 Real Fixture Card 1489369

**Match:** Mexico vs South Africa  
**Fixture:** `api-football:1489369`  
**Round:** Group Stage - 1  
**Kickoff UTC:** 2026-06-11T19:00:00Z  
**Kickoff CST:** 2026-06-12 03:00  
**Venue:** Estadio Azteca, Mexico City, Mexico  
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
| 1X2 | Home=1.40 | Draw=4.30 | Away=8.75 |
| AH | Home -1=1.70, Away -1=2.15, Home -0.5=1.48, Away -0.5=2.65, Home -1.5=2.30, Away -1.5=1.62 |
| OU | Over 1.5=1.38, Under 1.5=3.00, Over 2.5=2.10, Under 2.5=1.70, Over 3.5=3.80, Under 3.5=1.25 |
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
