# W1 Real Fixture Card 1489386

**Match:** Uzbekistan vs Colombia  
**Fixture:** `api-football:1489386`  
**Round:** Group Stage - 1  
**Kickoff UTC:** 2026-06-18T02:00:00Z  
**Kickoff CST:** 2026-06-18 10:00  
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
| 1X2 | Home=8.50 | Draw=4.30 | Away=1.39 |
| AH | Home +1=2.30, Away +1=1.62, Home +1.5=1.70, Away +1.5=2.15 |
| OU | Over 1.5=1.28, Under 1.5=3.50, Over 2.5=1.85, Under 2.5=1.90, Over 3.5=3.20, Under 3.5=1.33 |
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
