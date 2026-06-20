#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Checker for W1 Scout staged pre-match scheduler."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config/w1_scout_schedule_policy.json"
SCHED = ROOT / "scripts/w1_scout_scheduler.py"
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
SERVER = ROOT / "scripts/w1_local_predict_server.py"
RUN_LOCAL = ROOT / "scripts/run_w1_local_with_scheduler.sh"
RUNBOOK = ROOT / "reports/W1_SCOUT_SCHEDULER_RUNBOOK.md"
errors: list[str] = []

REQ = ["early_48h", "early_24h", "watch_12h", "watch_6h", "watch_2h", "official_1h", "final_30m"]


def fail(msg: str) -> None:
    errors.append(msg)


def run(cmd: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, env={**os.environ, **(env or {})}, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def assert_policy() -> None:
    if not POLICY.is_file():
        fail("missing config/w1_scout_schedule_policy.json")
        return
    p = json.loads(POLICY.read_text(encoding="utf-8"))
    stages = p.get("stages") or []
    ids = [s.get("stage_id") for s in stages]
    if ids != REQ:
        fail(f"stage_id order mismatch: {ids}")
    for s in stages:
        for key in ("stage_id", "label_cn", "offset_minutes", "window_grace_minutes", "lock_mode"):
            if key not in s:
                fail(f"stage missing {key}: {s}")
        if s.get("lock_mode") not in {"updateable", "lock"}:
            fail(f"invalid lock_mode: {s}")
    if (p.get("display_priority") or [])[0] != "final_30m":
        fail("display priority must prefer final_30m")


def assert_scheduler_static() -> None:
    if not SCHED.is_file():
        fail("missing scripts/w1_scout_scheduler.py")
        return
    text = SCHED.read_text(encoding="utf-8")
    for token in (
        "--once", "--daemon", "--interval", "--dry-run", "--now-override", "--fixture-id", "--stage", "--max-fixtures",
        "config/w1_scout_schedule_policy.json", "due_queue", "kickoff", "window_grace_minutes", "trigger <= now < due_end", "now >= kickoff",
        "W1_SCOUT_FORCE_FIXTURE", "W1_SCOUT_FORCE_HASH", "W1_SCOUT_FORCE_REFRESH", "W1_SCOUT_SCHEDULE_STAGE", "W1_SCOUT_SCHEDULE_STAGE_LABEL", "W1_SCOUT_LOCK_CMD", "stage_id", "stage_label_cn",
        "data_snapshot_digest", "w1_scout_ledger.py", "pending_remaining_count", "pending_remaining_preview", "timeout", "partial", "dashboard 仅展示 scheduler 产物",
        "dashboard_scout_calls_payload", "verify_dashboard_payload_fixture", "dashboard_payload_missing", "/dashboard-data scout_calls",
        'W1_SCOUT_SCHEDULER_MAX_FIXTURES_PER_RUN", "4"', "W1_SCOUT_SCHEDULER_CONTINUE_UNTIL_EMPTY", "W1_SCOUT_SCHEDULER_MAX_BATCHES",
    ):
        if token not in text:
            fail(f"scheduler missing token: {token}")
    if "embedded_count = len(success) if embed.returncode == 0 else 0" in text:
        fail("scheduler must not count embed success from returncode only")
    if "verify_embedded_fixture(fid, sid)" in text:
        fail("scheduler embedded_count must be based on dynamic dashboard payload, not static HTML embed")
    if "w1_score_engine" in text or "DEFAULT_RHO" in text:
        fail("scheduler must not touch score engine/RHO")


def assert_dry_run_no_write_and_due_logic() -> None:
    watched = [ROOT / "state/w1_scout_scheduler_status.json", ROOT / "state/w1_scout_calls.json", ROOT / "state/w1_scout_bundles.json"]
    before = {p: (p.stat().st_mtime_ns if p.exists() else None) for p in watched}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        calls = tmp / "w1_scout_calls.json"
        bundles = tmp / "w1_scout_bundles.json"
        status = tmp / "w1_scout_scheduler_status.json"
        calls.write_text(json.dumps({"stage": "W1_SCOUT", "schema_version": "W1_SCOUT_READ_V1", "calls": []}), encoding="utf-8")
        bundles.write_text(json.dumps({"bundles": []}), encoding="utf-8")
        dry_env = {
            "W1_SCOUT_CALLS_PATH": str(calls),
            "W1_SCOUT_BUNDLES_PATH": str(bundles),
            "W1_SCOUT_SCHEDULER_STATUS_PATH": str(status),
        }
        proc = run([sys.executable, str(SCHED), "--dry-run", "--now-override", "2026-06-20T02:00:00+08:00", "--fixture-id", "1489391"], env=dry_env)
        proc_mid = run([sys.executable, str(SCHED), "--dry-run", "--now-override", "2026-06-20T02:10:00+08:00", "--fixture-id", "1489391"], env=dry_env)
        proc_final = run([sys.executable, str(SCHED), "--dry-run", "--now-override", "2026-06-20T02:30:00+08:00", "--fixture-id", "1489391"], env=dry_env)
        proc2 = run([sys.executable, str(SCHED), "--dry-run", "--now-override", "2026-06-20T01:40:00+08:00", "--stage", "final_30m", "--fixture-id", "1489391"], env=dry_env)
        proc3 = run([sys.executable, str(SCHED), "--dry-run", "--now-override", "2026-06-20T04:00:00+08:00", "--fixture-id", "1489391"], env=dry_env)
        proc4 = run([sys.executable, str(SCHED), "--dry-run", "--now-override", "2026-06-20T02:00:00+08:00", "--max-fixtures", "1"], env=dry_env)
    if proc.returncode != 0:
        fail(f"scheduler dry-run failed: {proc.stderr or proc.stdout}")
    if "official_1h" not in proc.stdout or "early_48h" in proc.stdout or "watch_2h" in proc.stdout:
        fail("T-1h now override should produce only official_1h for the 03:00 CST fixture")
    if "official_1h" not in proc_mid.stdout or any(stage in proc_mid.stdout for stage in ("early_48h", "early_24h", "watch_12h", "watch_6h", "watch_2h")):
        fail("T-50m window must not backfill earlier stages for the same fixture")
    if "final_30m" not in proc_final.stdout or "official_1h" in proc_final.stdout:
        fail("T-30m now override should produce only final_30m for the 03:00 CST fixture")
    if "final_30m" in proc2.stdout:
        fail("T-30m must not be due at T-80m for the 03:00 CST fixture")
    if "DUE" in proc3.stdout:
        fail("scheduler dry-run must not queue already-started fixture")
    if "processed_count=1" not in proc4.stdout or "pending_remaining_count=" not in proc4.stdout:
        fail("--max-fixtures must limit processed fixtures and expose remaining count")
    after = {p: (p.stat().st_mtime_ns if p.exists() else None) for p in watched}
    if before != after:
        fail("scheduler dry-run must not write runtime files")


def assert_dashboard_contract() -> None:
    text = HTML.read_text(encoding="utf-8")
    for token in (
        "W1 Scout Scheduler", "T-48/T-24/T-12/T-6/T-2/T-1/T-30m", "dashboard 仅展示结果",
        "尚未进入赛前生产窗口", "早盘参考待生成", "赛前观察待生成", "正式判断待生成", "最终版待生成",
        "无赛前推荐，不参与命中统计", "阶段：", "scoutStageRank", "final_30m", "offi'+'cial_1h",
        "scoutHasReadableCall", "generated_at", "asian_handicap_card", "recommendation_card",
    ):
        if token not in text:
            fail(f"dashboard missing scheduler/stage token: {token}")
    scout = text[text.find("function pScoutAnalyst("):text.find("function pScoutCycleStatus(")]
    if "等待下一次自动周期" in scout:
        fail("Scout analyst card must not use old waiting-for-next-autopilot wording")


def assert_viewer_runtime_contract() -> None:
    server = SERVER.read_text(encoding="utf-8") if SERVER.is_file() else ""
    if 'os.environ.get("W1_SCOUT_AUTOPILOT", "0")' not in server:
        fail("server autopilot must default disabled")
    if "SCOUT_SCHEDULER_STATUS" not in server or "scheduler_status_for_dashboard" not in server:
        fail("/dashboard-data must read scheduler status, not server autopilot as primary flow")
    for token in ("load_scout_calls_for_dashboard", 'payload["scout_calls"]', "SCOUT_EMBED.display_call", "scout_reviews", "scout_calibration"):
        if token not in server:
            fail(f"/dashboard-data must serve dynamic Scout display payload: {token}")
    for token in (
        "scout_call_dashboard_ready",
        "scout_stage_for_match",
        "W1_SCOUT_FORCE_FIXTURE",
        "W1_SCOUT_SCHEDULE_STAGE",
        "W1_SCOUT_SCHEDULE_STAGE_LABEL",
        "W1_SCOUT_FORCE_REFRESH",
        "W1_SCOUT_DISABLE_MEMORY_COMMIT",
        "runner force fixture=",
        "POST /predict received",
        "可由 /dashboard-data 上屏",
    ):
        if token not in server:
            fail(f"manual Scout fallback must force and verify the selected fixture: {token}")
    html = HTML.read_text(encoding="utf-8") if HTML.is_file() else ""
    for bad in ("server 兜底检查开启", "等待下一次自动周期", "下一次检查"):
        if bad in html:
            fail(f"dashboard must not show old server autopilot primary wording: {bad}")
    if not RUN_LOCAL.is_file():
        fail("missing scripts/run_w1_local_with_scheduler.sh")
    else:
        run_local = RUN_LOCAL.read_text(encoding="utf-8")
        for token in (
            "w1_local_predict_server.py",
            "w1_scout_scheduler.py",
            "--daemon",
            "logs/w1_local_server.log",
            "logs/w1_scout_scheduler.log",
            "trap cleanup",
            "W1_SCOUT_SCHEDULER_MAX_FIXTURES_PER_RUN",
            "W1_SCOUT_SCHEDULER_CONTINUE_UNTIL_EMPTY",
            "W1_SCOUT_SCHEDULER_MAX_BATCHES",
        ):
            if token not in run_local:
                fail(f"local scheduler launcher missing token: {token}")
    if not RUNBOOK.is_file():
        fail("missing scheduler runbook")
    else:
        runbook = RUNBOOK.read_text(encoding="utf-8")
        for token in ("两个进程", "dashboard viewer", "scheduler producer", "run_w1_local_with_scheduler.sh", "dashboard 打开不会自动生产"):
            if token not in runbook:
                fail(f"scheduler runbook missing two-process guidance: {token}")


def main() -> int:
    assert_policy()
    assert_scheduler_static()
    assert_dry_run_no_write_and_due_logic()
    assert_dashboard_contract()
    assert_viewer_runtime_contract()
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"W1 scout scheduler check FAIL ({len(errors)})")
        return 1
    print("W1 scout scheduler check PASS (schedule policy, dry-run, due stages, dashboard stage contract)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
