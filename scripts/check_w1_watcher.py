#!/usr/bin/env python3
"""Local checker for W1 watcher runtime files."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WATCHER = ROOT / "scripts/w1_watcher.sh"
STATE = ROOT / "state/w1_refresh_state.json"
LOGS = ROOT / "logs"
LOCKS = ROOT / "locks"
POLICY = ROOT / "docs/W1_WATCHER_POLICY.md"
STATUS = ROOT / "reports/match_previews/W1_WATCHER_STATUS.md"

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


def parse_cst(value: str, field: str) -> datetime:
    if not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2} CST$", value or ""):
        fail(f"{field} must use YYYY-MM-DD HH:MM CST format")
    return datetime.strptime(value.removesuffix(" CST"), "%Y-%m-%d %H:%M")


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
    if state.get("normal_refresh_hours_cst") != EXPECTED_HOURS:
        fail("normal_refresh_hours_cst mismatch")
    next_run = parse_cst(state.get("next_run_cst", ""), "next_run_cst")
    last_refresh_raw = state.get("last_refresh")
    if last_refresh_raw:
        last_refresh = parse_cst(last_refresh_raw, "last_refresh")
        if next_run < last_refresh:
            fail("next_run_cst must not be before last_refresh")
        if next_run - last_refresh > timedelta(hours=24):
            fail("next_run_cst must be explainable within 24h of last_refresh")
    if next_run.strftime("%H:%M") not in EXPECTED_HOURS:
        fail("next_run_cst hour must align with normal refresh hours")
    special = state.get("special_refresh", {})
    if special:
        if not special.get("fixture_id"):
            fail("special refresh fixture_id missing")
        if not (special.get("windows_before_kickoff") or special.get("refresh_type")):
            fail("special refresh must explain either windows_before_kickoff or refresh_type")
        if special.get("snapshot_ts") and not re.match(r"^\d{8}_\d{4}$", str(special.get("snapshot_ts"))):
            fail("special refresh snapshot_ts format invalid")


def assert_script_static() -> None:
    text = read(WATCHER)
    if "Auto Refresh Watcher v2" not in text:
        fail("watcher must identify itself as v2")
    if "odds_1X2/AH/OU / lineup / referee / injury" not in text:
        fail("watcher must document the v2 substantial-change definition")
    if "No substantial change. Snapshot NOT written." not in text:
        fail("watcher must skip snapshot writes when there is no substantial change")
    if "SNAPSHOT_TS=$(TZ='Asia/Shanghai' date '+%Y%m%d_%H%M')" not in text:
        fail("watcher must use SNAPSHOT_TS for snapshot filenames")
    if 'json.dump({"snapshot_time": SNAPSHOT_TIME' not in text:
        fail("watcher must use SNAPSHOT_TIME inside snapshot JSON")
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


def assert_remote_safe() -> None:
    remote = subprocess.run(["git", "remote", "-v"], cwd=ROOT, text=True, capture_output=True)
    allowed = {
        "git@github.com:QIUYEDALAO/w1-world-cup-engine.git",
        "https://github.com/QIUYEDALAO/w1-world-cup-engine.git",
    }
    for line in remote.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] not in allowed:
            fail(f"git remote points outside W1 repo: {parts[1]}")
    state = json.loads(read(STATE))
    if state.get("boundaries", {}).get("pushed") is not False:
        fail("watcher runtime boundary must keep pushed=false")


def assert_scheduler_points_to_watcher() -> None:
    cron = subprocess.run(["crontab", "-l"], cwd=ROOT, text=True, capture_output=True)
    if cron.returncode != 0:
        fail("crontab is not readable")
    lines = [line for line in cron.stdout.splitlines() if "w1_watcher.sh" in line and not line.lstrip().startswith("#")]
    if not any("0 0,6,12,18 * * *" in line and "./scripts/w1_watcher.sh" in line for line in lines):
        fail("normal cron schedule must point to ./scripts/w1_watcher.sh")
    special_lines = [line for line in lines if "W1_REFRESH_NOW=1 ./scripts/w1_watcher.sh" in line]
    if len(special_lines) < 3:
        fail("first-match special cron entries must point to ./scripts/w1_watcher.sh")


def main() -> int:
    try:
        assert_paths()
        assert_state()
        assert_script_static()
        assert_shell_checks()
        assert_scheduler_points_to_watcher()
        assert_remote_safe()
    except CheckError as exc:
        print(f"W1 watcher self-test FAIL: {exc}", file=sys.stderr)
        return 1

    print("W1 watcher self-test PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
