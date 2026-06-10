# W1 Real Fixture Card 1489379

**Match:** Saudi Arabia vs Uruguay  
**Fixture:** `api-football:1489379`  
**Round:** Group Stage - 1  
**Kickoff UTC:** 2026-06-15T22:00:00Z  
**Kickoff CST:** 2026-06-16 06:00  
**Venue:** Hard Rock Stadium, Miami, USA  
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
| 1X2 | Home=8.30 | Draw=4.10 | Away=1.41 |
| AH | Home +0.5=2.65, Away +0.5=1.48, Home +1=2.15, Away +1=1.70, Home +1.5=1.62, Away +1.5=2.30 |
| OU | Over 1.5=1.30, Under 1.5=3.35, Over 2.5=1.95, Under 2.5=1.83, Over 3.5=3.40, Under 3.5=1.30 |
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
