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
    "Policy Engine 判定未形成可主推条件。",
    "Policy Engine 判定未形成可推荐条件。",
    "Policy Engine 未提供具体 pass_reason 或 failed_gates；请复核 policy_result。",
    "本场不进入推荐池；dashboard 不用泛化比赛剧本替代 Policy 根因。",
)
SUPPORT_SETTLEMENTS = {"full_win", "half_win", "push"}
RISK_SETTLEMENTS = {"half_loss", "full_loss"}


def fail(message: str) -> None:
    print(f"W1 decision card check FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def settlement_scores(card: dict) -> tuple[set[str], set[str]]:
    settlement = card.get("score_path_settlement") if isinstance(card.get("score_path_settlement"), dict) else {}
    support = {str((row or {}).get("score")) for row in settlement.get("support_paths") or [] if isinstance(row, dict)}
    risk = {str((row or {}).get("score")) for row in settlement.get("risk_paths") or [] if isinstance(row, dict)}
    for row in settlement.get("support_paths") or []:
        if (row or {}).get("settlement") not in SUPPORT_SETTLEMENTS:
            fail(f"support score has invalid settlement: {row}")
    for row in settlement.get("risk_paths") or []:
        if (row or {}).get("settlement") not in RISK_SETTLEMENTS:
            fail(f"risk score has invalid settlement: {row}")
    return support, risk


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
    fixture_1489393_display: dict | None = None
    for call in calls:
        if not isinstance(call, dict):
            continue
        display = SCOUT_EMBED.display_call(call)
        if str(display.get("fixture_id") or "") == "1489393":
            fixture_1489393_display = display
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
        if card.get("decision_state") == "RECOMMEND":
            support, risk = settlement_scores(card)
            if not support:
                fail(f"fixture {display.get('fixture_id')} RECOMMEND missing support settlement paths")
            if str(display.get("fixture_id") or "") == "1489392":
                if "2-0" in support:
                    fail("fixture 1489392 Curacao +1.5 must not use 2-0 as support")
                if "2-0" not in risk:
                    fail("fixture 1489392 Curacao +1.5 must classify 2-0 as risk")
                if "0-0" not in support:
                    fail("fixture 1489392 Curacao +1.5 must classify 0-0 as support")
            if str(display.get("fixture_id") or "") == "1489393":
                if "2-0" not in risk:
                    fail("fixture 1489393 Ivory Coast +1.5 must classify 2-0 as risk")
                if not ({"1-1", "2-1", "1-0"} & support):
                    fail("fixture 1489393 Ivory Coast +1.5 must keep close-score support paths")
            if str(display.get("fixture_id") or "") == "1539006":
                if "1-0" in support:
                    fail("fixture 1539006 Paraguay +0.5 must not use 1-0 as support")
                if not ({"0-0", "1-1"} & support):
                    fail("fixture 1539006 Paraguay +0.5 must classify draw paths as support")
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
    if fixture_1489393_display:
        policy = fixture_1489393_display.get("policy_result") if isinstance(fixture_1489393_display.get("policy_result"), dict) else {}
        card = fixture_1489393_display.get("decision_card") if isinstance(fixture_1489393_display.get("decision_card"), dict) else {}
        gates = policy.get("hard_gates") if isinstance(policy.get("hard_gates"), dict) else {}
        market_status = policy.get("market_data_status") if isinstance(policy.get("market_data_status"), dict) else {}
        history_status = policy.get("movement_history_status") if isinstance(policy.get("movement_history_status"), dict) else {}
        if policy.get("decision_state") != "RECOMMEND" or policy.get("recommendation_grade") != "B+":
            fail("fixture 1489393 display_call must resolve current state to RECOMMEND/B+, not old PASS")
        if card.get("card_type") != "RECOMMEND_CARD":
            fail("fixture 1489393 display_call must render RECOMMEND_CARD")
        for gate in ("has_ah", "has_market_fair_prob", "has_score_matrix"):
            if gates.get(gate) is not True:
                fail(f"fixture 1489393 display_call missing {gate}=true")
        if market_status.get("has_current_ah") is not True:
            fail("fixture 1489393 must distinguish current AH as available")
        if history_status.get("movement_history_status") == "insufficient":
            text = json.dumps(card, ensure_ascii=False)
            if "历史盘口时间序列不足" not in text:
                fail("fixture 1489393 insufficient movement history must use explicit history wording")
            if "盘口快照不足" in text or "盘口数据不足" in text or "盘口缺失" in text:
                fail("fixture 1489393 current AH available must not use ambiguous/missing market wording")
    if checked == 0:
        print("SKIP: missing runtime input with policy_result calls")
        return 0
    print(f"W1 decision card check PASS (checked={checked})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
