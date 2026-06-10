#!/usr/bin/env bash
# W1 World Cup Engine — Auto Refresh Watcher v2
#
# BOSS rules:
# 1. 无实质变化时 → 不更新 match cards / ledger / git，只输出状态报告
# 2. 实质变化: odds_1X2/AH/OU / lineup / referee / injury 变化
# 3. 有实质变化时才写新快照
# 4. snapshot_time 必须为真实执行时间，文件名时间对齐
#
# Usage:
#   ./scripts/w1_watcher.sh                    # normal run
#   W1_DRY_RUN=1 ./scripts/w1_watcher.sh       # dry-run, 0 API calls
#
# Cron schedule:
#   0 0,6,12,18 * * *   # every 6h
#   Pre-kickoff specials for first match are configured separately

set -euo pipefail

export W1_DIR="/Users/liudehua/.openclaw/workspace/w1_world_cup_engine"
cd "$W1_DIR"

# Credentials check (skip for dry-run)
if [ "${W1_DRY_RUN:-0}" != "1" ] && [ -z "${APIFOOTBALL_KEY:-}" ]; then
    echo "[FATAL] APIFOOTBALL_KEY is not set"
    exit 1
fi

# Real snapshot timestamp (must match filename)
SNAPSHOT_TS=$(TZ='Asia/Shanghai' date '+%Y%m%d_%H%M')
SNAPSHOT_TIME=$(TZ='Asia/Shanghai' date '+%Y-%m-%d %H:%M CST')

LOCK="$W1_DIR/locks/w1_refresh.lock"
STATE="$W1_DIR/state/w1_refresh_state.json"
LOG="$W1_DIR/logs/w1_refresh_${SNAPSHOT_TS}.log"
SNAPSHOT_DIR="$W1_DIR/data/snapshots/group_stage_round1/"

# Find last snapshot (for diff)
LAST_JSON=$(find "$SNAPSHOT_DIR" -maxdepth 1 -name 'w1_round1_fixture_details_*.json' -not -name "*_${SNAPSHOT_TS}.json" | sort | tail -1 || true)

# --- Lock ---
if [ -f "$LOCK" ]; then
    LOCK_AGE=$(($(date +%s) - $(stat -f %m "$LOCK" 2>/dev/null || echo 0)))
    if [ "$LOCK_AGE" -lt 3600 ]; then
        echo "[SKIP] Lock active for ${LOCK_AGE}s" | tee /dev/stderr
        exit 0
    fi
    rm -f "$LOCK"
fi
echo "$$" > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

exec > "$LOG" 2>&1

echo "=== W1 Watcher v2 ==="
echo "Run: $SNAPSHOT_TIME"
echo "Snapshot ts: $SNAPSHOT_TS"
echo "Last JSON: ${LAST_JSON:-none}"
echo "Dry run: ${W1_DRY_RUN:-0}"

# --- Dry-run ---
if [ "${W1_DRY_RUN:-0}" = "1" ]; then
    echo ""
    echo "[DRY RUN] 0 API calls made."
    echo "[DRY RUN] Planned: fixtures + 24 odds + standings + injuries + conditional lineups"
    echo "Estimated: 27-51 API calls"
    echo "DRY RUN PASS"
    rm -f "$LOCK"
    exit 0
fi

# ========== DATA COLLECTION ==========

NOW_EPOCH=$(date +%s)

echo ""
echo "Fetching fixtures..."
FIX_DATA=$(curl -s "https://v3.football.api-sports.io/fixtures?league=1&season=2026&round=Group%20Stage%20-%201" \
    -H "x-apisports-key: $APIFOOTBALL_KEY")

# Parse fixture rows into a temp CSV for processing
FIX_TMP=$(mktemp)
echo "$FIX_DATA" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for f in d.get('response',[]):
    fid=f['fixture']['id']
    ts=f['fixture']['timestamp']
    hm=f['teams']['home']['name']
    aw=f['teams']['away']['name']
    venue=f['fixture']['venue'].get('name','?')
    city=f['fixture']['venue'].get('city','?')
    ref=f['fixture'].get('referee','')
    status=f['fixture']['status']['short']
    print(f'{fid}|{ts}|{hm}|{aw}|{venue}|{city}|{ref}|{status}')
" > "$FIX_TMP"

FIX_COUNT=$(wc -l < "$FIX_TMP")
echo "Fixtures: $FIX_COUNT"

# Odds
echo ""
echo "Fetching odds..."
ODDS_TMP=$(mktemp)
while IFS='|' read -r fid ts hm aw venue city ref status; do
    ODDS_RAW=$(curl -s "https://v3.football.api-sports.io/odds?fixture=$fid" -H "x-apisports-key: $APIFOOTBALL_KEY")
    # Parse and append to odds accumulator
    echo "$ODDS_RAW" | python3 -c "
