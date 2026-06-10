# W1 Real Fixture Card 1539016

**Match:** Iraq vs Norway  
**Fixture:** `api-football:1539016`  
**Round:** Group Stage - 1  
**Kickoff UTC:** 2026-06-16T22:00:00Z  
**Kickoff CST:** 2026-06-17 06:00  
**Venue:** Gillette Stadium, Boston, USA  
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
| 1X2 | Home=11.50 | Draw=6.40 | Away=1.21 |
| AH | Home +2=1.73, Away +2=2.05, Home +1.5=2.20, Away +1.5=1.62 |
| OU | Over 1.5=1.18, Under 1.5=4.75, Over 2.5=1.57, Under 2.5=2.38, Over 3.5=2.40, Under 3.5=1.55 |
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
