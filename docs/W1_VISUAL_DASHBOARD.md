# W1 Visual Dashboard V1

**Artifact:** `reports/dashboard/W1_VISUAL_DASHBOARD.html`  
**Data:** `reports/dashboard/assets/w1_dashboard_data.json`  
**Group context:** `data/static/world_cup_2026_groups.json`

## Purpose

W1_VISUAL_DASHBOARD_V1 is a static, boss-facing dashboard for the World Cup 2026 W1 pre-match workflow. It is designed to be opened directly as an HTML file and does not require a web server.

## Contents

- Top status cards for `W1_WAIT`, `W1_WATCH`, `W1_PLAY`, and `W1_PASS`
- `watcher_version`
- `play_guard_version`
- `next_refresh`
- 12-group overview from Group A to Group L
- Advancement rules visualization
- Round of 32 placeholder
- Group standings template
- Third-place ranking template
- First match card for Mexico vs South Africa
- Report entrypoints for existing Markdown reports

## Data Policy

The dashboard is generated from local W1 artifacts:

- `data/processed/ledger/w1_ledger_group_stage_round1.csv`
- `data/processed/match_cards/group_stage_round1/*.json`
- `state/w1_refresh_state.json`
- `config/w1_decision_policy.json`

It does not call external APIs and does not predict standings or rankings.

## Validation

Run:

```bash
python3 scripts/check_w1_visual_dashboard.py
```

Expected:

```text
W1 visual dashboard self-test PASS
```