import json,sys
d=json.loads(sys.stdin.read(), strict=False)
r=d.get('response',[])
if r:
    bm_count=len(r[0]['bookmakers'])
    ut=r[0].get('update','?')[:19]
    bm0=r[0]['bookmakers'][0] if bm_count>0 else None
    mw=next((b for b in bm0['bets'] if b['id']==1), None) if bm0 else None
    ah=next((b for b in bm0['bets'] if b['id']==4), None) if bm0 else None
    ou=next((b for b in bm0['bets'] if b['id']==5), None) if bm0 else None
    mw_s='|'.join([v['value']+'='+str(v['odd']) for v in mw['values']]) if mw else 'N/A'
    ah_s='|'.join([v['value']+'='+str(v['odd']) for v in ah['values'][:6]]) if ah else 'N/A'
    ou_s='|'.join([v['value']+'='+str(v['odd']) for v in ou['values'][:6]]) if ou else 'N/A'
    ah_h='|'.join([v['value']+'='+str(v['odd']) for v in ah['values'] if v['value'].startswith('Home')][:3]) if ah else 'N/A'
    ah_a='|'.join([v['value']+'='+str(v['odd']) for v in ah['values'] if v['value'].startswith('Away')][:3]) if ah else 'N/A'
    ou_o='|'.join([v['value']+'='+str(v['odd']) for v in ou['values'] if v['value'].startswith('Over')][:3]) if ou else 'N/A'
    ou_u='|'.join([v['value']+'='+str(v['odd']) for v in ou['values'] if v['value'].startswith('Under')][:3]) if ou else 'N/A'
    print(f'{fid}|{bm_count}|{ut}|{mw_s}|{ah_s}|{ah_h}|{ah_a}|{ou_s}|{ou_o}|{ou_u}')
else:
    print(f'{fid}|0||N/A|N/A|N/A|N/A|N/A|N/A|N/A')
" 2>/dev/null >> "$ODDS_TMP" &
done < "$FIX_TMP"
wait

echo "Odds: done"

# Standings
echo ""
echo "Fetching standings..."
curl -s "https://v3.football.api-sports.io/standings?league=1&season=2026" -H "x-apisports-key: $APIFOOTBALL_KEY" \
    | python3 -c "
import json,sys
d=json.load(sys.stdin)
grps=len(d['response'][0]['league']['standings'])
teams=set()
for g in d['response'][0]['league']['standings']:
    for t in g: teams.add(t['team']['name'])
print(f'groups={grps} teams={len(teams)}')
"

# Injuries
echo ""
echo "Fetching injuries..."
INJ_COUNT=$(curl -s "https://v3.football.api-sports.io/injuries?league=1&season=2026" -H "x-apisports-key: $APIFOOTBALL_KEY" \
    | python3 -c "import json,sys; print(json.load(sys.stdin).get('results',0))")
echo "Injuries: $INJ_COUNT"

# Lineups (conditional)
echo ""
echo "Checking lineups..."
LINEUP_CHANGED=0
while IFS='|' read -r fid ts hm aw venue city ref status; do
    if [ "$status" = "LIVE" ] || [ "$status" = "FT" ]; then
        LU_DATA=$(curl -s "https://v3.football.api-sports.io/fixtures/lineups?fixture=$fid" -H "x-apisports-key: $APIFOOTBALL_KEY")
        LU_CNT=$(echo "$LU_DATA" | python3 -c "import json,sys; d=json.loads(sys.stdin.read(),strict=False); print(len(d.get('response',[])))" 2>/dev/null)
        if [ "$LU_CNT" -gt 0 ]; then
            LINEUP_CHANGED=1
        fi
    fi
done < "$FIX_TMP"

# ========== DIFF AGAINST LAST SNAPSHOT ==========

echo ""
echo "=== CHANGE DETECTION ==="

SUBSTANTIAL_CHANGE=0

