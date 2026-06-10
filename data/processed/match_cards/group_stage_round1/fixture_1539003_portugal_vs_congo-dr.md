# W1 Real Fixture Card 1539003

**Match:** Portugal vs Congo DR  
**Fixture:** `api-football:1539003`  
**Round:** Group Stage - 1  
**Kickoff UTC:** 2026-06-17T17:00:00Z  
**Kickoff CST:** 2026-06-18 01:00  
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
| 1X2 | Home=1.25 | Draw=5.50 | Away=12.00 |
| AH | Home -2=2.25, Away -2=1.60, Home -1.5=1.73, Away -1.5=2.05 |
| OU | Over 1.5=1.20, Under 1.5=4.33, Over 2.5=1.65, Under 2.5=2.20, Over 3.5=2.60, Under 3.5=1.48 |
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
