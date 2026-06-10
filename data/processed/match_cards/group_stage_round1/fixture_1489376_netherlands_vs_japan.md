# W1 Real Fixture Card 1489376

**Match:** Netherlands vs Japan  
**Fixture:** `api-football:1489376`  
**Round:** Group Stage - 1  
**Kickoff UTC:** 2026-06-14T20:00:00Z  
**Kickoff CST:** 2026-06-15 04:00  
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
| 1X2 | Home=1.95 | Draw=3.50 | Away=3.65 |
| AH | Home -0.5=1.95, Away -0.5=1.85, Home +0=1.45, Away +0=2.75 |
| OU | Over 1.5=1.30, Under 1.5=3.45, Over 2.5=1.93, Under 2.5=1.85, Over 3.5=3.40, Under 3.5=1.30 |
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
