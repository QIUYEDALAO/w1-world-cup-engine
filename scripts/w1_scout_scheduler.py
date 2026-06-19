#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 Scout pre-match scheduler.

Independent production entrypoint for staged Scout reads.  The dashboard server is
only a viewer/fallback; this scheduler decides which fixture/stage is due and
invokes the existing single-fixture Scout cycle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config/w1_scout_schedule_policy.json"
DASH = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
CALLS = Path(os.environ.get("W1_SCOUT_CALLS_PATH", ROOT / "state/w1_scout_calls.json"))
BUNDLES = Path(os.environ.get("W1_SCOUT_BUNDLES_PATH", ROOT / "state/w1_scout_bundles.json"))
STATUS = Path(os.environ.get("W1_SCOUT_SCHEDULER_STATUS_PATH", ROOT / "state/w1_scout_scheduler_status.json"))
CYCLE = ROOT / "scripts/run_w1_scout_cycle.sh"
EMBED = ROOT / "scripts/w1_scout_embed.py"
LEDGER = ROOT / "scripts/w1_scout_ledger.py"


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_policy() -> dict[str, Any]:
    return load_json(POLICY, {"stages": []})


def stage_rank_map(policy: dict[str, Any]) -> dict[str, int]:
    order = policy.get("display_priority") or []
    return {str(stage): len(order) - idx for idx, stage in enumerate(order)}


def stage_by_id(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(stage.get("stage_id")): stage for stage in policy.get("stages", []) if stage.get("stage_id")}


def load_records() -> list[dict[str, Any]]:
    return load_json(DASH, {}).get("match_records", [])


def load_calls() -> dict[str, Any]:
    return load_json(CALLS, {"stage": "W1_SCOUT", "schema_version": "W1_SCOUT_READ_V1", "generated_by": None, "calls": []})


def generated_stage_keys() -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for call in load_calls().get("calls", []):
        fid = str(call.get("fixture_id") or "")
        stage = str(call.get("stage_id") or "")
        if fid and stage:
            out.add((fid, stage))
    return out


def due_stages_for_record(rec: dict[str, Any], now: datetime, policy: dict[str, Any], forced_stage: str | None = None) -> list[dict[str, Any]]:
    fid = str(rec.get("fixture_id") or "")
    kickoff = parse_dt(rec.get("kickoff_utc") or rec.get("kickoff"))
    if not fid or not kickoff or now >= kickoff:
        return []
    done = generated_stage_keys()
    stages = policy.get("stages", [])
    if forced_stage:
        stages = [s for s in stages if s.get("stage_id") == forced_stage]
    due: list[dict[str, Any]] = []
    for stage in stages:
        sid = str(stage.get("stage_id") or "")
        if not sid or (fid, sid) in done:
            continue
        trigger = kickoff + timedelta(minutes=int(stage.get("offset_minutes") or 0))
        if now >= trigger:
            due.append({"fixture_id": fid, "match": rec.get("match"), "kickoff_utc": iso(kickoff), "trigger_at_utc": iso(trigger), "stage": stage})
    return due


def due_queue(now: datetime, fixture_id: str | None, forced_stage: str | None) -> list[dict[str, Any]]:
    policy = load_policy()
    rows = []
    for rec in load_records():
        if fixture_id and str(rec.get("fixture_id")) != str(fixture_id):
            continue
        rows.extend(due_stages_for_record(rec, now, policy, forced_stage))
    rank = stage_rank_map(policy)
    rows.sort(key=lambda r: (parse_dt(r["trigger_at_utc"]) or now, -rank.get(str(r["stage"].get("stage_id")), 0), str(r["fixture_id"])))
    return rows


