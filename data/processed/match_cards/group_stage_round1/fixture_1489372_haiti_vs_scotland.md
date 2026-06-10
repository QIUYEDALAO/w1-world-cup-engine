# W1 Real Fixture Card 1489372

**Match:** Haiti vs Scotland  
**Fixture:** `api-football:1489372`  
**Round:** Group Stage - 1  
**Kickoff UTC:** 2026-06-14T01:00:00Z  
**Kickoff CST:** 2026-06-14 09:00  
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
| 1X2 | Home=6.20 | Draw=4.00 | Away=1.52 |
| AH | Home +0.5=2.50, Away +0.5=1.53, Home +1=1.90, Away +1=1.91, Home +1.5=1.62, Away +1.5=2.30 |
| OU | Over 1.5=1.28, Under 1.5=3.55, Over 2.5=1.85, Under 2.5=1.90, Over 3.5=3.25, Under 3.5=1.33 |
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
