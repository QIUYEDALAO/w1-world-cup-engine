# W1 Watcher Status

**Status:** READY  
**Checked at:** 2026-06-10 15:30 CST  
**Next run:** 2026-06-10 18:00 CST

## Files

| Path | Status | Purpose |
|---|---|---|
| `scripts/w1_watcher.sh` | READY | Local W1 refresh watcher |
| `locks/` | READY | Runtime lock directory |
| `logs/` | READY | Runtime log directory |
| `state/w1_refresh_state.json` | READY | Watcher state and next run metadata |

## Schedule

| Type | Time |
|---|---|
| Normal | 00:00 CST |
| Normal | 06:00 CST |
| Normal | 12:00 CST |
| Normal | 18:00 CST |
| Mexico vs South Africa special | T-2h |
| Mexico vs South Africa special | T-1h |
| Mexico vs South Africa special | T-30m |

## Validation

- `bash -n scripts/w1_watcher.sh`: PASS
- dry-run: PASS
- credential literal scan: PASS
- old-system path scan: PASS
- disallowed output scan: PASS
- remote status: no remote

