#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Checker for W1_SCOUT (AI analyst loop).

Guards: bundle is pre-match-only (no post-match leakage); every AI output is a
structured match read, not a prediction selector (has tilt/watch points/risks,
uses honest score-band language, carries an 'AI 解读' honesty label,
independent_edge=false, and avoids betting/guarantee/edge wording). Only ADDS
assertions; each safety rule has a reverse test.
"""
from __future__ import annotations

import json
import hashlib
import re
import sys
from pathlib import Path
from copy import deepcopy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from w1_results_overlay import load_results_map  # noqa: E402
import w1_scout_analyst as analyst_mod  # noqa: E402
import w1_recommendation_policy as W1REC  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
POLICY_P = ROOT / "config/w1_scout_policy.json"
SCHEMA_P = ROOT / "schemas/w1_scout_bundle_schema.json"
BUNDLE_MOD = ROOT / "scripts/w1_scout_bundle.py"
FETCHER = ROOT / "scripts/w1_scout_fetch_api_football.py"
MARKET_DEBUG = ROOT / "scripts/w1_scout_market_debug.py"
ANALYST = ROOT / "scripts/w1_scout_analyst.py"
REVIEW_MOD = ROOT / "scripts/w1_scout_review.py"
CALIBRATION_MOD = ROOT / "scripts/w1_scout_calibration.py"
BUNDLES_P = ROOT / "state/w1_scout_bundles.json"
CALLS_P = ROOT / "state/w1_scout_calls.json"
TRACK_P = ROOT / "state/scout_track_record.json"
LESSONS_P = ROOT / "state/scout_lessons.md"
AUDIT_P = ROOT / "state/scout_audit.jsonl"
LOCK_P = ROOT / "state/scout_lock.jsonl"
REVIEWS_P = ROOT / "state/scout_reviews.jsonl"
SCOUT_DIR = ROOT / "data/scout"

errors: list[str] = []

TAIL_TRIGGER_TOKENS = ("如果", "若", "一旦", "前 30 分钟", "前30分钟", "早球", "红牌", "被迫前压", "转换", "定位球", "门将失误")
REVERSE_FAILURE_TOKENS = ("如果上半场仍是 0-0", "如果上半场仍是0-0", "如果久攻不下", "如果低位防守成功", "如果首发进攻点缺席", "如果射门质量无法转化", "该剧本降权", "大比分剧本失效", "失效")
MARKET_TERMS = ("盘口", "让球", "大小球", "水位", "早盘", "临场", "盘口样本", "隐含")
MARKET_MISSING_TERMS = ("盘口数据缺失", "无法展开盘口剧本", "不展开盘口剧本", "盘口缺失", "让球盘口缺失", "大小球盘口缺失", "欧盘缺失", "市场读数缺失")
RECOMMENDATION_CARD_KEYS = (
    "one_x_two_cn",
    "score_picks_cn",
    "ou_pick_cn",
    "ah_pick_cn",
    "main_recommendation_cn",
    "risk_cn",
    "confidence_cn",
)
RECOMMENDATION_CARD_OPTIONAL_KEYS = ("data_status_cn",)
RECOMMENDATION_TEXT_KEYS = (
    "headline_cn",
    "grade_cn",
    "core_judgement_cn",
    "reason_bullets_cn",
    "score_recommendation_cn",
    "ou_aux_cn",
    "live_invalidation_cn",
)
SCRIPT_LAYER_KEYS = ("base_script_cn", "tail_script_cn", "reverse_script_cn", "market_script_cn")
AH_CARD_KEYS = (
    "schema_version",
    "fixture_id",
    "stage_id",
    "stage_label_cn",
    "data_readiness",
    "main_ah_pick_cn",
    "ah_side_cn",
    "ah_line",
    "ah_price",
    "current_handicap_cn",
    "ah_confidence_cn",
    "recommendation_grade",
    "ah_logic_cn",
    "cover_probability_model",
    "cover_probability_market",
    "cover_edge",
    "line_movement_cn",
    "water_movement_cn",
    "market_consensus_cn",
    "ou_pick_cn",
    "score_path_cn",
    "score_main_cn",
    "score_backup_cn",
    "risk_cn",
    "pass_reason_cn",
    "final_action_cn",
)
FUNDS_FORBIDDEN_TOKENS = ("下注", "重仓", "梭哈", "倍投", "加仓", "稳赚", "必红", "包中")
PROMISE_FORBIDDEN_TOKENS = ("必穿", "稳赢", "包赢", "保证命中", "资金建议")
ENGLISH_TEAM_TOKENS = ("Australia", "Türkiye", "Turkey", "South Korea", "Mexico", "USA")
RECOMMENDATION_SOURCE_TOKENS = ("来源：市场", "来源：市场赔率", "来源：W1模型", "来源：score matrix", "来源：缺失", "来源：盘口")
VISIBLE_FORBIDDEN_TOKENS = (
    "p_home",
    "p_draw",
    "p_away",
    "None",
    "null",
    "NaN",
    "undefined",
    "claim",
    "fields",
    "source",
    "availability",
    "weight",
    "历史样本-0",
    "1-历史样本-0",
    "xG若干",
    "若干",
    "LDDL",
    "赢盘",
    "输盘",
    "全赢",
    "走水",
    "不输不赢",
    "无输赢",
    "返还本金",
    "本金",
    "打出",
    "打穿盘口",
    "打穿概率",
    "打穿大球",
    "深穿",
    "暂无若干",
    "TBD",
)
WEAK_OVERCLAIM_TOKENS = ("概率较高", "确定", "明显", "强烈", "零封概率较高", "大胜概率较高", "明显打穿", "穿盘路径明确")
MARKET_MISSING_TEXT = "市场赔率数据缺失，暂时无法对比市场倾向。"
MARKET_SCRIPT_MISSING_TEXT = "盘口数据缺失，无法展开让球覆盖或大小球触发判断；本场只保留比赛剧本推演。"
XG_WEAK_TEXT = "xG 样本不足，只作为弱参考。"


def fail(m):
    errors.append(m)


def script_binds_evidence(script: str, evidence_rows: list[dict]) -> bool:
    if not evidence_rows:
        return False
    compact_script = script.replace(" ", "")
    for row in evidence_rows:
        claim = str(row.get("claim") or "").strip()
        if claim and claim in script:
            return True
        compact_claim = claim.replace(" ", "")
        for size in (8, 6, 4):
            for idx in range(0, max(0, len(compact_claim) - size + 1)):
                piece = compact_claim[idx:idx + size]
                if piece and piece in compact_script:
                    return True
    return False


def visible_text_chunks(read: dict) -> list[str]:
    chunks: list[str] = []
    if not isinstance(read, dict):
        return chunks
    for key in ("tilt_cn", "score_band_cn", "vs_market_cn", "regular_script_cn", "high_variance_tail_script_cn", "market_expert_script_cn"):
        if read.get(key):
            chunks.append(str(read.get(key)))
    for key in ("watch_points_cn", "risks_cn", "evidence_chain_cn", "reverse_risks_cn"):
        value = read.get(key)
        if isinstance(value, list):
            chunks.extend(str(item) for item in value if str(item).strip())
        elif value:
            chunks.append(str(value))
    evidence_rows = read.get("evidence")
    if isinstance(evidence_rows, list):
        chunks.extend(str(row.get("claim") or "") for row in evidence_rows if isinstance(row, dict))
    layers = read.get("script_layers")
    if isinstance(layers, dict):
        chunks.extend(str(layers.get(key) or "") for key in SCRIPT_LAYER_KEYS)
    card = read.get("recommendation_card")
    if isinstance(card, dict):
        chunks.extend(str(card.get(key) or "") for key in RECOMMENDATION_CARD_KEYS + RECOMMENDATION_CARD_OPTIONAL_KEYS)
    rec_text = read.get("recommendation_text")
    if isinstance(rec_text, dict):
        for key in RECOMMENDATION_TEXT_KEYS:
            value = rec_text.get(key)
            if isinstance(value, list):
                chunks.extend(str(item or "") for item in value)
            else:
                chunks.append(str(value or ""))
    ah_card = read.get("asian_handicap_card")
    if isinstance(ah_card, dict):
        chunks.extend(str(ah_card.get(key) or "") for key in AH_CARD_KEYS)
    return chunks


def weak_low_evidence(read: dict, readiness: str) -> bool:
    if readiness not in {"中", "低"}:
        return False
    evidence_rows = read.get("evidence") if isinstance(read, dict) else []
    market_missing = False
    xg_weak = False
    if isinstance(evidence_rows, list):
        for row in evidence_rows:
            if not isinstance(row, dict):
                continue
            source = str(row.get("source") or "")
            availability = str(row.get("availability") or "")
            if source == "market" and availability == "missing":
                market_missing = True
            if source == "xg_roll" and availability in {"weak_sample", "partial", "missing"}:
                xg_weak = True
    visible = "\n".join(visible_text_chunks(read))
    if MARKET_MISSING_TEXT in visible or "盘口数据缺失" in visible:
        market_missing = True
    if XG_WEAK_TEXT in visible or "xG样本不足" in visible:
        xg_weak = True
    return market_missing and xg_weak


def validate_data_wording(read: dict, readiness: str) -> list[str]:
    errs: list[str] = []
    visible = "\n".join(visible_text_chunks(read))
    for match in re.finditer(r"近\s*(\d+)\s*场\s*(\d+)\s*胜\s*(\d+)\s*平\s*(\d+)\s*负", visible):
        n, w, d, l = (int(item) for item in match.groups())
        if w + d + l != n:
            errs.append(f"recent form W-D-L sum mismatch: {match.group(0)}")
    for match in re.finditer(r"近\s*(\d+)\s*场[^。；;\n]{0,28}", visible):
        snippet = match.group(0)
        n = int(match.group(1))
        counts = []
        for label in ("胜", "平", "负"):
            token_match = re.search(r"([0-9一二三四五六七八九十两]+)\s*" + label, snippet)
            if token_match:
                counts.append(_small_cn_int(token_match.group(1)))
        if counts and all(item is not None for item in counts) and sum(int(item) for item in counts) != n:
            errs.append(f"recent form W-D-L sum mismatch: {snippet}")
    for match in re.finditer(r"xG\s*(?:为|约|=|:|：)?\s*\d+(?:\.\d+)?\s*[（(][^）)]*\d+\s*场[^）)]*[）)]", visible, flags=re.I):
        start = max(0, match.start() - 24)
        end = min(len(visible), match.end() + 24)
        window = visible[start:end]
        if not any(token in window for token in ("总量", "累计", "场均", "平均", "每场", "avg", "total")):
            errs.append(f"xG wording missing total/avg basis: {match.group(0)}")
    for match in re.finditer(r"[0-9一二三四五六七八九十两]+\s*场[^。；;\n]{0,12}xG\s*(?:为|约|=|:|：)?\s*\d+(?:\.\d+)?", visible, flags=re.I):
        start = max(0, match.start() - 16)
        end = min(len(visible), match.end() + 16)
        window = visible[start:end]
        if not any(token in window for token in ("总量", "累计", "场均", "平均", "每场", "avg", "total")):
            errs.append(f"xG wording missing total/avg basis: {match.group(0)}")
    tail = str(read.get("high_variance_tail_script_cn") or "")
    if weak_low_evidence(read, readiness) and re.search(r"(?:^|[^0-9])(?:[3-9]-0|0-[3-9])(?:[^0-9]|$)", tail):
        errs.append("weak evidence context must not state a strong 3-0/0-3 tail score without sufficient support")
    return errs


def _small_cn_int(text: str) -> int | None:
    text = text.strip()
    if text.isdigit():
        return int(text)
    mapping = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if text in mapping:
        return mapping[text]
    if text == "十":
        return 10
    if text.startswith("十") and len(text) == 2 and text[1] in mapping:
        return 10 + mapping[text[1]]
    if "十" in text:
        left, right = text.split("十", 1)
        if left in mapping:
            return mapping[left] * 10 + (mapping.get(right, 0) if right else 0)
    return None


def validate_visible_text(read: dict, readiness: str) -> list[str]:
    errs: list[str] = []
    chunks = visible_text_chunks(read)
    visible = "\n".join(chunks)
    for token in VISIBLE_FORBIDDEN_TOKENS:
        if token in visible:
            errs.append(f"visible Scout text contains forbidden token: {token}")
    for token in FUNDS_FORBIDDEN_TOKENS:
        if token in visible:
            errs.append(f"recommendation card / visible Scout text contains forbidden funds token: {token}")
    for token in PROMISE_FORBIDDEN_TOKENS:
        if token in visible:
            errs.append(f"visible Scout text contains forbidden promise token: {token}")
    for token in ENGLISH_TEAM_TOKENS:
        if token in visible:
            errs.append(f"visible Scout text contains English team token: {token}")
    score_band = str(read.get("score_band_cn") or "")
    if "历史样本" in score_band or "若干" in score_band:
        errs.append("score_band_cn must not contain machine fallback tokens")
    market_script = str(read.get("market_expert_script_cn") or "")
    if any(token in market_script for token in ("p_home", "p_draw", "p_away", "None", "null", "NaN", "undefined")):
        errs.append("market_expert_script_cn must not expose market variables or missing sentinels")
    if "盘口数据缺失" in market_script and MARKET_SCRIPT_MISSING_TEXT not in market_script:
        errs.append("market_expert_script_cn must use the approved market-missing sentence")
    if weak_low_evidence(read, readiness):
        for token in WEAK_OVERCLAIM_TOKENS:
            if token in visible:
                errs.append(f"weak evidence context overclaims: {token}")
    errs.extend(validate_data_wording(read, readiness))
    return errs


def validate_recommendation_card(read: dict, readiness: str) -> list[str]:
    errs: list[str] = []
    card = read.get("recommendation_card")
    if not isinstance(card, dict):
        return ["read.recommendation_card must be an object"]
    for key in RECOMMENDATION_CARD_KEYS:
        value = str(card.get(key) or "").strip()
        if not value:
            errs.append(f"read.recommendation_card.{key} missing")
        if len(value) > 80:
            errs.append(f"read.recommendation_card.{key} too long (>80 chars)")
    confidence = str(card.get("confidence_cn") or "")
    if confidence not in {"高", "中", "低"}:
        errs.append("read.recommendation_card.confidence_cn must be 高/中/低")
    if readiness == "低":
        joined = "\n".join(str(card.get(key) or "") for key in RECOMMENDATION_CARD_KEYS + RECOMMENDATION_CARD_OPTIONAL_KEYS)
        if "观察" not in joined and "降级" not in joined:
            errs.append("low data_readiness recommendation_card must explicitly show 观察 or 降级")
        strong_tokens = ("强推", "确定", "重心", "首选直接", "单关")
        for token in strong_tokens:
            if token in joined:
                errs.append(f"low data_readiness recommendation_card overstates: {token}")
    one_x_two = str(card.get("one_x_two_cn") or "")
    card_text = "\n".join(str(card.get(key) or "") for key in RECOMMENDATION_CARD_KEYS + RECOMMENDATION_CARD_OPTIONAL_KEYS)
    if not any(token in card_text for token in RECOMMENDATION_SOURCE_TOKENS):
        errs.append("recommendation_card must include an explicit 来源 label")
    if not any(token in one_x_two for token in ("主胜", "平", "客胜", "1X2", "胜平负")):
        errs.append("recommendation_card.one_x_two_cn must use 1X2 / 主胜平客胜 wording")
    if "比分" not in str(card.get("score_picks_cn") or "") and not any(token in str(card.get("score_picks_cn") or "") for token in ("首选", "次选", "风险", "观察")):
        errs.append("recommendation_card.score_picks_cn must use score pick / observation wording")
    if "大小球" not in str(card.get("ou_pick_cn") or "") and not any(token in str(card.get("ou_pick_cn") or "") for token in ("大", "小", "2.5")):
        errs.append("recommendation_card.ou_pick_cn must mention totals / 大小球")
    if "让球" not in str(card.get("ah_pick_cn") or "") and not any(token in str(card.get("ah_pick_cn") or "") for token in ("受让", "+", "-")):
        errs.append("recommendation_card.ah_pick_cn must mention handicap / 让球")
    return errs


def validate_recommendation_text(read: dict, ah_grade: str) -> list[str]:
    errs: list[str] = []
    text = read.get("recommendation_text")
    if not isinstance(text, dict):
        return ["read.recommendation_text must be an object"]
    for key in RECOMMENDATION_TEXT_KEYS:
        if key not in text:
            errs.append(f"read.recommendation_text.{key} missing")
    headline = str(text.get("headline_cn") or "")
    core = str(text.get("core_judgement_cn") or "")
    reasons = text.get("reason_bullets_cn")
    invalid = text.get("live_invalidation_cn")
    if not ("AI亚盘推荐" in headline or "AI亚盘结论" in headline):
        errs.append("recommendation_text.headline_cn must start as AI AH recommendation/conclusion")
    if not isinstance(reasons, list) or len([x for x in reasons if str(x).strip()]) < 3:
        errs.append("recommendation_text.reason_bullets_cn needs at least 3 bullets")
    if not isinstance(invalid, list) or len([x for x in invalid if str(x).strip()]) < 3:
        errs.append("recommendation_text.live_invalidation_cn needs at least 3 conditions")
    if ah_grade in {"A", "A-", "B+", "B"}:
        for token in ("W1覆盖率", "市场隐含"):
            if token not in core:
                errs.append(f"graded recommendation core_judgement_cn must mention {token}")
        joined = "\n".join(str(x) for x in (reasons or [])) + "\n" + "\n".join(str(x) for x in (invalid or [])) + "\n" + core
        for token in ("盘口", "水位", "比分"):
            if token not in joined:
                errs.append(f"graded recommendation_text must mention {token}")
        if not any(token in joined for token in ("失效", "降权", "降级")):
            errs.append("graded recommendation_text must mention invalidation/degrade semantics")
    if ah_grade in {"PASS", "C/观察"}:
        joined = headline + "\n" + core + "\n" + "\n".join(str(x) for x in (reasons or [])) + "\n" + "\n".join(str(x) for x in (invalid or []))
        if not any(token in joined for token in ("PASS", "观察", "降级")):
            errs.append("PASS/observation recommendation_text must state PASS/观察/降级")
        if not any(token in joined for token in ("重新评估", "等待", "再确认", "观察")):
            errs.append("PASS/observation recommendation_text must include observation/re-evaluation condition")
    return errs


def _is_num(value) -> bool:
    return isinstance(value, (int, float))


def validate_asian_handicap_card(read: dict, readiness: str) -> list[str]:
    errs: list[str] = []
    card = read.get("asian_handicap_card")
    if not isinstance(card, dict):
        return ["read.asian_handicap_card must be an object"]
    for key in AH_CARD_KEYS:
        if key not in card:
            errs.append(f"read.asian_handicap_card.{key} missing")
    if card.get("schema_version") != "scout_ah_recommendation_v1":
        errs.append("read.asian_handicap_card.schema_version mismatch")
    grade = str(card.get("recommendation_grade") or "")
    if grade not in {"A", "A-", "B+", "B", "C/观察", "PASS"}:
        errs.append(f"invalid AH recommendation_grade {grade}")
    text = "\n".join(str(card.get(key) or "") for key in AH_CARD_KEYS)
    if "1X2" in str(card.get("main_ah_pick_cn") or "") or "主胜" in str(card.get("main_ah_pick_cn") or ""):
        errs.append("AH card must not use 1X2 as primary pick")
    if not any(token in text for token in ("亚盘", "让球", "受让", "主推", "PASS / 观察")):
        errs.append("AH card must prioritize Asian handicap wording")
    for token in FUNDS_FORBIDDEN_TOKENS + PROMISE_FORBIDDEN_TOKENS:
        if token in text:
            errs.append(f"AH card contains forbidden token: {token}")
    for token in ENGLISH_TEAM_TOKENS:
        if token in text:
            errs.append(f"AH card contains English team token: {token}")
    if "客队受让 -" in text:
        errs.append("AH card must not say 客队受让 with a negative line")
    if "主队让球 +" in text:
        errs.append("AH card must not say 主队让球 with a positive line")
    main_pick = str(card.get("main_ah_pick_cn") or "")
    current = str(card.get("current_handicap_cn") or "") + "\n" + str(card.get("ah_logic_cn") or "")
    if re.search(r"\+\s*0\.5", main_pick) and re.search(r"-\s*0\.5", current):
        errs.append("AH card sign mismatch: +0.5 main pick conflicts with -0.5 current handicap")
    if readiness == "低" and grade not in {"PASS", "C/观察"}:
        errs.append("low data_readiness AH card must be PASS/C observation")
    if readiness == "低" and "观察" not in text:
        errs.append("low data_readiness AH card must explicitly show 观察")
    if grade in {"A", "A-", "B+"}:
        for key in ("main_ah_pick_cn", "ah_side_cn", "ah_confidence_cn", "risk_cn", "final_action_cn"):
            if not str(card.get(key) or "").strip():
                errs.append(f"grade {grade} AH card missing {key}")
        for key in ("ah_line", "ah_price", "cover_probability_model", "cover_probability_market", "cover_edge"):
            if not _is_num(card.get(key)):
                errs.append(f"grade {grade} AH card missing numeric {key}")
        if "亚盘主推" not in str(card.get("final_action_cn") or ""):
            errs.append(f"grade {grade} final_action_cn must say 亚盘主推")
    else:
        if not str(card.get("pass_reason_cn") or "").strip():
            errs.append("PASS/C AH card must include pass_reason_cn")
    return errs


def market_has_lines(bundle: dict) -> bool:
    market = bundle.get("market") if isinstance(bundle.get("market"), dict) else {}
    availability = bundle.get("availability") if isinstance(bundle.get("availability"), dict) else {}
    has_ah = availability.get("market_ah") == "available" or (
        market.get("ah_line") not in (None, "")
        and isinstance(market.get("ah_home_price"), (int, float))
        and isinstance(market.get("ah_away_price"), (int, float))
    )
    has_ou = availability.get("market_ou") == "available" or (
        market.get("ou_line") not in (None, "")
        and isinstance(market.get("over_price"), (int, float))
        and isinstance(market.get("under_price"), (int, float))
    )
    return bool(has_ah or has_ou)


def model_has_1x2(bundle: dict) -> bool:
    market = bundle.get("market") if isinstance(bundle.get("market"), dict) else {}
    availability = bundle.get("availability") if isinstance(bundle.get("availability"), dict) else {}
    return availability.get("model_1x2") == "available" or all(
        isinstance(market.get(key), (int, float)) for key in ("model_p_home", "model_p_draw", "model_p_away")
    )


def market_all_missing(bundle: dict) -> bool:
    availability = bundle.get("availability") if isinstance(bundle.get("availability"), dict) else {}
    return all(availability.get(key) != "available" for key in ("market_1x2", "market_ah", "market_ou"))


def validate_call_against_bundle(call: dict, bundle: dict) -> list[str]:
    errs: list[str] = []
    read = call.get("read") if isinstance(call.get("read"), dict) else {}
    market_script = str(read.get("market_expert_script_cn") or "")
    card = read.get("recommendation_card") if isinstance(read.get("recommendation_card"), dict) else {}
    ah_card = read.get("asian_handicap_card") if isinstance(read.get("asian_handicap_card"), dict) else {}
    card_text = "\n".join(str(card.get(key) or "") for key in RECOMMENDATION_CARD_KEYS + RECOMMENDATION_CARD_OPTIONAL_KEYS)
    availability = bundle.get("availability") if isinstance(bundle.get("availability"), dict) else {}
    has_ah = availability.get("market_ah") == "available"
    has_ou = availability.get("market_ou") == "available"
    has_1x2 = availability.get("market_1x2") == "available"
    if market_has_lines(bundle):
        if "盘口数据缺失" in market_script or "无法展开盘口剧本" in market_script or "不展开盘口剧本" in market_script:
            errs.append("market AH/OU available but call still says market data is missing")
        if any(token in card_text for token in ("盘口缺失", "盘口数据缺失", "暂不输出大小球推荐", "暂不输出让球推荐")):
            errs.append("market AH/OU available but recommendation_card still says odds are missing")
        if not ("让球" in market_script and "大小球" in market_script and any(token in market_script for token in REVERSE_FAILURE_TOKENS + TAIL_TRIGGER_TOKENS)):
            errs.append("market AH/OU available but market_expert_script_cn lacks handicap/totals/condition language")
    if has_ah:
        ah_text = "\n".join(str(ah_card.get(key) or "") for key in AH_CARD_KEYS) + "\n" + str(card.get("ah_pick_cn") or "")
        if any(token in ah_text for token in ("让球盘口缺失", "盘口缺失", "暂不输出让球推荐", "W1覆盖概率缺失")):
            errs.append("market AH available but AH card/recommendation says handicap or W1 cover is missing")
    if has_ou:
        ou_text = str(card.get("ou_pick_cn") or "") + "\n" + str(ah_card.get("ou_pick_cn") or "")
        if any(token in ou_text for token in ("大小球盘口缺失", "盘口缺失", "暂不输出大小球推荐", "totals missing")):
            errs.append("market OU available but recommendation_card says totals are missing")
    if has_1x2:
        one_x_two_text = str(card.get("one_x_two_cn") or "") + "\n" + str(ah_card.get("market_consensus_cn") or "")
        if any(token in one_x_two_text for token in ("市场读数缺失", "欧盘缺失", "1X2 数据缺失", "暂不展开胜平负推荐")):
            errs.append("market 1X2 available but recommendation_card says 1X2 is missing")
    market = bundle.get("market") if isinstance(bundle.get("market"), dict) else {}
    ah = market.get("ah") if isinstance(market.get("ah"), dict) else {}
    if has_ah and availability.get("model_1x2") == "available" and ah.get("cover_probability_model") is None:
        errs.append("market AH + W1 matrix available but bundle missing W1 cover probability")
    if has_ah and ah.get("cover_probability_model") is not None:
        if ah_card.get("cover_probability_model") is None:
            errs.append("AH available with score matrix but asian_handicap_card missing cover_probability_model")
        if str(ah_card.get("recommendation_grade") or "") in {"A", "A-", "B+"} and not str(ah_card.get("final_action_cn") or "").startswith("亚盘主推"):
            errs.append("graded AH card must be an Asian-handicap primary recommendation")
    if not has_ah:
        if str(ah_card.get("recommendation_grade") or "") in {"A", "A-", "B+"}:
            errs.append("AH missing but asian_handicap_card still makes a graded recommendation")
    if str(ah_card.get("recommendation_grade") or "") in {"PASS", "C/观察"}:
        reason = str(ah_card.get("pass_reason_cn") or "").strip()
        allowed_reason = any(token in reason for token in ("覆盖差", "cover edge", "盘口缺失", "AH盘口", "AH 盘口", "模型覆盖概率缺失", "W1覆盖概率缺失", "覆盖概率缺失", "数据就绪度", "低", "冲突", "异常", "观察", "≤ 0", "<= 0", "无正向覆盖"))
        if not allowed_reason:
            errs.append("PASS/C AH card must include a machine-readable pass_reason tied to edge/data/conflict/missing")
    if model_has_1x2(bundle):
        one_x_two = str(card.get("one_x_two_cn") or "")
        if "缺失" in one_x_two or "暂不展开胜平负推荐" in one_x_two:
            errs.append("W1 model 1X2 available but recommendation_card.one_x_two_cn still says missing")
        if "来源：W1模型" not in one_x_two and "来源：市场" not in one_x_two:
            errs.append("1X2 recommendation must label source as W1模型 or market when model 1X2 exists")
    elif market_all_missing(bundle):
        has_market_terms = any(token in market_script for token in MARKET_TERMS)
        has_missing = any(token in market_script for token in MARKET_MISSING_TERMS)
        if has_market_terms and not has_missing:
            errs.append("market all missing but call invents market expert script")
    return errs


def validate_script_layers(read: dict, style_mode: str, readiness: str, grade: str) -> list[str]:
    errs: list[str] = []
    layers = read.get("script_layers")
    if not isinstance(layers, dict):
        return ["read.script_layers must be an object"]
    for key in SCRIPT_LAYER_KEYS:
        if not str(layers.get(key) or "").strip():
            errs.append(f"read.script_layers.{key} missing")
    base = str(layers.get("base_script_cn") or "")
    tail = str(layers.get("tail_script_cn") or "")
    reverse = str(layers.get("reverse_script_cn") or "")
    market = str(layers.get("market_script_cn") or "")
    if len(base.strip()) < 8:
        errs.append("script_layers.base_script_cn must describe the normal AH script")
    if style_mode == "aggressive_script":
        if not tail.strip():
            errs.append("aggressive_script requires script_layers.tail_script_cn")
        if not reverse.strip():
            errs.append("aggressive_script requires script_layers.reverse_script_cn")
        if not market.strip():
            errs.append("aggressive_script requires script_layers.market_script_cn")
        combined = "\n".join([tail, reverse, market])
        if not any(token in tail for token in TAIL_TRIGGER_TOKENS):
            errs.append("aggressive_script tail_script_cn must include trigger semantics")
        if not any(token in combined for token in REVERSE_FAILURE_TOKENS):
            errs.append("aggressive_script must include failure/invalidating semantics")
        if any(token in tail for token in ("3-1", "4-1", "5-2", "穿盘")):
            if not any(token in tail for token in TAIL_TRIGGER_TOKENS):
                errs.append("aggressive big-tail/cover script must include trigger semantics")
            if not any(token in combined for token in REVERSE_FAILURE_TOKENS):
                errs.append("aggressive big-tail/cover script must include failure semantics")
        if readiness == "低":
            if grade in {"A", "B+"}:
                errs.append("low data_readiness aggressive_script must not be A/B+")
            if re.search(r"(?:4-1|5-2|[4-9]-[0-9]|[0-9]-[4-9])", tail):
                errs.append("low data_readiness aggressive_script must not state big-score tail")
            for token in ("强穿盘", "穿盘路径明确", "明显穿盘"):
                if token in tail + market:
                    errs.append("low data_readiness aggressive_script must not state strong cover conclusion")
    return errs


def validate_call(c: dict, policy: dict) -> list[str]:
    errs: list[str] = []
    if c.get("schema_version") != "scout_ah_recommendation_v2":
        errs.append("schema_version must be scout_ah_recommendation_v2")
    legacy_runtime = c.get("_legacy_runtime_normalized") is True
    if not str(c.get("generated_at") or "").strip() and not legacy_runtime:
        errs.append("generated_at required for Scout v2 call ordering")
    if not (str(c.get("stage_id") or "").strip() or str(c.get("stage_label_cn") or "").strip()) and not legacy_runtime:
        errs.append("Scout v2 call requires stage_id or stage_label_cn")
    if c.get("style_mode") not in {"conservative", "balanced", "aggressive_script"}:
        errs.append(f"invalid style_mode {c.get('style_mode')}")
    if c.get("safety_label") != "亚盘研究推荐 · 非资金指令 · 不承诺结果":
        errs.append("safety_label mismatch")
    policy_result = c.get("policy_result")
    if not isinstance(policy_result, dict):
        errs.append("policy_result must be present")
    else:
        for issue in W1REC.policy_consistency_issues(c):
            errs.append(f"policy_result consistency: {issue}")
        if c.get("policy_enforced") is not True:
            errs.append("policy_enforced must be true")
    for f in policy["read_required_fields"]:
        if f not in c:
            errs.append(f"missing field {f}")
    read = c.get("read") or {}
    if not isinstance(read, dict):
        errs.append("read must be object")
        read = {}
    for f in policy["read_subfields"]["read"]:
        if f not in read:
            errs.append(f"read.{f} missing")
    errs.extend(validate_recommendation_card(read, str(c.get("data_readiness") or "")))
    errs.extend(validate_asian_handicap_card(read, str(c.get("data_readiness") or "")))
    ah_grade = str((read.get("asian_handicap_card") or {}).get("recommendation_grade") or "") if isinstance(read.get("asian_handicap_card"), dict) else ""
    errs.extend(validate_recommendation_text(read, ah_grade))
    errs.extend(validate_script_layers(read, str(c.get("style_mode") or ""), str(c.get("data_readiness") or ""), ah_grade))
    watch = read.get("watch_points_cn")
    risks = read.get("risks_cn")
    if not isinstance(watch, list) or len([x for x in watch if str(x).strip()]) < 2:
        errs.append("bare translation rejected: need at least 2 watch_points_cn")
    if not isinstance(risks, list) or len([x for x in risks if str(x).strip()]) < 1:
        errs.append("bare translation rejected: need at least 1 risks_cn")
    evidence_contract = policy.get("evidence_contract") or {}
    evidence_rows = read.get("evidence")
    if not isinstance(evidence_rows, list) or len(evidence_rows) < int(evidence_contract.get("min_items", 2)):
        errs.append("read.evidence must include at least 2 structured evidence rows")
        evidence_rows = []
    allowed_sources = set(evidence_contract.get("sources") or [])
    allowed_availability = set(evidence_contract.get("availability") or [])
    allowed_weight = set(evidence_contract.get("weight") or [])
    required_evidence_fields = set(evidence_contract.get("required_fields") or [])
    for idx, row in enumerate(evidence_rows):
        if not isinstance(row, dict):
            errs.append(f"read.evidence[{idx}] must be object")
            continue
        missing = required_evidence_fields - set(row)
        if missing:
            errs.append(f"read.evidence[{idx}] missing fields: {sorted(missing)}")
        if str(row.get("source") or "") not in allowed_sources:
            errs.append(f"read.evidence[{idx}] invalid source {row.get('source')}")
        if str(row.get("availability") or "") not in allowed_availability:
            errs.append(f"read.evidence[{idx}] invalid availability {row.get('availability')}")
        if str(row.get("weight") or "") not in allowed_weight:
            errs.append(f"read.evidence[{idx}] invalid weight {row.get('weight')}")
        fields = row.get("fields")
        if not isinstance(fields, list) or not fields or not all(isinstance(x, str) and x.strip() for x in fields):
            errs.append(f"read.evidence[{idx}] fields must be a non-empty string array")
        if not str(row.get("claim") or "").strip():
            errs.append(f"read.evidence[{idx}] claim must be non-empty")
    evidence = read.get("evidence_chain_cn")
    if not isinstance(evidence, list) or len([x for x in evidence if str(x).strip()]) < 2:
        errs.append("evidence_chain_cn must include at least 2 data evidence bullets")
    reverse_risks = read.get("reverse_risks_cn")
    if not isinstance(reverse_risks, list) or len([x for x in reverse_risks if str(x).strip()]) < 1:
        errs.append("reverse_risks_cn must include at least 1 reverse path")
    regular_script = str(read.get("regular_script_cn") or "")
    if len(regular_script.strip()) < 8:
        errs.append("regular_script_cn must describe the normal match script")
    if evidence_rows and not script_binds_evidence(regular_script, evidence_rows):
        errs.append("regular_script_cn must bind at least 1 structured evidence row")
    tail_script = str(read.get("high_variance_tail_script_cn") or "")
    if not any(token in tail_script for token in ("高方差", "早球", "红牌", "转换", "定位球", "门将", "尾部")):
        errs.append("high_variance_tail_script_cn must describe a tail/high-variance script")
    if not any(token in tail_script for token in TAIL_TRIGGER_TOKENS):
        errs.append("high_variance_tail_script_cn must include a concrete trigger condition")
    if evidence_rows and not script_binds_evidence(tail_script, evidence_rows):
        errs.append("high_variance_tail_script_cn must bind at least 1 structured evidence claim verbatim")
    reverse_text = "\n".join(str(x) for x in reverse_risks) if isinstance(reverse_risks, list) else ""
    if not any(token in reverse_text for token in REVERSE_FAILURE_TOKENS):
        errs.append("reverse_risks_cn must include at least 1 failure/invalidating condition")
    market_script = str(read.get("market_expert_script_cn") or "")
    market_has_terms = any(token in market_script for token in MARKET_TERMS)
    market_missing = any(token in market_script for token in MARKET_MISSING_TERMS)
    market_has_condition = any(token in market_script for token in TAIL_TRIGGER_TOKENS + REVERSE_FAILURE_TOKENS)
    if not ((market_has_terms and market_has_condition) or market_missing):
        errs.append("market_expert_script_cn must either use market-language with a condition or explicitly say market data is missing")
    score_band = str(read.get("score_band_cn") or "")
    if not any(token in score_band for token in ("区间", "分布", "别当真", "偏")):
        errs.append("score_band_cn must use band/distribution language")
    readiness = c.get("data_readiness")
    if readiness not in policy["readiness_levels"]:
        errs.append(f"invalid data_readiness {readiness}")
    errs.extend(validate_visible_text(read, str(readiness or "")))
    if policy["honesty"]["honesty_label_required_substr"] not in str(c.get("honesty_label", "")):
        errs.append("honesty_label must contain 'AI 解读'")
    if c.get("independent_edge") is not False:
        errs.append("independent_edge must be false")
    for old in ("call", "market_divergence", "key_factors_cn", "conviction", "track_record_context_cn"):
        if old in c:
            errs.append(f"old prediction field forbidden: {old}")
    text = json.dumps(c, ensure_ascii=False)
    for t in policy["forbidden_terms"]:
        if t in text:
            errs.append(f"forbidden term: {t}")
    return errs


def normalize_runtime_call_for_validation(call: dict, bundle: dict | None) -> dict:
    """Validate old gitignored runtime calls through the current AH-first hardener.

    This keeps local state files from blocking source checks after schema upgrades
    without mutating state/w1_scout_calls.json or weakening validate_call() for new
    model output and reverse tests.
    """
    fid = str(call.get("fixture_id") or (bundle or {}).get("fixture_id") or "")
    try:
        normalized = analyst_mod.harden_call(deepcopy(call), fid, deepcopy(bundle) if bundle else None)
        if call.get("schema_version") != "scout_ah_recommendation_v2":
            normalized["_legacy_runtime_normalized"] = True
        return normalized
    except Exception:
        return deepcopy(call)


def bundle_leak(bundles, forbidden) -> list:
    hits = []
    for b in bundles:
        low = json.dumps(b, ensure_ascii=False).lower()
        for f in forbidden:
            if f.lower() in low:
                hits.append((b.get("fixture_id"), f))
        if b.get("asof_pre_kickoff") is not True:
            hits.append((b.get("fixture_id"), "asof_pre_kickoff!=true"))
    return hits


def validate_scout_payload(payload: dict, label: str, forbidden: list[str]) -> list[str]:
    errs: list[str] = []
    for key in ("fixture_id", "asof_pre_kickoff", "availability"):
        if key not in payload:
            errs.append(f"{label} missing {key}")
    if payload.get("asof_pre_kickoff") is not True:
        errs.append(f"{label} asof_pre_kickoff must be true")
    availability = payload.get("availability") or {}
    if not isinstance(availability, dict):
        errs.append(f"{label} availability must be object")
    else:
        bad = {k: v for k, v in availability.items() if v not in {"available", "partial", "missing"}}
        if bad:
            errs.append(f"{label} invalid availability values: {bad}")
    leaks = bundle_leak([payload], forbidden)
    for _, field in leaks:
        errs.append(f"{label} leaked post-match field: {field}")
    return errs


def validate_scout_file(path: Path, forbidden: list[str]) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path.relative_to(ROOT)} invalid JSON: {exc}"]
    errs = validate_scout_payload(payload, path.relative_to(ROOT).as_posix(), forbidden)
    return errs


def count_jsonl_rows(path: Path) -> int:
    rows = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows += 1
    return rows


def jsonl_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def digest_read(call: dict) -> str:
    blob = json.dumps(call, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def result_fixture_ids() -> set[str]:
    return set(load_results_map())


def validate_review_rows(reviews: list[dict], locks: dict[str, dict], finished: set[str], policy: dict) -> list[str]:
    errs: list[str] = []
    for row in reviews:
        fid = str(row.get("fixture_id"))
        if fid not in finished:
            errs.append(f"review {fid} has no local finished result")
        lock = locks.get(fid)
        if not lock:
            errs.append(f"review {fid} missing immutable lock")
            continue
        expected = lock.get("prematch_read_digest") or digest_read(lock.get("call") or {})
        if row.get("prematch_read_digest") != expected:
            errs.append(f"review {fid} prematch_read_digest mismatch")
        if row.get("honesty_label") != policy["honesty"]["review_label_exact"]:
            errs.append(f"review {fid} honesty label mismatch")
        text = json.dumps(row, ensure_ascii=False)
        for token in policy["forbidden_terms"]:
            if token in text:
                errs.append(f"review {fid} forbidden term: {token}")
    return errs


def validate_memory_consistency(track: dict, audit_rows: int) -> list[str]:
    overall = track.get("overall") or {}
    if "n" not in overall:
        return ["track_record overall.n missing"]
    if overall.get("n") != audit_rows:
        return [f"track_record overall.n={overall.get('n')} does not match scout_audit rows={audit_rows}"]
    return []


def main() -> int:
    for p in (POLICY_P, SCHEMA_P, BUNDLE_MOD, FETCHER, MARKET_DEBUG, ANALYST, REVIEW_MOD, CALIBRATION_MOD, BUNDLES_P, TRACK_P, LESSONS_P, AUDIT_P, LOCK_P):
        if not p.is_file():
            fail(f"missing artifact: {p.relative_to(ROOT)}")
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print("W1 scout check FAIL")
        return 1

    policy = json.loads(POLICY_P.read_text(encoding="utf-8"))
    forbidden_pm = policy["leakage"]["forbidden_postmatch_fields"]
    bundles = json.loads(BUNDLES_P.read_text(encoding="utf-8")).get("bundles", [])

    # bundle source must not read post-match results
    src = BUNDLE_MOD.read_text(encoding="utf-8")
    for tok in ("actual_score", "fulltime", "ft_score", "post_match_calibration"):
        # allowed only inside the leakage-guard comment, not as a field read
        if f'rec.get("{tok}")' in src or f"rec['{tok}']" in src:
            fail(f"bundle assembler reads post-match field: {tok}")

    fetcher = FETCHER.read_text(encoding="utf-8")
    for token in ("SCOUT_DIR", "data/scout", "load_api_key", "APIFOOTBALL_", "OPENCLAW_APIFOOTBALL_KEY"):
        if token not in fetcher:
            fail(f"fetcher missing token: {token}")
    for token in ("/fixtures?team=&season=&status=FT", "/fixtures/statistics?fixture=", "dt < kickoff"):
        if token not in fetcher:
            fail(f"fetcher missing pre-match rolling-data guard token: {token}")
    for token in ("--retries", "api-football retry", "failed fixtures after retries"):
        if token not in fetcher:
            fail(f"fetcher missing transient retry/continue guard token: {token}")
    for token in ("FORBIDDEN_POSTMATCH_KEYS", "strip_forbidden_postmatch_fields", "build_api_pred"):
        if token not in fetcher:
            fail(f"fetcher missing api response post-match scrub token: {token}")
    for token in ("/odds", "build_market_odds", "api-football /odds", "Asian Handicap", "Over/Under", "Match Winner"):
        if token not in fetcher:
            fail(f"fetcher missing odds-ingest token: {token}")
    for token in ("external_api_prediction", "third_party_model", "not_independent_edge"):
        if token not in fetcher:
            fail(f"api_pred must be labelled as third-party comparison only: {token}")
    if "write_json(RESULTS" in fetcher or "RESULTS_JSON" in fetcher:
        fail("fetcher must not write result ledger")
    if "w1_score_engine" in fetcher or "DEFAULT_RHO" in fetcher:
        fail("fetcher must not import/alter score engine")

    analyst = ANALYST.read_text(encoding="utf-8")
    for token in (
        "DEEPSEEK_API_KEY",
        "W1_SCOUT_LLM",
        "W1_SCOUT_BASE_URL",
        "https://api.deepseek.com/chat/completions",
        "deepseek-v4-pro",
        "validate_call",
        "state/w1_scout_calls.json",
        "honesty_label",
        "independent_edge",
        "--style-mode",
        "get_system_prompt",
        "aggressive_script",
        "script_layers",
        "scout_ah_recommendation_v2",
        "--dry-run",
    ):
        if token not in analyst:
            fail(f"analyst missing token: {token}")
    for token in (
        "script_layers{base_script_cn,tail_script_cn,reverse_script_cn,market_script_cn}",
        "read{tilt_cn,score_band_cn,watch_points_cn[],risks_cn[],vs_market_cn",
        "evidence[{claim,source,fields[],availability,weight}]",
        "asian_handicap_card{schema_version,fixture_id,stage_id,stage_label_cn,data_readiness,main_ah_pick_cn,ah_side_cn,ah_line,ah_price,current_handicap_cn,ah_confidence_cn,recommendation_grade,ah_logic_cn,cover_probability_model,cover_probability_market,cover_edge,line_movement_cn,water_movement_cn,market_consensus_cn,ou_pick_cn,score_path_cn,score_main_cn,score_backup_cn,risk_cn,pass_reason_cn,final_action_cn}",
        "recommendation_text{headline_cn,grade_cn,core_judgement_cn,reason_bullets_cn[],score_recommendation_cn,ou_aux_cn,live_invalidation_cn[]}",
        "recommendation_card{one_x_two_cn,score_picks_cn,ou_pick_cn,ah_pick_cn,main_recommendation_cn,risk_cn,confidence_cn,data_status_cn}",
        "evidence_chain_cn",
        "regular_script_cn",
        "high_variance_tail_script_cn",
        "reverse_risks_cn",
        "market_expert_script_cn",
        "AI 解读·非预测·非推介·可能错",
    ):
        if token not in analyst:
            fail(f"analyst missing read-schema token: {token}")
    for token in ("actual_score", "fulltime", "ft_score", "post_match_calibration", "w1_score_engine", "DEFAULT_RHO"):
        if token in analyst:
            fail(f"analyst must not read/use redline or post-match token: {token}")
    if "https://api.anthropic.com" in analyst or "ANTHROPIC_API_KEY" in analyst:
        fail("analyst must follow the T5 OpenAI-compatible route, not Anthropic-only routes")
    if "deepseek-chat" in analyst:
        fail("analyst must use fixed DeepSeek-V4-Pro (API id: deepseek-v4-pro) for the DeepSeek route")
    for token in ("previous_calls", "reused previous valid scout call"):
        if token in analyst:
            fail(f"analyst must not fallback to previous calls: {token}")
    review_src = REVIEW_MOD.read_text(encoding="utf-8")
    for token in ("prematch_read_digest", "AI 复盘·赛后对照", "state/scout_reviews.jsonl", "不许嘴硬", "hashlib.sha256"):
        if token not in review_src:
            fail(f"review script missing token: {token}")
    ledger_src = (ROOT / "scripts/w1_scout_ledger.py").read_text(encoding="utf-8")
    if "hashlib.sha256" not in ledger_src:
        fail("ledger digest must use sha256 canonical JSON")
    calibration_src = CALIBRATION_MOD.read_text(encoding="utf-8")
    for token in ("state/scout_calibration.json", "direction_calibration", "avg_readiness_dims", "不是战胜市场的证据"):
        if token not in calibration_src:
            fail(f"calibration script missing token: {token}")
    market_debug_src = MARKET_DEBUG.read_text(encoding="utf-8")
    for token in ("--fixture-id", "scout_file_exists", "cover_probability_model", "pass_reason"):
        if token not in market_debug_src:
            fail(f"market debug script missing token: {token}")

    # bundle leakage
    leaks = bundle_leak(bundles, forbidden_pm)
    if leaks:
        fail(f"scout bundle post-match leakage: {leaks[:5]}")
    if len(bundles) < 1:
        fail("no scout bundles built")
    for b in bundles:
        if (b.get("availability") or {}).get("market") not in {"available", "partial", "missing"}:
            fail(f"bundle {b.get('fixture_id')} availability.market missing or invalid")
        availability = b.get("availability") or {}
        for key in ("market_1x2", "model_1x2", "market_ah", "market_ou"):
            if availability.get(key) not in {"available", "missing"}:
                fail(f"bundle {b.get('fixture_id')} availability.{key} missing or invalid")
        market = b.get("market") or {}
        for key in ("p_home", "p_draw", "p_away", "model_p_home", "model_p_draw", "model_p_away", "model_1x2_source", "score_picks", "ah_line", "ah_home_price", "ah_away_price", "ou_line", "over_price", "under_price", "bookmaker_count", "market_source", "odds_updated_at", "one_x_two", "ah", "ou"):
            if key not in market:
                fail(f"bundle {b.get('fixture_id')} market missing key {key}")
        if availability.get("market_ah") == "available" and availability.get("model_1x2") == "available":
            ah = market.get("ah") if isinstance(market.get("ah"), dict) else {}
            for key in ("home_handicap", "home_price", "away_price", "cover_probability_model", "cover_probability_market", "cover_edge"):
                if key not in ah:
                    fail(f"bundle {b.get('fixture_id')} market.ah missing key {key}")
        if availability.get("market_ah") == "available" and availability.get("model_1x2") == "available":
            ah = market.get("ah") if isinstance(market.get("ah"), dict) else {}
            if "cover_probability_model" not in ah:
                fail(f"bundle {b.get('fixture_id')} has AH+W1 matrix inputs but missing cover_probability_model")

    if SCOUT_DIR.is_dir():
        for path in sorted(SCOUT_DIR.glob("*.json")):
            for err in validate_scout_file(path, forbidden_pm):
                fail(err)

    # growth files structure
    track = json.loads(TRACK_P.read_text(encoding="utf-8"))
    for k in ("overall", "updated_at"):
        if k not in track:
            fail(f"track_record missing section {k}")
    audit_rows = count_jsonl_rows(AUDIT_P)
    for err in validate_memory_consistency(track, audit_rows):
        fail(err)
    lessons_text = LESSONS_P.read_text(encoding="utf-8").strip()
    if not lessons_text:
        fail("scout_lessons.md must be non-empty")
    for t in policy["forbidden_terms"]:
        if t in lessons_text:
            fail(f"scout_lessons.md contains forbidden term: {t}")
    for memory_path in (AUDIT_P, TRACK_P, LESSONS_P, LOCK_P):
        text = memory_path.read_text(encoding="utf-8")
        for secret_token in ("DEEPSEEK_API_KEY", "APIFOOTBALL_KEY", "OPENCLAW_APIFOOTBALL_KEY", "Bearer ", "sk-"):
            if secret_token in text:
                fail(f"Scout memory file contains secret-like token {secret_token}: {memory_path.relative_to(ROOT)}")
    locks = {str(row.get("fixture_id")): row for row in jsonl_rows(LOCK_P)}
    finished = result_fixture_ids()
    for err in validate_review_rows(jsonl_rows(REVIEWS_P), locks, finished, policy):
        fail(err)

    # calls (validate if present)
    n_calls = 0
    if CALLS_P.is_file():
        calls = json.loads(CALLS_P.read_text(encoding="utf-8")).get("calls", [])
        n_calls = len(calls)
        bundle_by_fixture = {str(bundle.get("fixture_id")): bundle for bundle in bundles}
        seen = set()
        for c in calls:
            fid = c.get("fixture_id")
            if fid in seen:
                fail(f"duplicate call for fixture {fid}")
            seen.add(fid)
            c_for_validation = normalize_runtime_call_for_validation(c, bundle_by_fixture.get(str(fid)))
            for e in validate_call(c_for_validation, policy):
                fail(f"call {fid}: {e}")
            if str(fid) in bundle_by_fixture:
                for e in validate_call_against_bundle(c_for_validation, bundle_by_fixture[str(fid)]):
                    fail(f"call {fid}: {e}")

    # --- reverse tests ---
    base = {"schema_version": "scout_ah_recommendation_v2", "fixture_id": "X", "generated_at": "2026-06-20T00:00:00Z", "stage_id": "watch_6h", "stage_label_cn": "赛前观察", "style_mode": "balanced", "safety_label": "亚盘研究推荐 · 非资金指令 · 不承诺结果",
            "read": {"tilt_cn": "主队小优", "score_band_cn": "偏 1-0/2-0,但单场看区间、别当真",
                     "watch_points_cn": ["主队边路推进", "客队转换防守"], "risks_cn": ["早球会改变节奏"],
                     "vs_market_cn": "与市场差异不大,仅作讨论点",
                     "evidence": [
                         {"claim": "市场读数主队略低水", "source": "market", "fields": ["market"], "availability": "partial", "weight": "medium"},
                         {"claim": "阵容信息部分缺失", "source": "lineups", "fields": ["lineup"], "availability": "partial", "weight": "low"},
                     ],
                     "recommendation_text": {
                         "headline_cn": "AI亚盘推荐：主队 -0.25",
                         "grade_cn": "A-｜信心：中",
                         "core_judgement_cn": "主队略占优，但当前盘口仍需水位确认。主队 -0.25 有浅盘保护，W1覆盖率 53%，市场隐含 51%，模型侧多出约 2%，因此主线更偏向主队浅让。",
                         "reason_bullets_cn": ["主队 -0.25 覆盖小胜路径，盘口容错高于深盘。", "欧盘参考主胜45%、平29%、客胜26%，平局权重不低。", "比分路径集中在 1-0 / 1-1，不是大胜结构。"],
                         "score_recommendation_cn": "主比分：1-0；备选：1-1 / 2-1；风险：2-1",
                         "ou_aux_cn": "小2.5，信心中。若早球出现，小球方向失效。",
                         "live_invalidation_cn": ["主队 -0.25 退盘或水位明显反向。", "主队20分钟内早球后比赛进入开放节奏。", "主队首发进攻点缺席，当前方向降级观察。"]
                     },
                     "recommendation_card": {
                         "one_x_two_cn": "主胜 45%｜平 29%｜客胜 26%｜来源：市场赔率",
                         "score_picks_cn": "首选 1-0｜次选 1-1｜风险 2-1｜来源：score matrix",
                         "ou_pick_cn": "小2.5｜信心：中｜失效：早球｜来源：盘口",
                         "ah_pick_cn": "主队 -0.25｜信心：中｜覆盖深盘不稳｜来源：盘口",
                         "main_recommendation_cn": "主线看主队不败与低比分；让球只作覆盖条件讨论。",
                         "risk_cn": "若客队先球或主队久攻不下，主线降权。",
                         "confidence_cn": "中",
                         "data_status_cn": "市场赔率可用 / 数据部分缺失"
                     },
                     "asian_handicap_card": {
                         "schema_version": "scout_ah_recommendation_v1",
                         "fixture_id": "X",
                         "stage_id": "watch_6h",
                         "stage_label_cn": "赛前观察",
                         "data_readiness": "中",
                         "main_ah_pick_cn": "主队 -0.25",
                         "ah_side_cn": "主队让球",
                         "ah_line": -0.25,
                         "ah_price": 1.9,
                         "current_handicap_cn": "主队 -0.25 @ 1.9",
                         "ah_confidence_cn": "中",
                         "recommendation_grade": "A-",
                         "ah_logic_cn": "W1覆盖率 53% vs 市场隐含 51%，覆盖差 2%；主队让球方向只在盘口与水位维持时成立。",
                         "cover_probability_model": 0.53,
                         "cover_probability_market": 0.51,
                         "cover_edge": 0.02,
                         "line_movement_cn": "盘口基本稳定",
                         "water_movement_cn": "两侧水位接近",
                         "market_consensus_cn": "欧盘参考：主胜45%｜平29%｜客胜26%。",
                         "ou_pick_cn": "小2.5｜信心：中｜失效：早球",
                         "score_path_cn": "主线 1-0 12% / 1-1 11%；风险 2-1 9%",
                         "score_main_cn": "1-0",
                         "score_backup_cn": "1-1 / 2-1",
                         "risk_cn": "早球、首发关键点缺席、盘口退盘或水位反向，会削弱当前亚盘方向。",
                         "pass_reason_cn": "",
                         "final_action_cn": "亚盘主推：主队 -0.25；若临场退盘或水位反向，降级观察。"
                     },
                     "evidence_chain_cn": ["市场读数主队略低水", "阵容信息部分缺失,只作降权证据"],
                     "regular_script_cn": "常规剧本是市场读数主队略低水支撑主队压住节奏,通过边路和二点球慢慢建立优势。",
                     "high_variance_tail_script_cn": "如果市场读数主队略低水被早球或红牌打穿,尾部高方差剧本会让比赛脱离常规节奏。",
                     "reverse_risks_cn": ["如果低位防守成功,客队拖慢节奏后主队优势可能只停留在场面,大比分剧本失效。"],
                     "market_expert_script_cn": "若临场盘口样本仍显示早盘让球倾向主队,水位与样本厚度只作为读盘语境。",
                     "script_layers": {
                         "base_script_cn": "常规剧本是市场读数主队略低水支撑主队压住节奏,通过边路和二点球慢慢建立优势。",
                         "tail_script_cn": "如果市场读数主队略低水被早球或红牌打穿,尾部高方差剧本会让比赛脱离常规节奏。",
                         "reverse_script_cn": "如果低位防守成功,客队拖慢节奏后主队优势可能只停留在场面,大比分剧本失效。",
                         "market_script_cn": "若临场盘口样本仍显示早盘让球倾向主队,水位与样本厚度只作为读盘语境。"
                     }},
            "data_readiness": "中", "honesty_label": "AI 解读·非预测·非推介·可能错",
            "independent_edge": False}
    base_policy = W1REC.build_policy_result(W1REC._sample_bundle(0.055), W1REC.load_policy_config())
    base_policy.update({
        "decision_state": "RECOMMEND",
        "recommendation_grade": "A-",
        "main_ah_pick": "主队 -0.25",
        "candidate_ah_pick": "主队 -0.25",
        "main_ah_side": "home",
        "candidate_ah_side": "home",
        "failed_gates": [],
        "gate_severity": "none",
    })
    base["policy_result"] = base_policy
    base["policy_enforced"] = True
    if validate_call(base, policy):
        fail("reverse: a clean match read should pass")
    no_card = dict(base, read={**base["read"]})
    no_card["read"].pop("recommendation_card", None)
    if not validate_call(no_card, policy):
        fail("reverse: missing recommendation_card must be rejected")
    no_text = dict(base, read={**base["read"]})
    no_text["read"].pop("recommendation_text", None)
    if not validate_call(no_text, policy):
        fail("reverse: missing recommendation_text must be rejected")
    legacy = dict(base, call={"outcome_lean": "主", "scoreline_lean": "1-0", "confidence": "LOW"})
    if not validate_call(legacy, policy):
        fail("reverse: old prediction call field must be rejected")
    bare = dict(base, read={"tilt_cn": "主队小优", "score_band_cn": "1-0", "watch_points_cn": [], "risks_cn": [], "vs_market_cn": ""})
    if not validate_call(bare, policy):
        fail("reverse: bare translation (no watch/risks/band wording) must be rejected")
    no_evidence = dict(base, read={**base["read"], "evidence_chain_cn": []})
    if not validate_call(no_evidence, policy):
        fail("reverse: missing evidence chain must be rejected")
    bad_structured_evidence = dict(base, read={**base["read"], "evidence": [{"claim": "x", "source": "made_up", "fields": [], "availability": "ok", "weight": "strong"}]})
    if not validate_call(bad_structured_evidence, policy):
        fail("reverse: invalid structured evidence must be rejected")
    no_tail_trigger = dict(base, read={**base["read"], "high_variance_tail_script_cn": "尾部高方差剧本来自节奏变化。"})
    if not validate_call(no_tail_trigger, policy):
        fail("reverse: high variance script without trigger must be rejected")
    no_reverse_failure = dict(base, read={**base["read"], "reverse_risks_cn": ["客队也可能拖慢节奏"]})
    if not validate_call(no_reverse_failure, policy):
        fail("reverse: reverse risks without failure condition must be rejected")
    no_market_script = dict(base, read={**base["read"], "market_expert_script_cn": "普通自然语言描述"})
    if not validate_call(no_market_script, policy):
        fail("reverse: market expert script without market-language terms must be rejected")
    missing_market_script = dict(base, read={**base["read"], "market_expert_script_cn": "盘口数据缺失,不展开盘口剧本。"})
    if not validate_call(missing_market_script, policy):
        fail("reverse: short market-data-missing script must be rejected in favor of the approved sentence")
    approved_missing_market_script = dict(base, read={**base["read"], "market_expert_script_cn": MARKET_SCRIPT_MISSING_TEXT})
    if validate_call(approved_missing_market_script, policy):
        fail("reverse: approved market-data-missing script should pass")
    bad_visible_text = dict(base, read={
        **base["read"],
        "score_band_cn": "偏 1-历史样本-0",
        "evidence_chain_cn": ["市场读数 p_home=None", "数据claim 暴露了结构词"],
        "regular_script_cn": "常规剧本来自 claim 字段拼接。",
    })
    if not validate_call(bad_visible_text, policy):
        fail("reverse: visible machine/debug tokens must be rejected")
    weak_overclaim = dict(base, data_readiness="低", read={
        **base["read"],
        "evidence": [
            {"claim": "市场赔率数据缺失，暂时无法对比市场倾向。", "source": "market", "fields": ["market"], "availability": "missing", "weight": "low"},
            {"claim": "xG 样本不足，只作为弱参考。", "source": "xg_roll", "fields": ["xg_for"], "availability": "weak_sample", "weight": "low"},
        ],
        "evidence_chain_cn": ["市场赔率数据缺失，暂时无法对比市场倾向。", "xG 样本不足，只作为弱参考。"],
        "regular_script_cn": "常规剧本是市场赔率数据缺失，暂时无法对比市场倾向，但主队零封概率较高。",
        "high_variance_tail_script_cn": "如果 xG 样本不足，只作为弱参考，同时出现早球，尾部剧本打开。",
        "market_expert_script_cn": MARKET_SCRIPT_MISSING_TEXT,
    })
    if not validate_call(weak_overclaim, policy):
        fail("reverse: weak evidence overclaim must be rejected")
    bad_wdl = dict(base, read={**base["read"], "evidence_chain_cn": ["近期状态：近5场2胜3平2负。", "阵容信息部分缺失,只作降权证据"]})
    if not validate_call(bad_wdl, policy):
        fail("reverse: impossible recent form W-D-L count must be rejected")
    bad_cn_wdl = dict(base, read={**base["read"], "evidence_chain_cn": ["近期状态：近 5 场两平一负一胜。", "阵容信息部分缺失,只作降权证据"]})
    if not validate_call(bad_cn_wdl, policy):
        fail("reverse: impossible Chinese W-D-L count must be rejected")
    bad_xg_basis = dict(base, read={**base["read"], "evidence_chain_cn": ["xG 3.2（5场）", "阵容信息部分缺失,只作降权证据"]})
    if not validate_call(bad_xg_basis, policy):
        fail("reverse: xG number without total/avg basis must be rejected")
    bad_tail_score = dict(weak_overclaim, read={**weak_overclaim["read"], "regular_script_cn": "常规剧本是市场赔率数据缺失，暂时无法对比市场倾向，主队只有倾向。", "high_variance_tail_script_cn": "如果 xG 样本不足，只作为弱参考，同时出现早球，比分可能直接走到 3-0。"})
    if not validate_call(bad_tail_score, policy):
        fail("reverse: weak evidence strong tail score must be rejected")
    market_bundle = {"availability": {"market_ah": "available", "market_ou": "available"}, "market": {"ah_line": "-1", "ah_home_price": 1.9, "ah_away_price": 1.9, "ou_line": "2.5", "over_price": 1.9, "under_price": 1.9}}
    if not validate_call_against_bundle(approved_missing_market_script, market_bundle):
        fail("reverse: AH/OU available but missing-market script must be rejected")
    model_bundle = {
        "availability": {"model_1x2": "available", "market_ah": "missing", "market_ou": "missing"},
        "market": {"model_p_home": 0.47, "model_p_draw": 0.28, "model_p_away": 0.25},
    }
    missing_model_1x2 = dict(base, read={**base["read"], "recommendation_card": {**base["read"]["recommendation_card"], "one_x_two_cn": "1X2 数据缺失，降级观察｜来源：缺失"}})
    if not validate_call_against_bundle(missing_model_1x2, model_bundle):
        fail("reverse: W1 model 1X2 available but missing 1X2 card must be rejected")
    missing_bundle = {"availability": {"market_1x2": "missing", "market_ah": "missing", "market_ou": "missing"}, "market": {}}
    invented_market = dict(base, read={**base["read"], "market_expert_script_cn": "若临场让球盘口保持主队低水，大小球触发看早球。"})
    if not validate_call_against_bundle(invented_market, missing_bundle):
        fail("reverse: all-missing market bundle must reject invented market script")
    betting = dict(base, read={**base["read"], "watch_points_cn": ["稳赢", "主队边路推进"]})
    if not validate_call(betting, policy):
        fail("reverse: forbidden promise term must be caught")
    funds_card = dict(base, read={**base["read"], "recommendation_card": {**base["read"]["recommendation_card"], "main_recommendation_cn": "重仓主线"}})
    if not validate_call(funds_card, policy):
        fail("reverse: recommendation_card funds wording must be caught")
    low_no_observe = dict(base, data_readiness="低", read={**base["read"], "recommendation_card": {**base["read"]["recommendation_card"], "main_recommendation_cn": "主线看主队不败与低比分。", "risk_cn": "若客队先球则主线变化。", "data_status_cn": "数据部分缺失"}})
    if not validate_call(low_no_observe, policy):
        fail("reverse: low data recommendation_card without observation/downgrade must be rejected")
    if not bundle_leak([{"fixture_id": "Z", "asof_pre_kickoff": True, "actual_score": "2-1"}], forbidden_pm):
        fail("reverse: a bundle with actual_score must be caught")
    bad_scout = {"fixture_id": "Z", "asof_pre_kickoff": False, "availability": {"form": "made_up"}}
    if not validate_scout_payload(bad_scout, "reverse_bad_scout", forbidden_pm):
        fail("reverse: bad scout file shape must be catchable")
    if not validate_memory_consistency({"overall": {"n": audit_rows + 1}}, audit_rows):
        fail("reverse: memory n/audit row mismatch must be caught")
    fake_review = [{"fixture_id": "NO_RESULT", "prematch_read_digest": "bad", "honesty_label": "AI 复盘·赛后对照"}]
    if not validate_review_rows(fake_review, locks, finished, policy):
        fail("reverse: review without finished result / digest match must be caught")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"W1 scout check FAIL ({len(errors)})")
        return 1
    print(f"W1 scout check PASS (bundles={len(bundles)}, reads={n_calls}, audit_rows={audit_rows}, no leakage, "
          "structured read contract, memory consistent, no betting/edge wording)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
