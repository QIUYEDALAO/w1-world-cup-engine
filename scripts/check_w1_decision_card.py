#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Checker for W1 Scout decision_card protocol."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "config/w1_decision_card_schema.json"
MODULE = ROOT / "scripts/w1_decision_card.py"
CALLS = ROOT / "state/w1_scout_calls.json"

sys.path.insert(0, str(ROOT / "scripts"))
import w1_decision_card as W1CARD  # noqa: E402
import w1_scout_embed as SCOUT_EMBED  # noqa: E402

GENERIC_PASS_TEXT = (
    "hard gate / edge / 数据就绪度 / movement / calibration 任一条件不足",
    "Policy Engine 判定未形成可推荐条件。",
)


def fail(message: str) -> None:
    print(f"W1 decision card check FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    if not SCHEMA.is_file():
        fail("missing config/w1_decision_card_schema.json")
    if not MODULE.is_file():
        fail("missing scripts/w1_decision_card.py")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    for key in ("schema_version", "required", "decision_states", "card_types", "reason_labels", "redlines"):
        if key not in schema:
            fail(f"schema missing {key}")
    for label in ("盘口结构", "模型优势", "路径一致性"):
        if label not in schema.get("reason_labels", []):
            fail(f"schema missing reason label {label}")
    proc = subprocess.run([sys.executable, str(MODULE), "--self-test"], cwd=str(ROOT), text=True, capture_output=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        fail("w1_decision_card.py --self-test failed")

    if not CALLS.is_file():
        print("SKIP: missing runtime input state/w1_scout_calls.json")
        return 0
    calls = json.loads(CALLS.read_text(encoding="utf-8")).get("calls", [])
    checked = 0
    for call in calls:
        if not isinstance(call, dict):
            continue
        display = SCOUT_EMBED.display_call(call)
        if not isinstance(display.get("policy_result"), dict):
            continue
        card = display.get("decision_card") if isinstance(display.get("decision_card"), dict) else W1CARD.build_decision_card(display)
        policy = display.get("policy_result")
        errors = W1CARD.validation_errors(card, policy)
        if errors:
            fail(f"fixture {display.get('fixture_id')} decision_card invalid: {errors}")
        if card["decision_state"] == "RECOMMEND" and not card.get("main_pick_cn"):
            fail(f"fixture {display.get('fixture_id')} RECOMMEND missing main pick")
        if card["decision_state"] in {"OBSERVE", "PASS"} and card.get("main_pick_cn"):
            fail(f"fixture {display.get('fixture_id')} non-RECOMMEND exposes main pick")
        if policy.get("decision_state") == "RECOMMEND" and card.get("decision_state") == "PASS":
            fail(f"fixture {display.get('fixture_id')} policy RECOMMEND rendered as PASS")
        failed = policy.get("failed_gates") if isinstance(policy.get("failed_gates"), list) else []
        if policy.get("decision_state") == "PASS":
            if not failed and not policy.get("pass_reason"):
                fail(f"fixture {display.get('fixture_id')} PASS needs failed_gates or pass_reason")
            text = json.dumps(card, ensure_ascii=False)
            if any(item in text for item in GENERIC_PASS_TEXT):
                fail(f"fixture {display.get('fixture_id')} PASS card uses generic pass reason")
            gates = policy.get("hard_gates") if isinstance(policy.get("hard_gates"), dict) else {}
            if gates.get("has_ah") is True and "missing_ah" in text:
                fail(f"fixture {display.get('fixture_id')} PASS card says AH missing despite has_ah=true")
        if failed and policy.get("decision_state") != "PASS":
            fail(f"fixture {display.get('fixture_id')} failed_gates must map to PASS")
        checked += 1
    if checked == 0:
        print("SKIP: missing runtime input with policy_result calls")
        return 0
    print(f"W1 decision card check PASS (checked={checked})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