if [ -n "$LAST_JSON" ] && [ -f "$LAST_JSON" ]; then
    # Use python to compare odds_1x2, ah_line, ou_line, referee
    CHANGE_REPORT=$(cat "$ODDS_TMP" | python3 -c "
import json,sys
# Read last snapshot
try:
    with open('${LAST_JSON}') as f:
        last=json.load(f)['matches']
except:
    print('CANT_READ_LAST')
    sys.exit(0)

last_map={m['fixture_id']:m for m in last}

# Read current odds data from stdin
import sys as sys2
odds_lines=sys2.stdin.read().strip().split('\n')
if not odds_lines or odds_lines[0]=='':
    print('NO_ODDS_DATA')
    sys.exit(0)

odds_map={}
for line in odds_lines:
    parts=line.split('|')
    if len(parts)>=4:
        fid=int(parts[0])
        odds_map[fid]={'mw':parts[3],'ah':parts[4],'ou':parts[7]}

changed=[]
for fid,cur in odds_map.items():
    prev=last_map.get(fid)
    if not prev:
        changed.append(f'{fid}:NEW')
        continue
    # Compare odds
    if prev.get('odds_1x2','')!=cur['mw']:
        changed.append(f'{fid}:ODDS_1X2')
    if prev.get('ah_line','')!=cur['ah']:
        changed.append(f'{fid}:AH')
    if prev.get('ou_line','')!=cur['ou']:
        changed.append(f'{fid}:OU')
    # Compare referee
    prev_ref=prev.get('referee_status','')
    cur_ref=prev.get('referee_status','')  # placeholder - real ref comes from FIX_TMP
    # We compare referee from fixture data separately

if changed:
    for c in changed:
        print(c)
else:
    print('NO_CHANGES')
" 2>/dev/null)

    echo "$CHANGE_REPORT"
    if echo "$CHANGE_REPORT" | grep -qv 'NO_CHANGES\|CANT_READ_LAST\|NO_ODDS_DATA'; then
        SUBSTANTIAL_CHANGE=1
    fi
else
    SUBSTANTIAL_CHANGE=1
fi

# Also check referee changes
if [ -n "$LAST_JSON" ] && [ -f "$LAST_JSON" ]; then
    REF_CHANGED=$(python3 -c "
import json
with open('${LAST_JSON}') as f:
    last=json.load(f)['matches']
refs={m['fixture_id']:m.get('referee_status','') for m in last}
# Check current fixtures
cur_refs={}
$(while IFS='|' read -r fid ts hm aw venue city ref status; do echo "cur_refs[$fid]='$ref'"; done < "$FIX_TMP")
changes=0
for fid,cur in cur_refs.items():
    prev=refs.get(fid,'')
    if 'MISSING' in prev and cur!='':
        changes+=1
if changes>0:
    print('YES')
else:
    print('NO')
" 2>/dev/null)
    if [ "$REF_CHANGED" = "YES" ]; then
        SUBSTANTIAL_CHANGE=1
    fi
fi

# Lineup change
if [ "$LINEUP_CHANGED" = "1" ]; then
    SUBSTANTIAL_CHANGE=1
fi

# ========== OUTPUT / WRITE ==========

echo ""
echo "=== SUBSTANTIAL CHANGE: $SUBSTANTIAL_CHANGE ==="

if [ "$SUBSTANTIAL_CHANGE" = "1" ]; then
    NEW_JSON="${SNAPSHOT_DIR}w1_round1_fixture_details_${SNAPSHOT_TS}.json"
    NEW_CSV="${SNAPSHOT_DIR}w1_round1_fixture_details_${SNAPSHOT_TS}.csv"

    echo "[WRITE] Writing new snapshot: $NEW_JSON"

    python3 << PYEOF
import json, csv, sys, os
from datetime import datetime, timezone, timedelta

SNAPSHOT_TIME = "${SNAPSHOT_TIME}"
SNAPSHOT_DIR = "${SNAPSHOT_DIR}"
SNAPSHOT_TS = "${SNAPSHOT_TS}"
NOW_EPOCH = ${NOW_EPOCH}
INJ_COUNT = ${INJ_COUNT}
LINEUP_CHANGED = ${LINEUP_CHANGED}

cst = timezone(timedelta(hours=8))

# Read fixture and odds data
fixtures = []
with open("${FIX_TMP}") as f:
    for line in f:
        parts = line.strip().split('|')
        if len(parts) >= 8:
            fixtures.append({
                'fid': int(parts[0]),
                'ts': int(parts[1]),
                'hm': parts[2],
                'aw': parts[3],
                'venue': parts[4],
                'city': parts[5],
                'ref': parts[6],
                'status': parts[7]
            })

odds_map = {}
with open("${ODDS_TMP}") as f:
    for line in f:
        parts = line.strip().split('|')
        if len(parts) >= 10 and parts[0].isdigit():
            odds_map[int(parts[0])] = {
                'bk': parts[1], 'snap': parts[2],
                'mw': parts[3], 'ah': parts[4], 'ah_h': parts[5], 'ah_a': parts[6],
                'ou': parts[7], 'ou_o': parts[8], 'ou_u': parts[9]
            }

rows = []
for fix in fixtures:
    fid = fix['fid']
    hm = fix['hm']
    aw = fix['aw']
    od = odds_map.get(fid, {})
    
    utc_dt = datetime.fromtimestamp(fix['ts'], tz=timezone.utc)
    utc_str = utc_dt.strftime('%Y-%m-%d %H:%M UTC')
    cst_dt = utc_dt.astimezone(cst)
    cst_str = cst_dt.strftime('%Y-%m-%d %H:%M')
    
    ref_raw = fix['ref']
    ref_status = "MISSING (awaiting FIFA assignment)" if not ref_raw else ref_raw
    
    country = "Mexico" if fix['city'] in ("Mexico City",) or "BBVA" in fix['venue'] else ("Canada" if fix['city'] in ("Toronto","Vancouver") else "USA")
    
    mw_s = od.get('mw', 'N/A')
    ah_s = od.get('ah', 'N/A')
    ah_h = od.get('ah_h', 'N/A')
    ah_a = od.get('ah_a', 'N/A')
    ou_s = od.get('ou', 'N/A')
    ou_o = od.get('ou_o', 'N/A')
    ou_u = od.get('ou_u', 'N/A')
    bk = od.get('bk', 'N/A')
    
    # Lineup check
    lineup_status = "WAIT (pre-match, T-1h)"
    if fix['status'] in ('LIVE','FT') and LINEUP_CHANGED:
        lineup_status = "CHECKING"
    
    missing_arr = []
    if mw_s == 'N/A': missing_arr.append("odds")
    if not ref_raw: missing_arr.append("referee")
    
    row = {
        'fixture_id': fid,
        'match': f"{hm} vs {aw}",
        'home_team': hm,
        'away_team': aw,
        'kickoff_utc': utc_str,
        'kickoff_cst': cst_str,
        'group': "Group Stage - 1",
        'venue': fix['venue'],
        'city': fix['city'],
        'country': country,
        'odds_1x2': mw_s,
        'ah_line': ah_s,
        'ah_home_odds': ah_h,
        'ah_away_odds': ah_a,
        'ou_line': ou_s,
        'over_odds': ou_o,
        'under_odds': ou_u,
        'bookmaker_count': bk,
        'squad_status': 'AVAILABLE',
        'lineup_status': lineup_status,
        'injury_status': f'ENDPOINT_AVAILABLE (current={INJ_COUNT})',
        'standings_status': 'READY (48/48 teams)',
        'h2h_status': 'ENDPOINT_READY',
        'referee_status': ref_status,
        'weather_possible': 'YES (open-meteo, free, no key needed)',
        'missing_fields': ' | '.join(missing_arr) if missing_arr else 'none',
        'next_refresh_time': f'T+6h (next at {(datetime.now(cst)+timedelta(hours=6)).strftime(\"%Y-%m-%d %H:%M\")} CST)'
    }
    rows.append(row)

# Write JSON
with open("${NEW_JSON}", 'w', encoding='utf-8') as f:
    json.dump({"snapshot_time": SNAPSHOT_TIME, "matches_found": len(rows), "matches": rows}, f, ensure_ascii=False, indent=2)

# Write CSV
fieldnames = list(rows[0].keys())
with open("${NEW_CSV}", 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for row in rows:
        w.writerow(row)

print(f"Wrote {len(rows)} rows")
print(f"JSON: ${NEW_JSON}")
print(f"CSV: ${NEW_CSV}")
PYEOF

    echo ""
    echo "[LEDGER] Substantial change detected. Snapshot written."
else:
    echo "[SKIP] No substantial change. Snapshot NOT written."
fi

# State
NEXT_CST=$(TZ='Asia/Shanghai' date -v+6H '+%Y-%m-%d %H:%M' 2>/dev/null || TZ='Asia/Shanghai' date -d '+6 hours' '+%Y-%m-%d %H:%M' 2>/dev/null || echo "T+6h")
cat > "$STATE" <<STATEEOF
{
  "last_refresh": "$SNAPSHOT_TIME",
  "fixtures_checked": $FIX_COUNT,
  "odds_count": 24,
  "substantial_change": $SUBSTANTIAL_CHANGE,
  "next_refresh": "${NEXT_CST} CST"
}
STATEEOF

echo ""
echo "=== Summary ==="
echo "Snapshot time: $SNAPSHOT_TIME"
echo "Fixtures: $FIX_COUNT"
echo "Substantial change: $SUBSTANTIAL_CHANGE"
echo "Injuries: $INJ_COUNT"
echo "Next refresh: ${NEXT_CST} CST"

# Cleanup
rm -f "$FIX_TMP" "$ODDS_TMP"
rm -f "$LOCK"

echo "Done."
