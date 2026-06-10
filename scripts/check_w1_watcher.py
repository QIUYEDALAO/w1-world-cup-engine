#!/usr/bin/env python3
"""Local checker for W1 watcher runtime files."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WATCHER = ROOT / "scripts/w1_watcher.sh"
STATE = ROOT / "state/w1_refresh_state.json"
LOGS = ROOT / "logs"
LOCKS = ROOT / "locks"
POLICY = ROOT / "docs/W1_WATCHER_POLICY.md"
STATUS = ROOT / "reports/match_previews/W1_WATCHER_STATUS.md"

EXPECTED_NEXT_RUN = "2026-06-10 18:00 CST"
EXPECTED_HOURS = ["00:00", "06:00", "12:00", "18:00"]
FORBIDDEN_RUNTIME_TERMS = ["Q" + "Q", "offi" + "cial", "pend" + "ing"]
OLD_SYSTEM_TERMS = ["V" + "3", "V" + "4", "M" + "1"]
SECRET_LITERAL_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization|bearer)\s*[:=]\s*['\"][^'\"${}][^'\"]{8,}['\"]"
)


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def assert_paths() -> None:
    if not WATCHER.is_file():
        fail("scripts/w1_watcher.sh is missing")
    if not os.access(WATCHER, os.X_OK):
        fail("scripts/w1_watcher.sh must be executable")
    for directory in (LOGS, LOCKS, STATE.parent):
        if not directory.is_dir():
            fail(f"Missing directory: {directory.relative_to(ROOT)}")
    if not STATE.is_file():
        fail("state/w1_refresh_state.json is missing")
    if not POLICY.is_file():
        fail("docs/W1_WATCHER_POLICY.md is missing")
    if not STATUS.is_file():
        fail("reports/match_previews/W1_WATCHER_STATUS.md is missing")


def assert_state() -> None:
    state = json.loads(read(STATE))
    if state.get("next_run_cst") != EXPECTED_NEXT_RUN:
        fail("next_run_cst mismatch")
    if state.get("normal_refresh_hours_cst") != EXPECTED_HOURS:
        fail("normal_refresh_hours_cst mismatch")
    special = state.get("special_refresh", {})
    if special.get("fixture_id") != 1489369:
        fail("Mexico vs South Africa special fixture_id missing")
    if special.get("windows_before_kickoff") != ["2h", "1h", "30m"]:
        fail("special refresh windows mismatch")


def assert_script_static() -> None:
    text = read(WATCHER)
    if SECRET_LITERAL_RE.search(text):
        fail("watcher contains a credential literal")
    for term in OLD_SYSTEM_TERMS:
        if term in text:
            fail(f"watcher references old system term: {term}")
    for term in FORBIDDEN_RUNTIME_TERMS:
        if term in text:
            fail("watcher contains a disallowed channel/status term")
    if "source \"$HOME/.openclaw/secrets/" in text:
        fail("watcher must not source legacy secret files")
    if "W1_DRY_RUN" not in text:
        fail("watcher must support W1_DRY_RUN")


def assert_shell_checks() -> None:
    syntax = subprocess.run(["bash", "-n", str(WATCHER)], cwd=ROOT, text=True, capture_output=True)
    if syntax.returncode != 0:
        fail(f"bash -n failed: {syntax.stderr.strip()}")

    before = {path.name for path in LOGS.glob("w1_refresh_*.log")}
    env = os.environ.copy()
    env["W1_DRY_RUN"] = "1"
    env.pop("APIFOOTBALL_KEY", None)
    dry = subprocess.run([str(WATCHER)], cwd=ROOT, text=True, capture_output=True, env=env, timeout=60)
    if dry.returncode != 0:
        fail(f"dry-run failed: {dry.stderr.strip() or dry.stdout.strip()}")
    after = sorted(
        (path for path in LOGS.glob("w1_refresh_*.log") if path.name not in before),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not after:
        after = sorted(LOGS.glob("w1_refresh_*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not after:
        fail("dry-run did not create a log")
    dry_output = dry.stdout + "\n" + read(after[0])
    if "DRY RUN PASS" not in dry_output:
        fail("dry-run did not report PASS")
    if "0 API calls made" not in dry_output:
        fail("dry-run must make zero API calls")


def assert_remote_absent() -> None:
    remote = subprocess.run(["git", "remote", "-v"], cwd=ROOT, text=True, capture_output=True)
    if remote.stdout.strip():
        fail("git remote must not be configured")


def main() -> int:
    try:
        assert_paths()
        assert_state()
        assert_script_static()
        assert_shell_checks()
        assert_remote_absent()
    except CheckError as exc:
        print(f"W1 watcher self-test FAIL: {exc}", file=sys.stderr)
        return 1

    print("W1 watcher self-test PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
