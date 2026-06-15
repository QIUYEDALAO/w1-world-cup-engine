# W1 S1B Odds Extension V1 — OU / AH Local File Pipeline

## Status

Scaffold only. No OU/AH data files provided yet. Pipeline defaults to 1X2_ONLY.

## Stage

A1 (spec) / A2 (schema) / C1 (checker) — complete.
B1 (OU loader) / B2 (AH loader) / C2 (integration checker) / R1 (generated rows) — blocked, pending local OU/AH csv/xlsx.

## Boundary

- OU/AH values must be supplied as local csv or xlsx files. No scraping, no API, no procurement.
- Files live under `data/local_odds/`. Gitignored.
- Loader reads only local files; no network calls.
- `scripts/w1_score_engine.py` unchanged.
- `DEFAULT_RHO` unchanged.
- `config/w1_decision_policy.json` unchanged.
- `config/w1_odds_movement_thresholds.json` unchanged.

## File Layout (once B1/B2 land)

```
data/local_odds/
  w1_ou_odds_extension.csv    ← OU: columns date, home, away, ou_line, over_odds, under_odds
  w1_ah_odds_extension.csv    ← AH: columns date, home, away, ah_line, home_odds, away_odds
```

Both files are gitignored and require manual placement.

## Pipeline Mode Rule

| Condition | pipeline_mode |
|---|---|
| No OU file exists | 1X2_ONLY |
| OU file exists, match NOT covered | 1X2_ONLY |
| OU file exists, match covered | FULL |
| AH file exists, match covered | FULL (with AH data appended) |

FULL applies only to the covered subset. Uncovered matches remain 1X2_ONLY.
No FULL pipeline result is generated when no OU/AH file exists.

## Matching

Match is by (date, home_team, away_team). Team names use `config/w1_team_aliases.json` normalization.
If a (date, home, away) pair appears in the OU file, that match is "OU covered".
If it appears in the AH file, that match is "AH covered".

## Schema (this document is the spec)

### OU Row

| Field | Type | Required | Notes |
|---|---|---|---|
| date | YYYY-MM-DD | yes | Match date |
| home | string | yes | Normalized via w1_team_aliases |
| away | string | yes | Normalized via w1_team_aliases |
| ou_line | number | yes | Over/under line (e.g. 2.5) |
| over_odds | number | yes | Decimal odds for Over |
| under_odds | number | yes | Decimal odds for Under |

### AH Row

| Field | Type | Required | Notes |
|---|---|---|---|
| date | YYYY-MM-DD | yes | Match date |
| home | string | yes | Normalized via w1_team_aliases |
| away | string | yes | Normalized via w1_team_aliases |
| ah_line | number | yes | Asian handicap line (e.g. -0.5) |
| home_odds | number | yes | Decimal odds for home side of AH |
| away_odds | number | yes | Decimal odds for away side of AH |

## Checker Rules (C1)

See `scripts/check_w1_odds_extension.py` for executable rules.
Summary:
- spec file exists
- schema file exists
- no external-fetch imports in new loader scripts
- no OU/AH file → output BLOCKED | SKIP, no FULL pipeline
- no forbidden imports (requests, urllib, selenium, playwright, web_fetch)
- does not modify production model files
