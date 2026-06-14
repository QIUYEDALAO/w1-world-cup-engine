#!/usr/bin/env python3
"""Validate W1_RECOMMENDATION_OUTPUT_POLICY_V1 display constraints."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/W1_RECOMMENDATION_OUTPUT_POLICY.md"
DATA_JSON = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
BUILD_SCRIPT = ROOT / "scripts/build_w1_dashboard_data.py"
SCORE_ENGINE = ROOT / "scripts/w1_score_engine.py"
RHO_PROVENANCE = ROOT / "config/w1_rho_provenance.json"
DECISION_POLICY = ROOT / "config/w1_decision_policy.json"

FORBIDDEN = ["建议下注", "推荐投注", "稳赚", "必胜", "保证命中", "bet", "stake", "profit", "guaranteed"]


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def assert_no_forbidden(path: Path) -> None:
    text = read(path)
    for term in FORBIDDEN:
        if term.isascii():
            if re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", text, re.I):
                fail(f"{path.relative_to(ROOT)} contains forbidden term: {term}")
        elif term in text:
            fail(f"{path.relative_to(ROOT)} contains forbidden term: {term}")


def assert_doc() -> None:
    if not DOC.is_file():
        fail("docs/W1_RECOMMENDATION_OUTPUT_POLICY.md is missing")
    text = read(DOC)
    for token in (
        "primary_score 必须唯一",
        "secondary_score 最多 1 个",
        "risk_paths",
        "tail_paths",
        "open_game_paths",
        "不得称为推荐",
        "完整 `score_pool`",
        "非投注/下注/资金建议",
        "不承诺命中率",
    ):
        if token not in text:
            fail(f"policy doc missing token: {token}")


def assert_builder_contract() -> None:
    text = read(BUILD_SCRIPT)
    for token in (
        "recommendation_view_from_score_distribution",
        "primary_basis",
        "most_likely_result_conditional_mode",
        "second_result_conditional_mode",
        "display_score_limit",
        "recommendation_view",
    ):
        if token not in text:
            fail(f"build_w1_dashboard_data.py missing token: {token}")
    if re.search(r"fixture_id\s*==|fid\s*==|==\s*['\"]1489", text):
        fail("recommendation view must not use fixture_id branching")


def assert_data() -> None:
    if not DATA_JSON.is_file():
        fail("dashboard_data.json missing")
    data = json.loads(read(DATA_JSON))
    records = data.get("match_records", [])
    if len(records) < 24:
        fail("dashboard_data.json must contain at least 24 match_records")
    for row in records:
        fid = row.get("fixture_id")
        view = row.get("recommendation_view")
        if not isinstance(view, dict):
            fail(f"{fid}: recommendation_view missing")
        primary = view.get("primary_score")
        secondary = view.get("secondary_score")
        if isinstance(primary, list):
            fail(f"{fid}: primary_score must be unique, not a list")
        if isinstance(secondary, list):
            fail(f"{fid}: secondary_score must be a single value or null")
        if primary and secondary and primary == secondary:
            fail(f"{fid}: secondary_score must not duplicate primary_score")
        if view.get("display_score_limit") != 2:
            fail(f"{fid}: display_score_limit must be 2")
        if view.get("primary_basis") != "most_likely_result_conditional_mode":
            fail(f"{fid}: primary_basis mismatch")
        if secondary and view.get("secondary_basis") != "second_result_conditional_mode":
            fail(f"{fid}: secondary_basis mismatch")
        if not view.get("risk_path_summary"):
            fail(f"{fid}: risk_path_summary missing")
        dist = row.get("score_distribution", {})
        if not dist.get("score_pool"):
            fail(f"{fid}: score_pool must remain available for expert layer")
        for item in dist.get("score_pool", []):
            if not isinstance(item.get("weight"), (int, float)):
                fail(f"{fid}: score_pool weight must remain numeric probability")


def assert_html() -> None:
    text = read(HTML)
    for token in ("recommendation_view", "主比分", "备选比分", "风险路径摘要", "专家展开区", "完整比分矩阵"):
        if token not in text:
            fail(f"dashboard HTML missing token: {token}")
    bad_patterns = [
        r"比分概率池[^<]{0,80}推荐",
        r"top_scores[^<]{0,80}推荐",
        r"风险路径[^<]{0,80}推荐",
    ]
    for pattern in bad_patterns:
        if re.search(pattern, text):
            fail(f"dashboard HTML labels expert/risk scores as recommendation: {pattern}")


def assert_core_unchanged() -> None:
    engine_text = read(SCORE_ENGINE)
    if "DEFAULT_RHO = -0.057766" not in engine_text:
        fail("DEFAULT_RHO must remain -0.057766")
    provenance = json.loads(read(RHO_PROVENANCE))
    if provenance.get("calibrated") is not True or float(provenance.get("default_rho")) != -0.057766:
        fail("rho provenance must remain calibrated=true and default_rho=-0.057766")
    if "W1_PLAY_GUARD_V1" not in read(DECISION_POLICY):
        fail("PLAY_GUARD policy missing")
    result = subprocess.run(
        ["git", "diff", "--name-only", "--", str(SCORE_ENGINE.relative_to(ROOT)), str(RHO_PROVENANCE.relative_to(ROOT)), str(DECISION_POLICY.relative_to(ROOT))],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        fail(result.stderr.strip() or "git diff failed")
    changed = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if changed:
        fail(f"core files changed unexpectedly: {changed}")


def main() -> int:
    try:
        assert_doc()
        assert_builder_contract()
        assert_data()
        assert_html()
        assert_core_unchanged()
        for path in (DOC, HTML, DATA_JSON, BUILD_SCRIPT):
            assert_no_forbidden(path)
    except (CheckError, Exception) as exc:  # noqa: BLE001
        print(f"W1 recommendation output policy check FAIL: {exc}", file=sys.stderr)
        return 1
    print("W1 recommendation output policy check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