def bundle_digest(fixture_id: str) -> str:
    bundles = load_json(BUNDLES, {}).get("bundles", [])
    selected = next((b for b in bundles if str(b.get("fixture_id")) == str(fixture_id)), None)
    blob = json.dumps(selected or {"fixture_id": fixture_id, "missing_bundle": True}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def annotate_stage(fixture_id: str, stage: dict[str, Any], kickoff_utc: str) -> bool:
    calls_doc = load_calls()
    calls = calls_doc.get("calls", []) if isinstance(calls_doc.get("calls"), list) else []
    sid = str(stage.get("stage_id") or "")
    prior_same_stage = [c for c in calls if not (str(c.get("fixture_id")) == str(fixture_id) and str(c.get("stage_id") or "") == sid)]
    candidates = [c for c in calls if str(c.get("fixture_id")) == str(fixture_id) and isinstance(c.get("read"), dict)]
    if not candidates:
        return False
    # Analyst writes/updates the unstaged fixture call; use the last matching call as this stage's snapshot.
    call = dict(candidates[-1])
    call["stage_id"] = sid
    call["stage_label_cn"] = str(stage.get("label_cn") or sid)
    call["stage_lock_mode"] = str(stage.get("lock_mode") or "updateable")
    call["generated_at"] = iso(now_utc())
    call["kickoff_at"] = kickoff_utc
    call["data_snapshot_digest"] = bundle_digest(fixture_id)
    calls_doc["calls"] = prior_same_stage + [call]
    CALLS.parent.mkdir(parents=True, exist_ok=True)
    CALLS.write_text(json.dumps(calls_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def run_stage(item: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    fid = str(item["fixture_id"])
    stage = item["stage"]
    sid = str(stage.get("stage_id"))
    lock_mode = str(stage.get("lock_mode") or "updateable")
    if dry_run:
        return {"fixture_id": fid, "stage_id": sid, "result": "dry_run", "message_cn": "dry-run 不抓取、不调用 AI、不写文件"}
    env = os.environ.copy()
    env.update({
        "W1_SCOUT_FORCE_FIXTURE": fid,
        "W1_SCOUT_FORCE_HASH": f"scheduler-{fid}-{sid}-{int(time.time())}",
        "W1_SCOUT_DISABLE_MEMORY_COMMIT": env.get("W1_SCOUT_DISABLE_MEMORY_COMMIT", "1"),
        "W1_SCOUT_AUTOPILOT_MAX_FIXTURES_PER_RUN": "1",
    })
    if lock_mode != "lock":
        env["W1_SCOUT_LOCK_CMD"] = "true"
    proc = subprocess.run(["bash", str(CYCLE)], cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=int(env.get("W1_SCOUT_SCHEDULER_STAGE_TIMEOUT_SECONDS", "480")))
    if proc.returncode != 0:
        return {"fixture_id": fid, "stage_id": sid, "result": "failed", "message_cn": (proc.stderr or proc.stdout or "stage failed").splitlines()[-1] if (proc.stderr or proc.stdout) else "stage failed"}
    annotated = annotate_stage(fid, stage, item["kickoff_utc"])
    if not annotated:
        return {"fixture_id": fid, "stage_id": sid, "result": "failed", "message_cn": "AI read 生成后未找到可标注 call"}
    subprocess.run([sys.executable, str(EMBED)], cwd=ROOT, env=env, check=False)
    if lock_mode == "lock":
        subprocess.run([sys.executable, str(LEDGER), "lock"], cwd=ROOT, env=env, check=False)
    return {"fixture_id": fid, "stage_id": sid, "result": "ok", "message_cn": f"{stage.get('label_cn')} {sid} 已生成并上屏"}


def parse_now(value: str | None) -> datetime:
    if not value:
        return now_utc()
    dt = parse_dt(value)
    if dt is None:
        raise SystemExit(f"invalid --now-override: {value}")
    return dt


def run_once(args: argparse.Namespace) -> int:
    now = parse_now(args.now_override)
    queue = due_queue(now, args.fixture_id, args.stage)
    if args.dry_run:
        print(f"scheduler dry-run now={iso(now)} due_count={len(queue)}")
        for item in queue:
            st = item["stage"]
            print(f"DUE fixture={item['fixture_id']} match={item.get('match')} stage={st.get('stage_id')} label={st.get('label_cn')} trigger={item['trigger_at_utc']} kickoff={item['kickoff_utc']}")
        return 0
    results = [run_stage(item, False) for item in queue]
    payload = {"schema_version": "W1_SCOUT_SCHEDULER_STATUS_V1", "updated_at_utc": iso(now_utc()), "due_count": len(queue), "results": results, "redlines_cn": "kickoff 后不补写赛前 read；dashboard 仅展示 scheduler 产物。"}
    write_json(STATUS, payload)
    ok = sum(1 for r in results if r.get("result") == "ok")
    failed = len(results) - ok
    print(f"scheduler once: due={len(queue)} ok={ok} failed={failed} status={STATUS.relative_to(ROOT)}")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run staged W1 Scout pre-match scheduler")
    parser.add_argument("--once", action="store_true", help="Run one scheduler scan")
    parser.add_argument("--daemon", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--now-override")
    parser.add_argument("--fixture-id")
    parser.add_argument("--stage")
    args = parser.parse_args()
    if args.daemon:
        while True:
            rc = run_once(args)
            if args.dry_run:
                return rc
            time.sleep(max(5, args.interval))
    return run_once(args)


if __name__ == "__main__":
    raise SystemExit(main())
