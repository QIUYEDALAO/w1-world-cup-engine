#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 runtime artifact policy checker (W1_RUNTIME_ARTIFACT_TRIAGE_V1).

Enforces the corrected "治本" tracking policy:
  * UNTRACKED (regenerable runtime): reports/dashboard/assets/w1_dashboard_data.json, state/*
    except the four W1_SCOUT learning-memory files explicitly persisted in git
  * TRACKED (source / template / facts — must NOT be untracked):
      match_cards/*.json, reports/dashboard/W1_VISUAL_DASHBOARD.html, data/results/round1_results.json
  * GITIGNORED (local/generated, never committed): data/local_odds/, data/processed/international/, the 2 untracked targets
  * EVIDENCE present + committable: the two local-odds QC reports

This guards against (a) re-tracking runtime artifacts that get dirtied by predict/
watcher/build, and (b) accidentally untracking source data (which would break a
fresh clone). It changes no model behavior.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GITIGNORE = ROOT / ".gitignore"

MUST_BE_UNTRACKED = ["reports/dashboard/assets/w1_dashboard_data.json"]
TRACKED_SCOUT_MEMORY = {
    "state/scout_audit.jsonl",
    "state/scout_track_record.json",
    "state/scout_lessons.md",
    "state/scout_lock.jsonl",
}
MUST_BE_TRACKED = [
    "reports/dashboard/W1_VISUAL_DASHBOARD.html",
    "data/results/round1_results.json",
]
MUST_BE_TRACKED_GLOB = ["data/processed/match_cards/group_stage_round1"]  # >=1 tracked
MUST_BE_GITIGNORED_PATTERNS = [
    "reports/dashboard/assets/w1_dashboard_data.json",
    "state/*",
    "!state/scout_audit.jsonl",
    "!state/scout_track_record.json",
    "!state/scout_lessons.md",
    "!state/scout_lock.jsonl",
    "data/local_odds/",
    "data/processed/international/",
]
QC_EVIDENCE = [
    "reports/W1_LOCAL_ODDS_2026_QUALITY_CHECK.md",
    "reports/W1_LOCAL_ODDS_HISTORICAL_QUALITY_CHECK.md",
]
REBUILD_CMD = "W1_DISABLE_API_ENV_BRIDGE=1 python3 scripts/build_w1_dashboard_data.py  # regenerates dashboard_data.json + state"

errors: list[str] = []


def fail(m: str) -> None:
    errors.append(m)


def tracked(rel: str) -> bool:
    r = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=ROOT,
                       capture_output=True, text=True)
    return r.returncode == 0


def tracked_under(rel_dir: str) -> list[str]:
    r = subprocess.run(["git", "ls-files", rel_dir], cwd=ROOT, capture_output=True, text=True)
    return [x for x in r.stdout.splitlines() if x.strip()]


def main() -> int:
    # 1. runtime artifacts must NOT be tracked
    for rel in MUST_BE_UNTRACKED:
        if tracked(rel):
            fail(f"runtime artifact still tracked (should be git rm --cached): {rel}")
    tracked_state = set(tracked_under("state/"))
    unexpected_state = sorted(tracked_state - TRACKED_SCOUT_MEMORY)
    if unexpected_state:
        fail(f"runtime state still tracked outside Scout memory allowlist: {unexpected_state[:4]}")
    missing_memory = sorted(TRACKED_SCOUT_MEMORY - tracked_state)
    if missing_memory:
        fail(f"Scout learning memory file not tracked: {missing_memory}")

    # 2. source/template/facts must STAY tracked (guard against over-untracking)
    for rel in MUST_BE_TRACKED:
        if not tracked(rel):
            fail(f"source/template/facts file lost from tracking (must stay): {rel}")
    for d in MUST_BE_TRACKED_GLOB:
        if not tracked_under(d):
            fail(f"no tracked files under source dir (cards must stay tracked): {d}")

    # 3. gitignore patterns present
    gi = GITIGNORE.read_text(encoding="utf-8") if GITIGNORE.is_file() else ""
    for pat in MUST_BE_GITIGNORED_PATTERNS:
        if pat not in gi:
            fail(f".gitignore missing pattern: {pat}")

    # 4. generated/local data must NOT be tracked
    for d in ("data/local_odds", "data/processed/international"):
        t = tracked_under(d)
        if t:
            fail(f"generated/local data tracked (should be gitignored): {d} (e.g. {t[:2]})")

    # 5. QC evidence present and committable (exists + not gitignored)
    for rel in QC_EVIDENCE:
        p = ROOT / rel
        if not p.is_file():
            fail(f"QC evidence report missing from tree: {rel}")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"W1 runtime artifact policy check FAIL ({len(errors)})")
        print(f"rebuild runtime artifacts with: {REBUILD_CMD}")
        return 1
    print("W1 runtime artifact policy check PASS "
          "(dashboard_data.json + raw state untracked; Scout memory allowlisted; cards/HTML/results tracked; local/processed gitignored; QC evidence present)")
    print(f"rebuild runtime artifacts with: {REBUILD_CMD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
