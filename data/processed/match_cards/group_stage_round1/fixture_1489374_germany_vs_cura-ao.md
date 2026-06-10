# W1 Real Fixture Card 1489374

**Match:** Germany vs Curaçao  
**Fixture:** `api-football:1489374`  
**Round:** Group Stage - 1  
**Kickoff UTC:** 2026-06-14T17:00:00Z  
**Kickoff CST:** 2026-06-15 01:00  
**Venue:** NRG Stadium, Houston, USA  
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
| 1X2 | Home=1.03 | Draw=16.50 | Away=29.00 |
| AH | Home -3=1.53, Away -3=2.50, Home -3.5=1.90, Away -3.5=1.91 |
| OU | Over 2.5=1.18, Under 2.5=4.75, Over 3.5=1.48, Under 3.5=2.60, Over 4.5=2.10, Under 4.5=1.70 |
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
