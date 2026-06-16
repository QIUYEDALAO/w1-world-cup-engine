#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 predict overlay split checker (W1_PREDICT_OVERLAY_SPLIT_V1).

Enforces that the local predict server never writes runtime state back into the
tracked source cards. Predict writes only to gitignored runtime overlays
(state/w1_live_refresh_state.json, state/w1_lineup_runtime_overlay.json) and to the
tracked facts ledger (data/results/round1_results.json); build merges these in
memory (apply_runtime_lineup_overlay / lineup_overlay_cache / result_overlay) so the
source cards stay frozen.

Static guards (fast, deterministic — no server spin-up):
  1. predict server defines NONE of the old card-writer functions and has no
     card-write idiom (write_json(path, card) / card["..."] = ...).
  2. predict server HAS the overlay/facts writers.
  3. build HAS the overlay-merge wiring.
  4. NO tracked source card carries runtime fields (live_refresh / result fields).
  5. .gitignore covers state/ (the runtime overlays); the runtime overlays are NOT
     tracked; the facts ledger round1_results.json stays tracked.

This strengthens the no-pollution invariant and changes no model behaviour. The
end-to-end "running /predict leaves CARDS_DIR with zero git diff" proof is exercised
by check_w1_click_to_predict / check_w1_manual_lineup_override (which run a real
/predict) and recorded in reports/W1_PREDICT_OVERLAY_SPLIT_V1_RESULT.md.
"""
from __future__ import annotations

import glob
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "scripts/w1_local_predict_server.py"
BUILD = ROOT / "scripts/build_w1_dashboard_data.py"
CARDS_DIR = ROOT / "data/processed/match_cards/group_stage_round1"
GITIGNORE = ROOT / ".gitignore"

RUNTIME_CARD_FIELDS = (
    "live_refresh",
    "status",
    "actual_score",
    "actual_score_display_cn",
    "result_source",
    "result_note",
    "result_synced_at_utc",
)
FORBIDDEN_CARD_WRITERS = (
    "def write_lineups_to_card",
    "def write_live_refresh_to_card",
    "def write_result_to_card",
)
FORBIDDEN_CARD_WRITE_IDIOMS = (
    "write_json(path, card)",
    "write_json(card_path",
    'card["live_refresh"]',
    'card["status"]',
    'card["actual_score"]',
    'card["lineups"]',
    'card["risk_flags"]',
    'card["data_gaps"]',
)
REQUIRED_OVERLAY_WRITERS = (
    "def write_lineups_overlay",
    "def write_live_refresh_state",
    "def write_result_overlay",
)
REQUIRED_BUILD_MERGE = (
    "def apply_runtime_lineup_overlay",
    "def lineup_overlay_cache",
    "LINEUP_RUNTIME_OVERLAY",
)
RUNTIME_OVERLAYS_MUST_BE_UNTRACKED = (
    "state/w1_live_refresh_state.json",
    "state/w1_lineup_runtime_overlay.json",
)

errors: list[str] = []


def fail(message: str) -> None:
    errors.append(message)


def tracked(rel: str) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", rel],
        cwd=ROOT, capture_output=True, text=True,
    )
    return result.returncode == 0


def main() -> int:
    # 1 + 2. predict server: no card writers / idioms; has overlay writers
    if not SERVER.is_file():
        fail("predict server missing")
    else:
        src = SERVER.read_text(encoding="utf-8")
        for fn in FORBIDDEN_CARD_WRITERS:
            if fn in src:
                fail(f"predict server still defines a source-card writer: {fn}")
        for idiom in FORBIDDEN_CARD_WRITE_IDIOMS:
            if idiom in src:
                fail(f"predict server still has a source-card write idiom: {idiom}")
        for fn in REQUIRED_OVERLAY_WRITERS:
            if fn not in src:
                fail(f"predict server missing overlay/facts writer: {fn}")

    # 3. build: overlay-merge wiring present
    if not BUILD.is_file():
        fail("build script missing")
    else:
        b = BUILD.read_text(encoding="utf-8")
        for token in REQUIRED_BUILD_MERGE:
            if token not in b:
                fail(f"build script missing overlay-merge wiring: {token}")

    # 4. no tracked source card carries runtime fields
    cards = sorted(glob.glob(str(CARDS_DIR / "*.json")))
    if not cards:
        fail(f"no source cards found under {CARDS_DIR.relative_to(ROOT)}")
    polluted = []
    for path in cards:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        bad = [key for key in RUNTIME_CARD_FIELDS if key in data]
        if bad:
            polluted.append((Path(path).name, bad))
    for name, bad in polluted[:6]:
        fail(f"source card carries runtime fields {bad} (must live in overlay/ledger): {name}")
    if len(polluted) > 6:
        fail(f"...and {len(polluted) - 6} more source cards carry runtime fields")

    # 5. gitignore + tracking policy
    gi = GITIGNORE.read_text(encoding="utf-8") if GITIGNORE.is_file() else ""
    if "state/" not in gi:
        fail(".gitignore must ignore state/ (predict runtime overlays)")
    for rel in RUNTIME_OVERLAYS_MUST_BE_UNTRACKED:
        if tracked(rel):
            fail(f"runtime overlay must NOT be tracked (gitignored): {rel}")
    if not tracked("data/results/round1_results.json"):
        fail("facts ledger data/results/round1_results.json must stay tracked")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"W1 predict overlay split check FAIL ({len(errors)})")
        return 1
    print(
        "W1 predict overlay split check PASS "
        "(predict writes overlays/ledger only; source cards carry no runtime fields; overlays gitignored)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
