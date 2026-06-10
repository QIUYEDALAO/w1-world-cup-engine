# W1 Real Fixture Card 1489370

**Match:** USA vs Paraguay  
**Fixture:** `api-football:1489370`  
**Round:** Group Stage - 1  
**Kickoff UTC:** 2026-06-13T01:00:00Z  
**Kickoff CST:** 2026-06-13 09:00  
**Venue:** SoFi Stadium, Los Angeles, USA  
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
| 1X2 | Home=1.98 | Draw=3.30 | Away=4.00 |
| AH | Home -0.5=1.95, Away -0.5=1.85, Home +0=1.42, Away +0=2.85 |
| OU | Over 1.5=1.42, Under 1.5=2.80, Over 2.5=2.25, Under 2.5=1.62, Over 3.5=4.20, Under 3.5=1.22 |
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
