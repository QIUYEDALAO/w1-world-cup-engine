#!/usr/bin/env python3
"""Validate W1_ODDS_MOVEMENT_MONITOR_V1 integration."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_JSON = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
BUILD = ROOT / "scripts/build_w1_dashboard_data.py"
SCORE_ENGINE = ROOT / "scripts/w1_score_engine.py"

FORBIDDEN = (
    "投注建议",
    "下注",
    "资金建议",
    "稳赚",
    "必胜",
    "保证命中",
    "建议下注",
    "推荐投注",
)


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def assert_no_forbidden(path: Path) -> None:
    text = read(path)
    for term in FORBIDDEN:
        if term in text:
            fail(f"Forbidden wording found in {path.relative_to(ROOT)}: {term}")
    for term in ("stake", "profit", "guaranteed"):
        if re.search(rf"(?<![A-Za-z]){term}(?![A-Za-z])", text, re.I):
            fail(f"Forbidden English wording found in {path.relative_to(ROOT)}: {term}")


def assert_core_unchanged() -> None:
    score_text = read(SCORE_ENGINE)
    if "DEFAULT_RHO = -0.057766" not in score_text:
        fail("DEFAULT_RHO changed")
    build_text = read(BUILD)
    if "solve_lambdas" in build_text and "odds_movement_monitor" in build_text:
        fail("odds movement monitor must not call lambda solver or alter score matrix core")
    for token in ("devig_proportional", "devig_two_way", "x2_tv_distance", "fair_total_from_ou"):
        if token not in build_text:
            fail(f"build script missing odds movement core token: {token}")
    if "RECOMPUTE 仅表示用最新共识盘口重新反解 λ" not in build_text:
        fail("RECOMPUTE semantics must be explicit")


def assert_record(row: dict) -> None:
    movement = row.get("odds_movement", {})
    if movement.get("schema_version") != "W1_ODDS_MOVEMENT_MONITOR_V1":
        fail(f"{row.get('fixture_id')}: schema_version mismatch")
    for key in (
        "status",
        "status_reason_code",
        "liquidity",
        "snapshots",
        "cumulative_move",
        "recent_move",
        "coherence",
        "digestion",
        "play_guard_input",
        "display",
        "single_book_outliers",
        "disclaimer_cn",
    ):
        if key not in movement:
            fail(f"{row.get('fixture_id')}: odds_movement missing {key}")
    status = movement["status"]
    if status not in {"MARKET_STABLE", "MARKET_MOVING", "MARKET_ALERT", "MARKET_CONFLICT", "THIN_MARKET_SKIP"}:
        fail(f"{row.get('fixture_id')}: invalid movement status {status}")
    liquidity = movement["liquidity"]
    for key in ("book_count_latest", "min_book_count_seen", "cross_book_spread_home_prob", "staleness_minutes", "markets_present"):
        if key not in liquidity:
            fail(f"{row.get('fixture_id')}: liquidity missing {key}")
    cumulative = movement["cumulative_move"]
    if "x2_tv_distance" not in cumulative:
        fail(f"{row.get('fixture_id')}: missing TV distance")
    if "mu_delta" not in cumulative:
        fail(f"{row.get('fixture_id')}: missing mu drift")
    if cumulative.get("x2_tv_distance") is not None and not (0 <= float(cumulative["x2_tv_distance"]) <= 1):
        fail(f"{row.get('fixture_id')}: TV distance outside [0,1]")
    for snapshot in movement.get("snapshots", []):
        x2 = snapshot.get("x2", {})
        probs = [x2.get("home_prob"), x2.get("draw_prob"), x2.get("away_prob")]
        if all(v is not None for v in probs) and abs(sum(float(v) for v in probs) - 1.0) > 0.001:
            fail(f"{row.get('fixture_id')}: 1X2 probabilities must be devigged before comparison")
    play_guard = movement["play_guard_input"]
    if status == "THIN_MARKET_SKIP" and play_guard.get("recommended_gate") != "SKIP":
        fail(f"{row.get('fixture_id')}: THIN_MARKET_SKIP must trigger SKIP")
    if status == "MARKET_MOVING" and movement.get("calibration", {}).get("gate_effect") != "WARN_ONLY":
        fail(f"{row.get('fixture_id')}: MARKET_MOVING must remain WARN_ONLY")
    if movement.get("calibration", {}).get("tier") != "A" and status in {"MARKET_ALERT", "MARKET_CONFLICT"}:
        if movement.get("calibration", {}).get("gate_effect") != "WARN_ONLY":
            fail(f"{row.get('fixture_id')}: Tier B/C alert/conflict must be WARN_ONLY")
    if not movement.get("display", {}).get("normal_sentence_cn"):
        fail(f"{row.get('fixture_id')}: normal display sentence missing")
    for outlier in movement.get("single_book_outliers", []):
        if "忽略" not in outlier.get("note_cn", ""):
            fail(f"{row.get('fixture_id')}: single book outlier must be marked ignored")


def assert_html() -> None:
    text = read(HTML)
    for token in (
        "市场状态",
        "盘口异动监控",
        "TV",
        "μ drift",
        "book_count",
        "spread",
        "stale",
        "single_book_outliers",
        "单家异常价",
        "风控门槛",
    ):
        if token not in text:
            fail(f"HTML missing odds movement token: {token}")
    if "手动调整 λ" not in text:
        fail("HTML must say odds movement does not manually adjust lambda")


def main() -> int:
    try:
        for path in (DATA_JSON, HTML, BUILD):
            if not path.is_file():
                fail(f"Missing artifact: {path.relative_to(ROOT)}")
            assert_no_forbidden(path)
        assert_core_unchanged()
        data = json.loads(read(DATA_JSON))
        monitor = data.get("odds_movement_monitor", {})
        if monitor.get("schema_version") != "W1_ODDS_MOVEMENT_MONITOR_V1":
            fail("dashboard root odds_movement_monitor metadata missing")
        if monitor.get("calibrated") != "none" or monitor.get("tier") != "C":
            fail("V1 monitor must use uncalibrated Tier C thresholds")
        records = data.get("match_records", [])
        if len(records) < 24:
            fail("Expected at least 24 match_records")
        for row in records:
            assert_record(row)
        assert_html()
    except (CheckError, json.JSONDecodeError) as exc:
        print(f"W1 odds movement monitor check FAIL: {exc}", file=sys.stderr)
        return 1
    print("W1 odds movement monitor check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
