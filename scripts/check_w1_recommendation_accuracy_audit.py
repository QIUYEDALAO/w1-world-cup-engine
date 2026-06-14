#!/usr/bin/env python3
"""Validate W1 recommendation accuracy audit artifacts."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = ROOT / "scripts/audit_w1_recommendation_accuracy.py"
AUDIT_MD = ROOT / "reports/W1_RECOMMENDATION_ACCURACY_AUDIT.md"
AUDIT_JSON = ROOT / "reports/w1_recommendation_accuracy_audit.json"
PROTECTED_FILES = [
    ROOT / "scripts/w1_score_engine.py",
    ROOT / "scripts/build_w1_dashboard_data.py",
    ROOT / "config/w1_decision_policy.json",
]
FORBIDDEN_PATTERNS = [
    "稳" + "赚",
    "必" + "胜",
    "保证" + "命中",
    "下注" + "建议",
    "投注" + "建议",
    "资金" + "建议",
]


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_no_forbidden(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for term in FORBIDDEN_PATTERNS:
        if re.search(re.escape(term), text):
            fail(f"{path.relative_to(ROOT)} contains forbidden phrase")


def assert_artifacts() -> dict[str, Any]:
    if not AUDIT_SCRIPT.is_file():
        fail("audit script missing")
    if not AUDIT_MD.is_file():
        fail("audit markdown missing")
    if not AUDIT_JSON.is_file():
        fail("audit json missing")
    data = read_json(AUDIT_JSON)
    metrics = data.get("metrics", {})
    matches = data.get("matches", [])
    if metrics.get("total_completed_matches", 0) < 1:
        fail("total_completed_matches must be >= 1")
    if len(matches) != metrics.get("total_completed_matches"):
        fail("matches count must equal total_completed_matches")
    for key in ("direction_accuracy", "score_pool_coverage"):
        if key not in metrics:
            fail(f"metrics missing {key}")
    for match in matches:
        if not match.get("actual_score"):
            fail(f"{match.get('fixture_id')}: actual_score missing")
        if match.get("rps_1x2") is None and not match.get("calibration_missing_reason"):
            fail(f"{match.get('fixture_id')}: RPS missing without missing_reason")
    text = AUDIT_MD.read_text(encoding="utf-8")
    required = [
        "不因单场调权重",
        "Qatar vs Switzerland 1-1",
        "USA vs Paraguay 4-1",
        "Australia vs Turkey 2-0",
        "RPS/log score",
        "score_pool 覆盖不等于推荐成功",
    ]
    for phrase in required:
        if phrase not in text:
            fail(f"audit markdown missing phrase: {phrase}")
    return data


def assert_protected_files_unchanged() -> None:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--", *[str(path.relative_to(ROOT)) for path in PROTECTED_FILES]],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        fail(f"git diff failed: {result.stderr or result.stdout}")
    changed = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if changed:
        fail(f"protected model/policy files changed: {', '.join(changed)}")


def main() -> int:
    try:
        assert_artifacts()
        assert_protected_files_unchanged()
        for path in (AUDIT_SCRIPT, AUDIT_MD, AUDIT_JSON):
            assert_no_forbidden(path)
    except (CheckError, json.JSONDecodeError) as exc:
        print(f"W1 recommendation accuracy audit check FAIL: {exc}", file=sys.stderr)
        return 1
    print("W1 recommendation accuracy audit check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
