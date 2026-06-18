#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Checker for W1_SCOUT G2 autopilot runner.

Validates the production loop contract without calling api-football or DeepSeek:
- policy exists and encodes dry-run/delta/failure/post-kickoff discipline.
- --dry-run exits cleanly and does not mutate runtime status.
- no effective delta does not call analyst/lock; review/calibration may refresh embed.
- analyst nonzero does not update sha/embed/lock and exits nonzero.
- raw state/ and data/scout/ remain runtime-only; the four Scout learning-memory
  files are explicitly allowed to be tracked.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/run_w1_scout_cycle.sh"
POLICY = ROOT / "config/w1_scout_autopilot_policy.json"
HTML_CHECK = ROOT / "scripts/check_w1_visual_dashboard.py"
SCOUT_CHECK = ROOT / "scripts/check_w1_scout.py"
SCOUT_MEMORY_ALLOWLIST = {
    "state/scout_audit.jsonl",
    "state/scout_track_record.json",
    "state/scout_lessons.md",
    "state/scout_lock.jsonl",
}

errors: list[str] = []


def fail(message: str) -> None:
    errors.append(message)


def run(cmd: list[str] | str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        env={**os.environ, **(env or {})},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=isinstance(cmd, str),
    )


def write_cmd(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -u\n" + body + "\n", encoding="utf-8")
    path.chmod(0o755)


def assert_policy() -> None:
    if not POLICY.is_file():
        fail("missing config/w1_scout_autopilot_policy.json")
        return
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    if policy.get("policy_version") != "W1_SCOUT_AUTOPILOT_G2_V1":
        fail("autopilot policy version mismatch")
    selection = policy.get("fixture_selection") or {}
    if selection.get("future_only_for_factor_fetch") is not True:
        fail("policy must require future-only factor fetch")
    if selection.get("started_or_finished_policy") != "audit_only":
        fail("policy must set started/finished fixtures to audit_only")
    if selection.get("no_post_match_fake_pre_match_factors") is not True:
        fail("policy must forbid fake pre-match factor backfill")
    delta = policy.get("delta_triggers") or {}
    if delta.get("no_delta_policy") != "do_not_call_ai_do_not_lock_audit_review_calibration_embed_only":
        fail("policy must make no-delta skip AI/lock while allowing review/calibration embed")
    failure = policy.get("failure_policy") or {}
    if failure.get("analyst_nonzero") != "do_not_update_sha_do_not_embed_do_not_lock_audit_calibration_exit_nonzero":
        fail("policy must block sha/embed/lock when analyst fails")
    dry = policy.get("dry_run_policy") or {}
    for key in ("no_external_fetch", "no_ai_call", "no_state_write", "no_embed", "no_lock"):
        if dry.get(key) is not True:
            fail(f"dry-run policy missing {key}=true")


def assert_runner_static() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    required = [
        "--dry-run",
        "W1_SCOUT_FORCE_HASH",
        "no effective delta -> skip DeepSeek and lock; audit/review/calibration visibility only",
        "run_audit_review_calibration",
        "W1_SCOUT_ENABLE_REVIEW",
        "W1_SCOUT_CALIBRATION_CMD",
        "W1_SCOUT_REVIEW_CMD",
        "analyst failed -> do not update sha, do not embed, do not lock; audit only",
        "future fixtures selected",
        "scout_cycle_status.json",
        "scout_cycle_errors.log",
        "persist_memory",
        "scout memory: cycle",
        "W1_SCOUT_DISABLE_MEMORY_COMMIT",
        "已开赛/完赛 fixture: 只 audit",
    ]
    for token in required:
        if token not in text:
            fail(f"runner missing token: {token}")
    if "--include-started" in text:
        fail("runner must not fetch started fixtures")
    if "scripts/w1_score_engine.py" in text or "DEFAULT_RHO" in text:
        fail("runner must not touch score engine/RHO")


def assert_dry_run() -> None:
    with tempfile.TemporaryDirectory(prefix="w1_scout_g2_dry_") as td:
        state = Path(td) / "state"
        state.mkdir()
        env = {"W1_SCOUT_STATE_DIR": str(state), "W1_SCOUT_FORCE_HASH": "dry", "W1_SCOUT_DISABLE_MEMORY_COMMIT": "1"}
        before = set(state.iterdir())
        proc = run(["bash", str(RUNNER), "--dry-run"], env=env)
        after = set(state.iterdir())
        if proc.returncode != 0:
            fail(f"dry-run failed: stdout={proc.stdout} stderr={proc.stderr}")
        if before != after:
            fail("dry-run must not write runtime state")
        if "no AI call" not in proc.stdout or "no state write" not in proc.stdout:
            fail("dry-run output must state no AI/no state write")


def assert_no_delta_blocks_ai_lock_allows_review_calibration_embed() -> None:
    with tempfile.TemporaryDirectory(prefix="w1_scout_g2_nodelta_") as td:
        root = Path(td)
        state = root / "state"
        state.mkdir()
        (state / ".scout_bundles.sha").write_text("same\n", encoding="utf-8")
        (state / "w1_scout_bundles.json").write_text('{"bundles":[]}\n', encoding="utf-8")
        dash = root / "dash.json"
        dash.write_text('{"match_records":[{"fixture_id":"F1","kickoff_utc":"2099-01-01T00:00:00Z"}]}\n', encoding="utf-8")
        marker = root / "marker"
        write_cmd(root / "fetch.sh", "touch \"$1/fetch\"".replace("$1", str(marker)))
        write_cmd(root / "build.sh", "touch \"" + str(marker) + "/build\"")
        write_cmd(root / "analyst.sh", "touch \"" + str(marker) + "/analyst\"")
        write_cmd(root / "embed.sh", "touch \"" + str(marker) + "/embed\"")
        write_cmd(root / "lock.sh", "touch \"" + str(marker) + "/lock\"")
        write_cmd(root / "audit.sh", "mkdir -p \"" + str(marker) + "\"; touch \"" + str(marker) + "/audit\"")
        write_cmd(root / "review.sh", "touch \"" + str(marker) + "/review\"")
        write_cmd(root / "calibration.sh", "touch \"" + str(marker) + "/calibration\"")
        marker.mkdir()
        env = {
            "W1_SCOUT_STATE_DIR": str(state),
            "W1_SCOUT_DASHBOARD_DATA": str(dash),
            "W1_SCOUT_FORCE_HASH": "same",
            "W1_SCOUT_FETCH_CMD": str(root / "fetch.sh"),
            "W1_SCOUT_BUILD_CMD": str(root / "build.sh"),
            "W1_SCOUT_ANALYST_CMD": str(root / "analyst.sh"),
            "W1_SCOUT_EMBED_CMD": str(root / "embed.sh"),
            "W1_SCOUT_LOCK_CMD": str(root / "lock.sh"),
            "W1_SCOUT_AUDIT_CMD": str(root / "audit.sh"),
            "W1_SCOUT_REVIEW_CMD": str(root / "review.sh"),
            "W1_SCOUT_CALIBRATION_CMD": str(root / "calibration.sh"),
            "W1_SCOUT_ENABLE_REVIEW": "1",
            "W1_SCOUT_DISABLE_MEMORY_COMMIT": "1",
        }
        proc = run(["bash", str(RUNNER)], env=env)
        if proc.returncode != 0:
            fail(f"no-delta runner failed: stdout={proc.stdout} stderr={proc.stderr}")
        for name in ("analyst", "lock"):
            if (marker / name).exists():
                fail(f"no-delta must not call {name}")
        if not (marker / "audit").exists():
            fail("no-delta must still allow audit")
        for name in ("review", "calibration", "embed"):
            if not (marker / name).exists():
                fail(f"no-delta should allow {name} for post-match review/calibration visibility")
        if (state / ".scout_bundles.sha").read_text(encoding="utf-8").strip() != "same":
            fail("no-delta must not rewrite sha")


def assert_analyst_fail_blocks_progress() -> None:
    with tempfile.TemporaryDirectory(prefix="w1_scout_g2_fail_") as td:
        root = Path(td)
        state = root / "state"
        state.mkdir()
        (state / ".scout_bundles.sha").write_text("old\n", encoding="utf-8")
        (state / "w1_scout_bundles.json").write_text('{"bundles":[]}\n', encoding="utf-8")
        dash = root / "dash.json"
        dash.write_text('{"match_records":[{"fixture_id":"F1","kickoff_utc":"2099-01-01T00:00:00Z"}]}\n', encoding="utf-8")
        marker = root / "marker"
        marker.mkdir()
        write_cmd(root / "ok.sh", "exit 0")
        write_cmd(root / "analyst_fail.sh", "touch \"" + str(marker) + "/analyst\"; exit 7")
        write_cmd(root / "embed.sh", "touch \"" + str(marker) + "/embed\"")
        write_cmd(root / "lock.sh", "touch \"" + str(marker) + "/lock\"")
        write_cmd(root / "audit.sh", "touch \"" + str(marker) + "/audit\"")
        write_cmd(root / "calibration.sh", "touch \"" + str(marker) + "/calibration\"")
        env = {
            "W1_SCOUT_STATE_DIR": str(state),
            "W1_SCOUT_DASHBOARD_DATA": str(dash),
            "W1_SCOUT_FORCE_HASH": "new",
            "W1_SCOUT_FETCH_CMD": str(root / "ok.sh"),
            "W1_SCOUT_BUILD_CMD": str(root / "ok.sh"),
            "W1_SCOUT_ANALYST_CMD": str(root / "analyst_fail.sh"),
            "W1_SCOUT_CHECK_CMD": str(root / "ok.sh"),
            "W1_SCOUT_EMBED_CMD": str(root / "embed.sh"),
            "W1_SCOUT_LOCK_CMD": str(root / "lock.sh"),
            "W1_SCOUT_AUDIT_CMD": str(root / "audit.sh"),
            "W1_SCOUT_CALIBRATION_CMD": str(root / "calibration.sh"),
            "W1_SCOUT_DISABLE_MEMORY_COMMIT": "1",
        }
        proc = run(["bash", str(RUNNER)], env=env)
        if proc.returncode == 0:
            fail("analyst failure must make runner exit nonzero")
        if (state / ".scout_bundles.sha").read_text(encoding="utf-8").strip() != "old":
            fail("analyst failure must not update sha")
        for name in ("embed", "lock"):
            if (marker / name).exists():
                fail(f"analyst failure must not call {name}")
        if not (marker / "audit").exists():
            fail("analyst failure may only continue to audit")
        if not (marker / "calibration").exists():
            fail("analyst failure should still run calibration after audit")
        status = json.loads((state / "scout_cycle_status.json").read_text(encoding="utf-8"))
        if status.get("phase") != "analyst" or status.get("result") != "failed":
            fail("analyst failure must write failed cycle status")


def assert_gitignored_runtime() -> None:
    tracked = set(x for x in run("git ls-files state data/scout").stdout.splitlines() if x.strip())
    unexpected = sorted(tracked - SCOUT_MEMORY_ALLOWLIST)
    missing_memory = sorted(SCOUT_MEMORY_ALLOWLIST - tracked)
    if unexpected:
        fail(f"runtime state/data scout files must not be tracked outside memory allowlist: {unexpected}")
    if missing_memory:
        fail(f"Scout learning-memory files must be tracked: {missing_memory}")


def main() -> int:
    assert_policy()
    assert_runner_static()
    assert_dry_run()
    assert_no_delta_blocks_ai_lock_allows_review_calibration_embed()
    assert_analyst_fail_blocks_progress()
    assert_gitignored_runtime()
    for required in (HTML_CHECK, SCOUT_CHECK):
        if not required.is_file():
            fail(f"missing related checker: {required.relative_to(ROOT)}")
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        print(f"W1 scout autopilot check FAIL ({len(errors)})")
        return 1
    print("W1 scout autopilot check PASS (dry-run/no-delta/analyst-fail gates, Scout memory allowlist, raw runtime gitignore, policy)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
