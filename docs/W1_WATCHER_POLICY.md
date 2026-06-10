# W1 Watcher Policy

**Status:** READY  
**Scope:** W1 only

## Schedule

Normal refresh windows use CST:

- 00:00
- 06:00
- 12:00
- 18:00

The first match, Mexico vs South Africa (`fixture_id=1489369`), also has special refresh windows before kickoff:

- 2h
- 1h
- 30m

The current recorded next run is `2026-06-10 18:00 CST`.

## Runtime Paths

- Script: `scripts/w1_watcher.sh`
- Lock directory: `locks/`
- Log directory: `logs/`
- State file: `state/w1_refresh_state.json`

## Safety

- Dry-run mode makes zero API calls.
- Validation checker does not call external APIs.
- Runtime credentials must come from the current environment.
- The watcher must not modify old systems.
- The watcher must not write disallowed distribution channels or status files.
- Remote configuration and push are outside watcher scope.

