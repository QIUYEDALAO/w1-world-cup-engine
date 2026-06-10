# W1 Real Fixture Card 1489371

**Match:** Brazil vs Morocco  
**Fixture:** `api-football:1489371`  
**Round:** Group Stage - 1  
**Kickoff UTC:** 2026-06-13T22:00:00Z  
**Kickoff CST:** 2026-06-14 06:00  
**Venue:** MetLife Stadium, New York New Jersey, USA  
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
| 1X2 | Home=1.62 | Draw=3.60 | Away=5.60 |
| AH | Home -1=2.15, Away -1=1.70, Home -0.5=1.62, Away -0.5=2.30 |
| OU | Over 1.5=1.33, Under 1.5=3.25, Over 2.5=2.00, Under 2.5=1.80, Over 3.5=3.45, Under 3.5=1.30 |
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
