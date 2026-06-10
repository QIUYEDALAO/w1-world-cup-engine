# W1 Real Fixture Card 1489384

**Match:** England vs Croatia  
**Fixture:** `api-football:1489384`  
**Round:** Group Stage - 1  
**Kickoff UTC:** 2026-06-17T20:00:00Z  
**Kickoff CST:** 2026-06-18 04:00  
**Venue:** AT&T Stadium, Dallas, USA  
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
| 1X2 | Home=1.71 | Draw=3.60 | Away=4.85 |
| AH | Home -1=2.30, Away -1=1.62, Home -0.5=1.70, Away -0.5=2.15 |
| OU | Over 1.5=1.36, Under 1.5=3.10, Over 2.5=2.10, Under 2.5=1.70, Over 3.5=3.85, Under 3.5=1.25 |
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
