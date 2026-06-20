#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Embed W1_SCOUT DeepSeek reads/reviews into the dashboard.

Reads state/w1_scout_calls.json, state/scout_reviews.jsonl, and
state/scout_calibration.json, then replaces dashboard embedded blobs idempotently.
Display-only: does not touch the W1 market base, λ, score matrix, or build pipeline.
"""
from __future__ import annotations

import json
import copy
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
CALLS = ROOT / "state/w1_scout_calls.json"
REVIEWS = ROOT / "state/scout_reviews.jsonl"
CALIBRATION = ROOT / "state/scout_calibration.json"
BUNDLES = ROOT / "state/w1_scout_bundles.json"
TAG_RE = re.compile(r'<script id="w1-scout-calls" type="application/json">.*?</script>', re.S)
REVIEWS_TAG_RE = re.compile(r'<script id="w1-scout-reviews" type="application/json">.*?</script>', re.S)
CALIBRATION_TAG_RE = re.compile(r'<script id="w1-scout-calibration" type="application/json">.*?</script>', re.S)
SCORE_BAND_FALLBACK = "常规比分带暂不展开；偏低比分小胜或平局分支，需结合临场数据。"
MARKET_MISSING_TEXT = "市场赔率数据缺失，暂时无法对比市场倾向。"
MARKET_SCRIPT_MISSING_TEXT = "盘口数据缺失，无法展开让球覆盖或大小球触发判断；本场只保留比赛剧本推演。"
XG_WEAK_TEXT = "xG 样本不足，只作为弱参考。"
VISIBLE_TEXT_KEYS = ("tilt_cn", "score_band_cn", "vs_market_cn", "regular_script_cn", "high_variance_tail_script_cn", "market_expert_script_cn")
VISIBLE_LIST_KEYS = ("watch_points_cn", "risks_cn", "evidence_chain_cn", "reverse_risks_cn")
DISPLAY_CALL_KEYS = {
    "fixture_id",
    "schema_version",
    "style_mode",
    "safety_label",
    "stage_id",
    "stage_label_cn",
    "stage_lock_mode",
    "generated_at",
    "kickoff_at",
    "data_snapshot_digest",
    "policy_result",
    "policy_enforced",
    "decision_card",
    "read",
    "data_readiness",
    "honesty_label",
    "independent_edge",
}
REPLACEMENTS = (
    ("p_home", "市场主胜读数"),
    ("p_draw", "市场平局读数"),
    ("p_away", "市场客胜读数"),
    ("None", "数据缺失"),
    ("null", "数据缺失"),
    ("NaN", "数据缺失"),
    ("undefined", "数据缺失"),
    ("数据claim", "证据"),
    ("claim", "证据"),
    ("fields", "数据项"),
    ("source", "来源"),
    ("availability", "可用度"),
    ("weight", "证据力度"),
    ("xG若干", XG_WEAK_TEXT),
    ("xG 若干", XG_WEAK_TEXT),
    ("若干", "样本不足"),
    ("1-历史样本-0", SCORE_BAND_FALLBACK),
    ("历史样本-0", SCORE_BAND_FALLBACK),
    ("Australia", "澳大利亚"),
    ("Türkiye", "土耳其"),
    ("Turkey", "土耳其"),
    ("South Korea", "韩国"),
    ("Mexico", "墨西哥"),
    ("USA", "美国"),
)
STRONG_REPLACEMENTS = (
    ("零封概率较高", "存在零封分支，但证据不足，需临场确认"),
    ("大胜概率较高", "大胜只作为尾部路径"),
    ("明显打穿", "盘口覆盖不展开"),
    ("穿盘路径明确", "盘口覆盖不展开"),
    ("概率较高", "倾向存在"),
    ("确定", "倾向"),
    ("强烈", "偏向"),
    ("明显", "相对"),
)
POLICY_FALLBACK_PASS_REASONS = (
    "Policy Engine 判定未形成可主推条件。",
    "hard gate / edge / 数据就绪度 / movement / calibration 任一条件不足。",
)

sys.path.insert(0, str(ROOT / "scripts"))
import w1_scout_analyst as W1ANALYST  # noqa: E402
import w1_decision_card as W1CARD  # noqa: E402


def read_reviews() -> list[dict]:
    if not REVIEWS.is_file():
        return []
    return [json.loads(line) for line in REVIEWS.read_text(encoding="utf-8").splitlines() if line.strip()]


def upsert_tag(html: str, tag_id: str, payload: dict, regex: re.Pattern[str]) -> str:
    blob = json.dumps(payload, ensure_ascii=False)
    if "</script>" in blob:
        blob = blob.replace("</script>", "<\\/script>")
    new_tag = f'<script id="{tag_id}" type="application/json">{blob}</script>'
    if regex.search(html):
        return regex.sub(lambda _m: new_tag, html, count=1)
    return html.replace('<script id="w1-data" type="application/json">',
                        new_tag + "\n" + '<script id="w1-data" type="application/json">', 1)


def clean_visible_text(value: object, *, score_band: bool = False, market_script: bool = False) -> str:
    text = str(value or "").strip()
    if re.search(r"(?:p_home|p_draw|p_away).*?(?:None|null|NaN|undefined)", text, flags=re.I):
        text = MARKET_SCRIPT_MISSING_TEXT if market_script else MARKET_MISSING_TEXT
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    text = re.sub(r"\b[WDL]{3,}\b", "近期战绩序列", text)
    text = re.sub(r"\d+-样本不足-\d+", SCORE_BAND_FALLBACK, text)
    if score_band and ("历史样本" in text or "样本不足-0" in text):
        return SCORE_BAND_FALLBACK
    if market_script and MARKET_MISSING_TEXT in text:
        return MARKET_SCRIPT_MISSING_TEXT
    for old, new in STRONG_REPLACEMENTS:
        text = text.replace(old, new)
    return text


def display_call(call: dict) -> dict:
    """Dashboard embeds only display text; structured evidence stays in state."""
    working = copy.deepcopy(call)
    fixture_id = str(working.get("fixture_id") or "")
    bundle = BUNDLE_BY_FIXTURE.get(fixture_id)
    try:
        working = W1ANALYST.harden_call(working, fixture_id, copy.deepcopy(bundle) if bundle else None)
    except Exception:
        if isinstance(working.get("read"), dict):
            W1ANALYST.normalize_recommendation_card(working, bundle)
            W1ANALYST.normalize_asian_handicap_card(working, bundle)
            W1ANALYST.normalize_recommendation_text(working, bundle)
    out = {key: copy.deepcopy(value) for key, value in working.items() if key in DISPLAY_CALL_KEYS}
    if out.get("safety_label"):
        out["safety_label"] = clean_visible_text(out.get("safety_label")).replace("非资金指令", "非操作指令")
    enforce_policy_display_copy(out)
    if isinstance(out.get("policy_result"), dict):
        out["decision_card"] = W1CARD.build_decision_card(out)
    bundle = BUNDLE_BY_FIXTURE.get(str(out.get("fixture_id") or ""))
    read = out.get("read")
    if isinstance(read, dict):
        read.pop("evidence", None)
        for key in VISIBLE_TEXT_KEYS:
            if key in read:
                read[key] = clean_visible_text(
                    read.get(key),
                    score_band=(key == "score_band_cn"),
                    market_script=(key == "market_expert_script_cn"),
                )
        for key in VISIBLE_LIST_KEYS:
            value = read.get(key)
            if isinstance(value, list):
                read[key] = [clean_visible_text(item) for item in value if str(item or "").strip()]
            elif isinstance(value, str):
                read[key] = [clean_visible_text(value)]
        rec_text = read.get("recommendation_text")
        if isinstance(rec_text, dict):
            for key in ("headline_cn", "grade_cn", "core_judgement_cn", "score_recommendation_cn", "ou_aux_cn"):
                if key in rec_text:
                    rec_text[key] = clean_visible_text(rec_text.get(key))
            for key in ("reason_bullets_cn", "live_invalidation_cn"):
                value = rec_text.get(key)
                if isinstance(value, list):
                    rec_text[key] = [clean_visible_text(item) for item in value if str(item or "").strip()]
                elif isinstance(value, str):
                    rec_text[key] = [clean_visible_text(value)]
    return out


def policy_reason_items(policy: dict) -> list[str]:
    if not isinstance(policy, dict):
        return list(POLICY_FALLBACK_PASS_REASONS)
    items: list[str] = []
    for key in ("pass_reason", "observe_reason"):
        value = str(policy.get(key) or "").strip()
        if value:
            items.append(value)
    failed = policy.get("failed_gates") if isinstance(policy.get("failed_gates"), list) else []
    if failed:
        items.append("未通过风控门槛：" + " / ".join(str(x) for x in failed if str(x).strip()))
    severity = str(policy.get("gate_severity") or "").strip()
    if severity and severity != "none":
        items.append(f"gate_severity={severity}，Policy Engine 未放行主方向。")
    for key, label in (("conflict_flags", "冲突标记"), ("movement_flags", "盘口变化标记"), ("grade_caps_applied", "等级封顶")):
        rows = policy.get(key) if isinstance(policy.get(key), list) else []
        if rows:
            items.append(f"{label}：" + " / ".join(str(x) for x in rows if str(x).strip()))
    calibration = policy.get("calibration") if isinstance(policy.get("calibration"), dict) else {}
    if calibration.get("reason"):
        items.append(str(calibration.get("reason")))
    probability = policy.get("probability") if isinstance(policy.get("probability"), dict) else {}
    edge_raw = probability.get("edge_raw")
    edge_calibrated = probability.get("edge_calibrated")
    cal_status = probability.get("calibration_status")
    if edge_raw is not None or edge_calibrated is not None or cal_status:
        items.append(f"edge_raw={edge_raw if edge_raw is not None else 'missing'}，edge_calibrated={edge_calibrated if edge_calibrated is not None else 'missing'}，calibration_status={cal_status or 'missing'}。")
    return items or list(POLICY_FALLBACK_PASS_REASONS)


def enforce_policy_display_copy(out: dict) -> None:
    policy = out.get("policy_result") if isinstance(out.get("policy_result"), dict) else {}
    decision = str(policy.get("decision_state") or "")
    if decision not in {"PASS", "OBSERVE"}:
        return
    read = out.get("read") if isinstance(out.get("read"), dict) else {}
    ah = read.get("asian_handicap_card") if isinstance(read.get("asian_handicap_card"), dict) else {}
    rec_text = read.get("recommendation_text") if isinstance(read.get("recommendation_text"), dict) else {}
    card = read.get("recommendation_card") if isinstance(read.get("recommendation_card"), dict) else {}
    reasons = policy_reason_items(policy)
    candidate = str(policy.get("candidate_ah_pick") or "").strip()

    if decision == "PASS":
        rec_text["headline_cn"] = "AI亚盘结论：PASS / 观察"
        rec_text["grade_cn"] = "PASS｜信心：低"
        rec_text["core_judgement_cn"] = reasons[0]
        rec_text["reason_bullets_cn"] = reasons[:4]
        rec_text["live_invalidation_cn"] = (
            policy.get("reassess_triggers")
            if isinstance(policy.get("reassess_triggers"), list) and policy.get("reassess_triggers")
            else ["若 hard gate、edge、盘口变化与校准状态重新满足条件，再复核。"]
        )
        ah["main_ah_pick_cn"] = "亚盘结论：PASS / 观察"
        ah["final_action_cn"] = "亚盘结论：PASS / 观察。"
        ah["recommendation_grade"] = "PASS"
        ah["pass_reason_cn"] = reasons[0]
        card["ah_pick_cn"] = "无正式方向，仅观察｜来源：Policy Engine"
        card["main_recommendation_cn"] = reasons[0]
    elif decision == "OBSERVE":
        rec_text["headline_cn"] = "AI亚盘结论：观察，不进入强推荐"
        rec_text["grade_cn"] = "B / 观察"
        rec_text["core_judgement_cn"] = str(policy.get("observe_reason") or "Policy Engine 判定仅保留观察方向。")
        rec_text["reason_bullets_cn"] = reasons[:4]
        ah["main_ah_pick_cn"] = "亚盘结论：观察"
        ah["final_action_cn"] = "亚盘结论：观察。"
        ah["recommendation_grade"] = "观察"
        card["ah_pick_cn"] = (f"{candidate}｜仅观察｜来源：Policy Engine" if candidate else "候选方向待确认｜仅观察｜来源：Policy Engine")


def load_bundle_map() -> dict[str, dict]:
    if not BUNDLES.is_file():
        return {}
    try:
        payload = json.loads(BUNDLES.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {str(row.get("fixture_id")): row for row in payload.get("bundles", []) if row.get("fixture_id")}


BUNDLE_BY_FIXTURE = load_bundle_map()


def parse_embedded_calls(html: str) -> list[dict]:
    match = TAG_RE.search(html)
    if not match:
        return []
    text = match.group(0)
    text = text[text.find(">") + 1:text.rfind("</script>")]
    try:
        payload = json.loads(text)
    except Exception:
        return []
    calls = payload.get("calls", [])
    return calls if isinstance(calls, list) else []


def verify_embedded_fixture(fixture_id: str, stage_id: str | None = None) -> bool:
    if not HTML.is_file():
        return False
    for call in parse_embedded_calls(HTML.read_text(encoding="utf-8")):
        if str(call.get("fixture_id")) != str(fixture_id):
            continue
        if stage_id is not None and str(call.get("stage_id") or "") != str(stage_id):
            continue
        read = call.get("read")
        if not isinstance(read, dict):
            continue
        if isinstance(read.get("asian_handicap_card"), dict) or isinstance(read.get("recommendation_card"), dict):
            return True
    return False


def main() -> int:
    calls = json.loads(CALLS.read_text(encoding="utf-8")) if CALLS.is_file() else {"calls": []}
    generated_by = calls.get("generated_by")
    if generated_by == "deepseek:deepseek-v4-pro":
        generated_by = "deepseek:deepseek-pro"
    html = HTML.read_text(encoding="utf-8")
    html = upsert_tag(html, "w1-scout-calls", {"generated_by": generated_by, "calls": [display_call(c) for c in calls.get("calls", [])]}, TAG_RE)
    html = upsert_tag(html, "w1-scout-reviews", {"reviews": read_reviews()}, REVIEWS_TAG_RE)
    calibration = json.loads(CALIBRATION.read_text(encoding="utf-8")) if CALIBRATION.is_file() else {"schema_version": "W1_SCOUT_CALIBRATION_V1", "note_cn": "这是 Scout 解读的自我体检与校准,不是战胜市场的证据。"}
    html = upsert_tag(html, "w1-scout-calibration", calibration, CALIBRATION_TAG_RE)
    HTML.write_text(html, encoding="utf-8")
    embedded_calls = parse_embedded_calls(html)
    embedded_keys = {
        (str(call.get("fixture_id")), str(call.get("stage_id") or ""))
        for call in embedded_calls
        if call.get("fixture_id") and isinstance(call.get("read"), dict)
    }
    print(f"embedded {len(embedded_keys)} scout fixture/stage reads into dashboard ({HTML.relative_to(ROOT)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
