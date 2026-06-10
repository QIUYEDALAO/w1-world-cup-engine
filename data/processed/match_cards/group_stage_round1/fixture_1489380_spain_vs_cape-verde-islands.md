# W1 Real Fixture Card 1489380

**Match:** Spain vs Cape Verde Islands  
**Fixture:** `api-football:1489380`  
**Round:** Group Stage - 1  
**Kickoff UTC:** 2026-06-15T16:00:00Z  
**Kickoff CST:** 2026-06-16 00:00  
**Venue:** Mercedes-Benz Stadium, Atlanta, USA  
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
| 1X2 | Home=1.09 | Draw=8.70 | Away=27.00 |
| AH | Home -3=2.25, Away -3=1.65, Home -2=1.50, Away -2=2.60, Home -2.5=1.90, Away -2.5=1.91 |
| OU | Over 1.5=1.10, Under 1.5=6.50, Over 2.5=1.35, Under 2.5=3.10, Over 3.5=1.90, Under 3.5=1.85 |
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
