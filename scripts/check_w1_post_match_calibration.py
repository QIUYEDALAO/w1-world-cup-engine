#!/usr/bin/env python3
"""Validate W1_POST_MATCH_AUTO_CALIBRATION_V1 outputs."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_JSON = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
BUILD_SCRIPT = ROOT / "scripts/build_w1_dashboard_data.py"

FORBIDDEN = [
    "bet",
    "stake",
    "profit",
    "guaranteed",
    "稳赚",
    "必胜",
]


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def assert_no_forbidden(text: str, label: str) -> None:
    for term in FORBIDDEN:
        if term.isascii():
            if re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", text, re.I):
                fail(f"Forbidden term found in {label}: {term}")
        elif term in text:
            fail(f"Forbidden term found in {label}: {term}")


def assert_builder() -> None:
    text = read(BUILD_SCRIPT)
    for token in (
        "auto_miss_reason_tags",
        "auto_lesson_cn",
        "prediction_hit_type",
        "post_match_auto_calibration_sample",
        "1489373",
        "1489370",
    ):
        if token not in text:
            fail(f"build script missing calibration token: {token}")


def assert_sample(records: list[dict[str, object]], fixture_id: str, score: dict[str, int], lesson_token: str) -> None:
    row = next((item for item in records if str(item.get("fixture_id")) == fixture_id), None)
    if not row:
        fail(f"fixture_id={fixture_id} missing")
    if row.get("status") != "finished":
        fail(f"fixture_id={fixture_id} must be finished")
    if row.get("actual_score") != score:
        fail(f"fixture_id={fixture_id} actual_score mismatch: {row.get('actual_score')}")
    if row.get("result_source") != "post_match_auto_calibration_sample":
        fail(f"fixture_id={fixture_id} result_source mismatch")
    calibration = row.get("post_match_calibration", {})
    if calibration.get("actual_score") != f"{score['home']}-{score['away']}":
        fail(f"fixture_id={fixture_id} calibration actual_score mismatch")
    if calibration.get("prediction_hit_type") != "pool_hit":
        fail(f"fixture_id={fixture_id} prediction_hit_type must be pool_hit")
    if not calibration.get("miss_reason_tags"):
        fail(f"fixture_id={fixture_id} miss_reason_tags must be generated")
    if lesson_token not in calibration.get("lesson_cn", ""):
        fail(f"fixture_id={fixture_id} lesson missing token: {lesson_token}")


def main() -> int:
    try:
        for path in (DATA_JSON, HTML, BUILD_SCRIPT):
            if not path.is_file():
                fail(f"missing file: {path.relative_to(ROOT)}")
            assert_no_forbidden(read(path), path.relative_to(ROOT).as_posix())
        assert_builder()
        data = json.loads(read(DATA_JSON))
        records = data.get("match_records", [])
        if len(records) < 24:
            fail("dashboard_data must contain at least 24 match records")
        assert_sample(records, "1489373", {"home": 1, "away": 1}, "深让不等于大胜")
        assert_sample(records, "1489370", {"home": 4, "away": 1}, "平手盘也可能打开")
        html = read(HTML)
        for token in ("赛后校准", "实际比分", "命中类型", "miss_reason_tags", "深让不等于大胜", "平手盘也可能打开"):
            if token not in html:
                fail(f"HTML missing calibration token: {token}")
    except (CheckError, json.JSONDecodeError) as exc:
        print(f"W1 post-match calibration check FAIL: {exc}", file=sys.stderr)
        return 1

    print("W1 post-match calibration check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
