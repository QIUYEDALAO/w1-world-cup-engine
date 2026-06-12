#!/usr/bin/env python3
"""Validate W1_EARLY_PREDICTION_MODE_V1 artifacts."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config/w1_decision_policy.json"
LEDGER_SCHEMA = ROOT / "config/w1_ledger_schema.json"
DATA_JSON = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
BUILD_SCRIPT = ROOT / "scripts/build_w1_dashboard_data.py"

VERSION = "W1_EARLY_PREDICTION_MODE_V1"
STAGES = ["EARLY_REFERENCE", "PREMATCH_WATCH", "FORMAL_DECISION", "FINAL_CHECK"]
STAGE_LABELS = ["早盘参考", "赛前观察", "正式判断", "最终版"]
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


def load(path: Path) -> dict[str, Any]:
    return json.loads(read(path))


def assert_no_forbidden(path: Path) -> None:
    text = read(path)
    for term in FORBIDDEN:
        if term.isascii():
            if re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", text, re.I):
                fail(f"Forbidden term found in {path.relative_to(ROOT)}: {term}")
        elif term in text:
            fail(f"Forbidden term found in {path.relative_to(ROOT)}: {term}")


def assert_policy() -> None:
    policy = load(POLICY)
    mode = policy.get("prediction_stage", {})
    if mode.get("version") != VERSION:
        fail("Policy prediction_stage version mismatch")
    if mode.get("allowed_stages") != STAGES:
        fail("Policy allowed_stages mismatch")

    stages = mode.get("stages", {})
    early = stages.get("EARLY_REFERENCE", {})
    watch = stages.get("PREMATCH_WATCH", {})
    formal = stages.get("FORMAL_DECISION", {})
    final = stages.get("FINAL_CHECK", {})
    if early.get("ledger_required") is not False or early.get("w1_play_allowed") is not False:
        fail("EARLY_REFERENCE must not require ledger or allow W1_PLAY")
    if watch.get("w1_play_allowed") is not False:
        fail("PREMATCH_WATCH must not allow W1_PLAY")
    if formal.get("requires_confirmed_lineup") is not True or formal.get("requires_play_guard") is not True:
        fail("FORMAL_DECISION must require confirmed_lineup and PLAY_GUARD")
    if final.get("requires_confirmed_lineup") is not True or final.get("requires_play_guard") is not True:
        fail("FINAL_CHECK must require confirmed_lineup and PLAY_GUARD")


def assert_ledger_schema() -> None:
    schema = load(LEDGER_SCHEMA)
    required = schema.get("required", [])
    for field in (
        "prediction_stage",
        "prediction_version",
        "reference_score",
        "final_decision_time",
        "early_prediction_hit",
        "final_prediction_hit",
    ):
        if field not in required:
            fail(f"Ledger schema must require {field}")
        if field not in schema.get("properties", {}):
            fail(f"Ledger schema must define {field}")
    if schema["properties"]["prediction_stage"].get("enum") != STAGES:
        fail("Ledger schema prediction_stage enum mismatch")
    if schema["properties"]["prediction_version"].get("const") != VERSION:
        fail("Ledger schema prediction_version mismatch")


def assert_dashboard_data() -> None:
    data = load(DATA_JSON)
    if data.get("early_prediction_mode", {}).get("version") != VERSION:
        fail("dashboard_data early_prediction_mode version mismatch")
    if data.get("early_prediction_mode", {}).get("enabled") is not True:
        fail("early_prediction_mode must be enabled")

    labels = [item.get("label_cn") for item in data.get("prediction_stage_flow_cn", [])]
    for label in STAGE_LABELS:
        if label not in labels:
            fail(f"Missing stage label in dashboard data: {label}")

    records = data.get("match_records", [])
    if len(records) < 24:
        fail("dashboard_data must contain at least 24 match records")
    for row in records:
        for field in (
            "prediction_stage",
            "prediction_version",
            "reference_direction",
            "reference_score",
            "risk_level_cn",
            "current_action_cn",
            "next_update_reason_cn",
            "is_final_decision",
        ):
            if field not in row:
                fail(f"{row.get('fixture_id')}: missing {field}")
        if row["prediction_version"] != VERSION:
            fail(f"{row.get('fixture_id')}: prediction_version mismatch")
        if row["prediction_stage"] == "EARLY_REFERENCE":
            if row.get("ledger_required") is True:
                fail(f"{row.get('fixture_id')}: EARLY_REFERENCE must not require ledger")
            if row.get("decision") == "W1_PLAY":
                fail(f"{row.get('fixture_id')}: EARLY_REFERENCE must not output W1_PLAY")
            if row.get("is_final_decision") is not False:
                fail(f"{row.get('fixture_id')}: EARLY_REFERENCE cannot be final")
        if row.get("decision") == "W1_PLAY" and row["prediction_stage"] not in ("FORMAL_DECISION", "FINAL_CHECK"):
            fail(f"{row.get('fixture_id')}: W1_PLAY only allowed in FORMAL_DECISION/FINAL_CHECK")
        if row.get("reference_score") and row.get("is_final_decision") is False:
            if "不是最终结论" not in row.get("non_final_disclaimer_cn", ""):
                fail(f"{row.get('fixture_id')}: reference_score must be marked non-final")


def assert_html() -> None:
    text = read(HTML)
    for label in STAGE_LABELS:
        if label not in text:
            fail(f"HTML missing stage label: {label}")
    for token in ("参考比分", "非最终结论", "不绕过 W1_PLAY_GUARD_V1"):
        if token not in text:
            fail(f"HTML missing token: {token}")


def main() -> int:
    try:
        for path in (POLICY, LEDGER_SCHEMA, DATA_JSON, HTML, BUILD_SCRIPT):
            if not path.is_file():
                fail(f"Missing file: {path.relative_to(ROOT)}")
            assert_no_forbidden(path)
        assert_policy()
        assert_ledger_schema()
        assert_dashboard_data()
        assert_html()
    except (CheckError, json.JSONDecodeError) as exc:
        print(f"W1 early prediction mode check FAIL: {exc}", file=sys.stderr)
        return 1

    print("W1 early prediction mode check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
