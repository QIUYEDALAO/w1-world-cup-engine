#!/usr/bin/env python3
"""Validate W1_MATCH_STAGE_GATE_FIX_V1."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
SCORE_ENGINE = ROOT / "scripts/w1_score_engine.py"
BUILD_SCRIPT = ROOT / "scripts/build_w1_dashboard_data.py"
RHO_PROVENANCE = ROOT / "config/w1_rho_provenance.json"
DECISION_POLICY = ROOT / "config/w1_decision_policy.json"


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def stage_for_delta(delta_hours: float) -> str:
    if delta_hours > 24:
        return "早盘参考"
    if delta_hours > 6:
        return "赛前观察"
    if delta_hours > 1:
        return "正式判断准备"
    if delta_hours > 0.5:
        return "最终版"
    if delta_hours >= 0:
        return "锁盘/赛前确认"
    return "赛中/已开赛"


def assert_sample_gate() -> None:
    cst = timezone(timedelta(hours=8))
    kickoff = datetime(2026, 6, 15, 1, 0, tzinfo=cst)
    now = datetime(2026, 6, 14, 23, 15, tzinfo=cst)
    delta = (kickoff - now).total_seconds() / 3600
    if not 1.7 < delta < 1.8:
        fail(f"sample delta should be about 1.75h, got {delta}")
    stage = stage_for_delta(delta)
    if stage == "早盘参考":
        fail("1.75h before kickoff must not be early reference")
    if stage != "正式判断准备":
        fail(f"1.75h before kickoff must be 正式判断准备, got {stage}")


def assert_html_gate() -> None:
    text = read(HTML)
    for token in (
        "function stageGate",
        "delta_hours",
        "if(delta>24)",
        "if(delta>6)",
        "if(delta>1)",
        "if(delta>0.5)",
        "if(delta>=0)",
        "正式判断准备",
        "锁盘/赛前确认",
        "赛中/已开赛",
        "stageActionText",
        "当前处于",
        "若首发、盘口、天气等关键数据未齐，仍不进入最终结论",
        "kickoff_utc",
    ):
        if token not in text:
            fail(f"dashboard missing stage gate token: {token}")
    if "12点后正式判断" in text or "12:00 后正式判断" in text:
        fail("dashboard must not use fixed 12:00 formal decision copy")
    js_without_embedded = re.sub(
        r'<script id="w1-data" type="application/json">.*?</script>',
        "",
        text,
        flags=re.S,
    )
    if re.search(r"12[:：]00.*(正式判断|切换|当前)", js_without_embedded):
        fail("dashboard JS must not contain fixed 12:00 stage switching logic")
    if "const cur=r.prediction_stage_cn" in js_without_embedded:
        fail("current stage must not come directly from static prediction_stage_cn")
    if "const gate=stageGate(r),cur=gate.label_cn" not in js_without_embedded:
        fail("current stage marker must come from stageGate")


def assert_core_unchanged() -> None:
    if "DEFAULT_RHO = -0.057766" not in read(SCORE_ENGINE):
        fail("DEFAULT_RHO changed")
    provenance = json.loads(read(RHO_PROVENANCE))
    if provenance.get("default_rho") != -0.057766 or provenance.get("calibrated") is not True:
        fail("rho provenance changed unexpectedly")
    if "W1_PLAY_GUARD_V1" not in read(DECISION_POLICY):
        fail("PLAY_GUARD missing")
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--",
            str(SCORE_ENGINE.relative_to(ROOT)),
            str(RHO_PROVENANCE.relative_to(ROOT)),
            str(DECISION_POLICY.relative_to(ROOT)),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        fail(result.stderr.strip() or "git diff failed")
    changed = [line for line in result.stdout.splitlines() if line.strip()]
    if changed:
        fail(f"model/core files changed unexpectedly: {changed}")


def main() -> int:
    try:
        assert_sample_gate()
        assert_html_gate()
        assert_core_unchanged()
    except (CheckError, Exception) as exc:  # noqa: BLE001
        print(f"W1 match stage gate check FAIL: {exc}", file=sys.stderr)
        return 1
    print("W1 match stage gate check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
