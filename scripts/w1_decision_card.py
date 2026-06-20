#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build display-only decision cards from Scout policy_result.

The decision card is a protocol lock: policy_result is the only decision source.
This module formats the policy into a human-readable card, but it does not
change thresholds, probabilities, calibration, score engine output, or Primary
Read logic.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "w1_decision_card_v1"
REASON_LABELS = ("盘口结构", "模型优势", "路径一致性")
OPTIONAL_REASON_LABELS = ("盘口变化",)
FORBIDDEN_GENERAL = ("重仓", "梭哈", "倍投", "加仓", "稳赚", "必红", "包中", "必穿", "保证命中", "资金建议", "稳胆", "稳赢")
FORBIDDEN_NON_RECOMMEND = ("主推", "强推", "重点推荐", "可作为主方向", "正式推荐", "AI亚盘推荐：", "亚盘推荐：")


def _s(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _pct(value: Any) -> str:
    n = _num(value)
    if n is None:
        return "缺失"
    return f"{n * 100:.1f}".rstrip("0").rstrip(".") + "%"


def _edge_points(value: Any) -> str:
    n = _num(value)
    if n is None:
        return "缺失"
    return f"{n * 100:.1f}".rstrip("0").rstrip(".") + "个百分点"


def _confidence_from_grade(grade: str, decision: str) -> str:
    if decision == "PASS":
        return "低"
    if decision == "OBSERVE" or grade == "B":
        return "观察"
    return {
        "A": "高",
        "A-": "中高",
        "B+": "中",
    }.get(grade, "中")


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _policy(call: dict) -> dict:
    policy = call.get("policy_result")
    return policy if isinstance(policy, dict) else {}


def _read(call: dict) -> dict:
    read = call.get("read")
    return read if isinstance(read, dict) else {}


def _ah(call: dict) -> dict:
    card = _read(call).get("asian_handicap_card")
    return card if isinstance(card, dict) else {}


def _rec_text(call: dict) -> dict:
    text = _read(call).get("recommendation_text")
    return text if isinstance(text, dict) else {}


def _score_path(call: dict, visible: bool) -> dict:
    ah = _ah(call)
    text = _rec_text(call)
    primary = _s(ah.get("score_main_cn"))
    alternates = [_s(x) for x in _s(ah.get("score_backup_cn")).replace("、", "/").split("/") if _s(x)]
    risk = ""
    score_text = _s(text.get("score_recommendation_cn"))
    if "风险：" in score_text:
        risk = _s(score_text.split("风险：", 1)[1].split("；", 1)[0])
    if not primary:
        primary = "待确认"
    return {
        "primary": primary,
        "alternates": alternates[:3],
        "risk": risk or "待确认",
        "visible": bool(visible),
    }


def _line_text(policy: dict) -> str:
    market = policy.get("market") if isinstance(policy.get("market"), dict) else {}
    line = market.get("selected_handicap")
    price = market.get("selected_price")
    line_num = _num(line)
    price_num = _num(price)
    line_cn = "未提供" if line_num is None else f"{line_num:+.2f}".rstrip("0").rstrip(".")
    price_cn = "未提供" if price_num is None else f"{price_num:.2f}".rstrip("0").rstrip(".")
    return f"盘口 {line_cn}，水位 {price_cn}"


def _score_path_text(call: dict) -> str:
    score = _score_path(call, True)
    alternates = " / ".join(score["alternates"]) if score["alternates"] else "待确认"
    return f"主路径 {score['primary']}，备选 {alternates}，风险 {score['risk']}"


def _movement_text(policy: dict) -> str:
    movement = policy.get("movement") if isinstance(policy.get("movement"), dict) else {}
    snapshots = policy.get("snapshots") if isinstance(policy.get("snapshots"), dict) else {}
    history = policy.get("movement_history_status") if isinstance(policy.get("movement_history_status"), dict) else {}
    flags = _list(policy.get("movement_flags"))
    line_delta = movement.get("line_delta", "未提供")
    price_delta = movement.get("price_delta", "未提供")
    used = snapshots.get("snapshots_used")
    source = snapshots.get("snapshots_source") or "未提供"
    visible_flags = ["历史盘口时间序列不足" if _s(x) in {"stale_or_missing_snapshots", "movement_history_insufficient"} else _s(x) for x in flags if _s(x)]
    flag_text = " / ".join(dict.fromkeys(visible_flags)) or "无强反向标记"
    history_text = ""
    if history:
        history_text = f" movement_history={history.get('movement_history_status', 'unknown')}，snapshot_type={history.get('snapshot_type', 'unknown')}。"
    return f"盘口变化：line_delta={line_delta}，price_delta={price_delta}，snapshots_used={used if used is not None else '未提供'}，source={source}，flags={flag_text}。{history_text}"


def _recommend_core(policy: dict, call: dict) -> str:
    pick = _s(policy.get("main_ah_pick") or policy.get("candidate_ah_pick"), "候选方向")
    prob = policy.get("probability") if isinstance(policy.get("probability"), dict) else {}
    grade_caps = _list(policy.get("grade_caps_applied"))
    calibration = policy.get("calibration") if isinstance(policy.get("calibration"), dict) else {}
    cal = _s(prob.get("calibration_status") or calibration.get("status"), "untrained")
    history = policy.get("movement_history_status") if isinstance(policy.get("movement_history_status"), dict) else {}
    history_cap = "；当前盘口可用，但历史盘口时间序列不足，movement 维度不加分" if history.get("movement_history_status") == "insufficient" else ""
    cap_text = "；校准未训练，等级按规则受限" if cal == "untrained" or grade_caps else ""
    return (
        f"{pick} 具备盘口保护，W1覆盖率 {_pct(prob.get('cover_prob_calibrated') if prob.get('cover_prob_calibrated') is not None else prob.get('cover_prob_raw'))}"
        f" 高于市场公平概率 {_pct(prob.get('market_prob_fair'))}，edge={_edge_points(prob.get('edge_calibrated') if prob.get('edge_calibrated') is not None else prob.get('edge_raw'))}。"
        f"{_score_path_text(call)} 支持当前受让/让球方向进入推荐池{history_cap}{cap_text}。"
    )


def _policy_snapshot(policy: dict) -> dict:
    prob = policy.get("probability") if isinstance(policy.get("probability"), dict) else {}
    cal = policy.get("calibration") if isinstance(policy.get("calibration"), dict) else {}
    return {
        "edge_raw": prob.get("edge_raw"),
        "edge_calibrated": prob.get("edge_calibrated"),
        "market_prob_fair": prob.get("market_prob_fair"),
        "market_prob_method": prob.get("market_prob_method"),
        "overround": prob.get("overround"),
        "calibration_status": prob.get("calibration_status") or cal.get("status"),
        "hard_gates_passed": not bool(policy.get("failed_gates")),
        "hard_gates": deepcopy(policy.get("hard_gates") or {}),
        "failed_gates": deepcopy(policy.get("failed_gates") or []),
        "movement_flags": deepcopy(policy.get("movement_flags") or []),
        "conflict_flags": deepcopy(policy.get("conflict_flags") or []),
        "grade_caps_applied": deepcopy(policy.get("grade_caps_applied") or []),
        "calibration": deepcopy(cal),
    }


def _calibration_cn(policy: dict) -> str:
    status = (_policy_snapshot(policy).get("calibration_status") or "untrained")
    if status == "untrained":
        return "未训练"
    return str(status)


def _pass_reason_items(policy: dict) -> list[str]:
    rows: list[str] = []
    gates = policy.get("hard_gates") if isinstance(policy.get("hard_gates"), dict) else {}
    prob = policy.get("probability") if isinstance(policy.get("probability"), dict) else {}
    failed = _list(policy.get("failed_gates"))
    if policy.get("pass_reason"):
        rows.append(_s(policy.get("pass_reason")))
    if "missing_score_matrix" in failed:
        rows.append("W1 score matrix 缺失，无法计算 AH 覆盖概率。")
        rows.append("当前不形成可验证放行条件，需等待 score matrix 生成或重新同步 fixture。")
    if "missing_market_fair_probability" in failed:
        rows.append("AH 盘口存在，但两边价格不足，market fair probability 未能计算。")
        rows.append("需重新抓取完整 AH home/away price。")
    if "edge_below_threshold" in failed:
        edge = prob.get("edge_calibrated") if prob.get("edge_calibrated") is not None else prob.get("edge_raw")
        rows.append(f"AH 数据可用，但 edge={_edge_points(edge)}，未达到 1.5pp 最低门槛。")
        rows.append("当前为价值不足，不是盘口缺失。")
    if "invalid_ah_sign" in failed:
        rows.append("AH 盘口符号异常，主队让球/客队受让方向不可信。")
    if "missing_ah" in failed:
        rows.append("AH 盘口缺失，无法形成亚盘放行条件。")
    if "missing_price" in failed:
        rows.append("AH 两边价格缺失或非法，无法计算市场公平概率。")
    if failed:
        rows.append("未通过风控门槛：" + " / ".join(_s(x) for x in failed if _s(x)))
    if gates.get("has_ah") is True and "missing_ah" in failed:
        rows.append("系统检测到 AH 字段可用，盘口缺失不得作为本场主原因；请复核解析链路。")
    severity = _s(policy.get("gate_severity"))
    if severity and severity != "none":
        rows.append(f"门槛严重度={severity}，Policy Engine 未放行。")
    if _list(policy.get("conflict_flags")):
        rows.append("冲突标记：" + " / ".join(_s(x) for x in policy.get("conflict_flags")))
    if _list(policy.get("movement_flags")):
        rows.append("盘口变化标记：" + " / ".join(_s(x) for x in policy.get("movement_flags")))
    cal = policy.get("calibration") if isinstance(policy.get("calibration"), dict) else {}
    if cal.get("reason"):
        rows.append(_s(cal.get("reason")))
    if prob.get("edge_raw") is not None or prob.get("edge_calibrated") is not None:
        rows.append(f"edge_raw={prob.get('edge_raw')}，edge_calibrated={prob.get('edge_calibrated')}。")
    return rows or ["Policy Engine 缺少可展示的具体风控字段；请复核 policy_result / failed_gates。"]


def _reason_blocks_for_recommend(policy: dict, call: dict) -> list[dict]:
    pick = _s(policy.get("main_ah_pick") or policy.get("candidate_ah_pick"), "候选方向")
    prob = policy.get("probability") if isinstance(policy.get("probability"), dict) else {}
    movement = _s(policy.get("movement_summary_cn"), "盘口变化未触发反向风险。")
    history = policy.get("movement_history_status") if isinstance(policy.get("movement_history_status"), dict) else {}
    market_status = policy.get("market_data_status") if isinstance(policy.get("market_data_status"), dict) else {}
    if history.get("movement_history_status") == "insufficient":
        current_status = "当前盘口可用" if market_status.get("has_current_ah") else "当前 AH 盘口不可用"
        movement = (
            f"{current_status}；但历史盘口时间序列不足，暂无法验证早盘到临场是否有退盘/升水，"
            "因此 movement 维度不加分，等级上限受限为 B+。"
        )
    score = _score_path(call, True)
    score_text = " / ".join([score["primary"], *score["alternates"]]).strip(" /") or "比分路径待确认"
    rows = [
        {"label": "盘口结构", "text": f"{pick}：{_line_text(policy)}，当前方向具备盘口保护；{movement}"},
        {"label": "模型优势", "text": f"W1覆盖率 {_pct(prob.get('cover_prob_calibrated') if prob.get('cover_prob_calibrated') is not None else prob.get('cover_prob_raw'))} vs 市场公平概率 {_pct(prob.get('market_prob_fair'))}，edge_raw={prob.get('edge_raw', '未提供')}，edge_calibrated={prob.get('edge_calibrated', '未提供')}，对应{_s(policy.get('recommendation_grade'), '推荐')}区间。"},
        {"label": "路径一致性", "text": f"比分路径集中在 {score_text}，风险比分 {score['risk']}，服务当前亚盘方向。"},
    ]
    snapshots = policy.get("snapshots") if isinstance(policy.get("snapshots"), dict) else {}
    if snapshots or policy.get("movement") or policy.get("movement_flags") or policy.get("grade_caps_applied"):
        rows.append({"label": "盘口变化", "text": _movement_text(policy) + (" 等级封顶：" + " / ".join(_s(x) for x in _list(policy.get("grade_caps_applied")) if _s(x)) if _list(policy.get("grade_caps_applied")) else "")})
    return rows


def _observe_reason_blocks(policy: dict, call: dict) -> list[dict]:
    prob = policy.get("probability") if isinstance(policy.get("probability"), dict) else {}
    return [
        {"label": "盘口结构", "text": "候选方向尚可观察，但盘口稳定性或保护力度不足。"},
        {"label": "模型优势", "text": f"edge={_edge_points(prob.get('edge_calibrated') if prob.get('edge_calibrated') is not None else prob.get('edge_raw'))}，不足以进入放行区间。"},
        {"label": "路径一致性", "text": "比分路径部分支持候选方向，但集中度不够。"},
    ]


def _pass_reason_blocks(policy: dict, call: dict) -> list[dict]:
    reasons = _pass_reason_items(policy)
    return [
        {"label": "盘口结构", "text": reasons[0] if len(reasons) > 0 else "盘口结构未形成稳定保护。"},
        {"label": "模型优势", "text": reasons[1] if len(reasons) > 1 else "edge 或市场公平概率不足，未达到放行条件。"},
        {"label": "路径一致性", "text": reasons[2] if len(reasons) > 2 else "比分矩阵与盘口方向未形成同一结论。"},
    ]


def _invalidation(policy: dict, call: dict) -> list[str]:
    rows = [_s(x) for x in _list(policy.get("reassess_triggers")) if _s(x)]
    text_rows = [_s(x) for x in _list(_rec_text(call).get("live_invalidation_cn")) if _s(x)]
    rows.extend(text_rows)
    while len(rows) < 3:
        rows.append(["盘口退盘或候选方向水位明显升高。", "关键首发或后腰防线信息出现反向变化。", "早球改变比赛节奏，原路径降权。"][len(rows)])
    return rows[:4]


def _recommend_invalidation(policy: dict, call: dict) -> list[str]:
    rows = _invalidation(policy, call)
    cleaned: list[str] = []
    for row in rows:
        text = row.replace("降级为 PASS / 观察", "方向失效并需重新评估")
        text = text.replace("降级为PASS", "方向失效")
        text = text.replace("降级为 PASS", "方向失效")
        text = text.replace("转 PASS", "转为重新评估")
        text = text.replace("PASS / 观察", "重新评估")
        text = text.replace("降级观察", "重新评估")
        text = text.replace("降级为观察", "重新评估")
        cleaned.append(text)
    return cleaned[:4]


def _reassess(policy: dict) -> list[str]:
    rows = [_s(x) for x in _list(policy.get("reassess_triggers")) if _s(x)]
    while len(rows) < 3:
        rows.append(["edge 重新回到推荐阈值以上。", "盘口恢复稳定，候选方向不再升水。", "首发确认后未出现关键位置反向变化。"][len(rows)])
    return rows[:4]


def build_decision_card(scout_call: dict) -> dict:
    policy = _policy(scout_call)
    decision = _s(policy.get("decision_state"), "PASS")
    grade = _s(policy.get("recommendation_grade"), "PASS")
    fixture_id = _s(scout_call.get("fixture_id"))
    stage_id = _s(scout_call.get("stage_id"))
    candidate = _s(policy.get("candidate_ah_pick"))
    main_pick = _s(policy.get("main_ah_pick"))
    cal = _calibration_cn(policy)
    text = _rec_text(scout_call)
    ah = _ah(scout_call)

    base = {
        "schema_version": SCHEMA_VERSION,
        "fixture_id": fixture_id,
        "stage_id": stage_id,
        "decision_state": decision,
        "recommendation_grade": grade,
        "main_pick_cn": "",
        "candidate_pick_cn": candidate,
        "policy_snapshot": _policy_snapshot(policy),
    }

    if decision == "RECOMMEND":
        base.update({
            "card_type": "RECOMMEND_CARD",
            "headline_cn": f"AI亚盘决策：RECOMMEND｜{main_pick}",
            "subheadline_cn": f"等级：{grade}｜信心：{_confidence_from_grade(grade, decision)}｜校准状态：{cal}",
            "main_pick_cn": main_pick,
            "one_line_verdict_cn": _recommend_core(policy, scout_call),
            "reason_blocks_cn": _reason_blocks_for_recommend(policy, scout_call),
            "score_path_cn": _score_path(scout_call, True),
            "ou_aux_cn": _s(text.get("ou_aux_cn") or ah.get("ou_pick_cn"), "大小球仅作辅助判断。"),
            "invalidation_conditions_cn": _recommend_invalidation(policy, scout_call),
            "action_status_cn": "当前可进入 B+ 推荐池；当前盘口可用，但缺少完整盘口时间序列，需临场复核退盘/升水。" if (policy.get("movement_history_status") or {}).get("movement_history_status") == "insufficient" else "当前可进入推荐池，但仍需临场盘口确认。",
            "display_rules": {"show_as_main_pick": True, "show_score_path": True, "show_reassess_triggers": False, "show_failed_gates": False},
        })
    elif decision == "OBSERVE":
        base.update({
            "card_type": "OBSERVE_CARD",
            "headline_cn": f"AI亚盘决策：OBSERVE｜{candidate or '候选待确认'}（候选）",
            "subheadline_cn": f"等级：{grade or 'B'}｜信心：观察｜校准状态：{cal}",
            "one_line_verdict_cn": _s(policy.get("observe_reason"), "当前方向有轻微信号，但不足以进入放行区间，需等待盘口和阵容进一步确认。"),
            "reason_blocks_cn": _observe_reason_blocks(policy, scout_call),
            "score_path_cn": _score_path(scout_call, False),
            "ou_aux_cn": _s(text.get("ou_aux_cn") or ah.get("ou_pick_cn"), "大小球仅作辅助判断。"),
            "upgrade_conditions_cn": _reassess(policy),
            "downgrade_conditions_cn": _invalidation(policy, scout_call),
            "invalidation_conditions_cn": _invalidation(policy, scout_call),
            "action_status_cn": "观察候选，不进入推荐池。",
            "display_rules": {"show_as_main_pick": False, "show_score_path": False, "show_reassess_triggers": True, "show_failed_gates": False},
        })
    else:
        reasons = _pass_reason_items(policy)
        base.update({
            "card_type": "PASS_CARD",
            "decision_state": "PASS",
            "recommendation_grade": "PASS",
            "headline_cn": "AI亚盘决策：PASS｜无推荐",
            "subheadline_cn": f"等级：PASS｜信心：低｜校准状态：{cal}",
            "candidate_pick_cn": candidate,
            "one_line_verdict_cn": reasons[0] if reasons else "当前盘口没有形成可推荐优势，系统主动过滤本场亚盘方向。",
            "reason_blocks_cn": _pass_reason_blocks(policy, scout_call),
            "score_path_cn": _score_path(scout_call, False),
            "ou_aux_cn": _s(text.get("ou_aux_cn") or ah.get("ou_pick_cn"), "大小球仅作辅助判断。"),
            "invalidation_conditions_cn": _reassess(policy),
            "pass_reason_blocks_cn": _pass_reason_blocks(policy, scout_call),
            "main_conflict_cn": "模型方向、盘口结构和比分路径没有形成同一结论。",
            "reassess_triggers_cn": _reassess(policy),
            "risk_note_cn": "本场不进入推荐池。PASS 是主动风控结论，不是数据生成失败。",
            "action_status_cn": "主动过滤，不进入推荐池。",
            "display_rules": {"show_as_main_pick": False, "show_score_path": False, "show_reassess_triggers": True, "show_failed_gates": True},
        })
    return base


def validation_errors(card: dict, policy: dict | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(card, dict):
        return ["card must be object"]
    policy = policy or {}
    decision = _s(card.get("decision_state"))
    grade = _s(card.get("recommendation_grade"))
    text = json.dumps(card, ensure_ascii=False)
    recommend_forbidden = (
        "PASS / 观察",
        "无推荐",
        "不进入推荐池",
        "降级为 PASS",
        "降级为观察",
        "Policy Engine 判定未形成可主推条件",
    )
    if card.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version mismatch")
    if policy:
        if decision != _s(policy.get("decision_state"), "PASS"):
            errors.append("decision_state must match policy_result")
        if grade != _s(policy.get("recommendation_grade"), "PASS"):
            errors.append("recommendation_grade must match policy_result")
    if decision == "RECOMMEND":
        if not card.get("main_pick_cn"):
            errors.append("RECOMMEND missing main_pick_cn")
        if grade not in {"A", "A-", "B+"}:
            errors.append("RECOMMEND grade must be A/A-/B+")
        if len(card.get("reason_blocks_cn") or []) < 3:
            errors.append("RECOMMEND reason_blocks must be at least 3")
        labels = [r.get("label") for r in card.get("reason_blocks_cn") or []]
        for label in REASON_LABELS:
            if label not in labels:
                errors.append(f"RECOMMEND reason label missing: {label}")
        if len(card.get("invalidation_conditions_cn") or []) < 3:
            errors.append("RECOMMEND needs 3 invalidation conditions")
        body_text = json.dumps(
            {
                "headline_cn": card.get("headline_cn"),
                "subheadline_cn": card.get("subheadline_cn"),
                "one_line_verdict_cn": card.get("one_line_verdict_cn"),
                "reason_blocks_cn": card.get("reason_blocks_cn"),
                "score_path_cn": card.get("score_path_cn"),
                "action_status_cn": card.get("action_status_cn"),
            },
            ensure_ascii=False,
        )
        for token in recommend_forbidden:
            if token in body_text:
                errors.append(f"RECOMMEND body contains contradictory token: {token}")
        if grade in {"A-", "B+"} and "信心：低" in _s(card.get("subheadline_cn")):
            errors.append(f"{grade} confidence must not be low")
        if "edge" not in body_text and "覆盖率" not in body_text:
            errors.append("RECOMMEND body must include model edge/coverage evidence")
        if "比分" not in body_text and "score_path" not in body_text:
            errors.append("RECOMMEND body must include score path evidence")
    elif decision == "OBSERVE":
        if card.get("main_pick_cn"):
            errors.append("OBSERVE must not have main_pick_cn")
        if "OBSERVE" not in _s(card.get("headline_cn")) and "观察" not in _s(card.get("headline_cn")):
            errors.append("OBSERVE headline must contain OBSERVE/观察")
        if grade not in {"B", "B+"}:
            errors.append("OBSERVE grade must be B/B+")
        if not card.get("upgrade_conditions_cn") or not card.get("downgrade_conditions_cn"):
            errors.append("OBSERVE needs upgrade/downgrade conditions")
    elif decision == "PASS":
        if card.get("main_pick_cn"):
            errors.append("PASS must not have main_pick_cn")
        if grade != "PASS":
            errors.append("PASS grade must be PASS")
        if "无推荐" not in _s(card.get("headline_cn")):
            errors.append("PASS headline must contain 无推荐")
        if not card.get("pass_reason_blocks_cn"):
            errors.append("PASS needs pass_reason_blocks_cn")
        if not card.get("reassess_triggers_cn"):
            errors.append("PASS needs reassess_triggers_cn")
    else:
        errors.append("invalid decision_state")
    if _s((card.get("policy_snapshot") or {}).get("calibration_status")) == "untrained" and grade == "A":
        errors.append("untrained calibration must not show A")
    if grade == "B" and decision != "OBSERVE":
        errors.append("B must be OBSERVE")
    if policy and policy.get("failed_gates") and decision != "PASS":
        errors.append("failed hard gates must be PASS")
    for token in FORBIDDEN_GENERAL:
        if token in text:
            errors.append(f"forbidden general token: {token}")
    if decision in {"OBSERVE", "PASS"}:
        for token in FORBIDDEN_NON_RECOMMEND:
            if token in text:
                errors.append(f"forbidden non-recommend token: {token}")
        if any(mark in text for mark in ("A-", "B+")):
            errors.append("OBSERVE/PASS must not display A-/B+ strong grades")
    return errors


def assert_valid_decision_card(card: dict, policy: dict | None = None) -> None:
    errors = validation_errors(card, policy)
    if errors:
        raise ValueError("; ".join(errors))


def sample_call(decision: str, grade: str, *, failed: list[str] | None = None, movement: list[str] | None = None, candidate: str = "巴拉圭 +0.5", main: str = "巴拉圭 +0.5") -> dict:
    if decision != "RECOMMEND":
        main = ""
    policy = {
        "decision_state": decision,
        "recommendation_grade": grade,
        "main_ah_pick": main,
        "candidate_ah_pick": candidate,
        "probability": {
            "edge_raw": 0.0617 if decision != "PASS" else 0.006,
            "edge_calibrated": 0.0617 if decision != "PASS" else 0.006,
            "market_prob_fair": 0.5306,
            "market_prob_method": "multiplicative",
            "overround": 0.047,
            "calibration_status": "untrained",
        },
        "calibration": {"status": "untrained", "method": "raw_passthrough", "reason": "样本量不足，当前仅使用 raw passthrough；不声称已完成校准。"},
        "failed_gates": failed or [],
        "movement_flags": movement or [],
        "conflict_flags": [],
        "grade_caps_applied": ["untrained_max_grade"] if decision != "PASS" else [],
        "reassess_triggers": ["edge重新回到推荐阈值以上。", "盘口恢复稳定。", "首发确认无反向变化。"],
        "pass_reason": "edge低于推荐阈值，不足以覆盖市场定价噪声。" if decision == "PASS" else "",
        "observe_reason": "edge处于观察区间，等待盘口确认。" if decision == "OBSERVE" else "",
    }
    return {
        "fixture_id": "SELFTEST",
        "stage_id": "official_1h",
        "policy_result": policy,
        "read": {
            "asian_handicap_card": {
                "score_main_cn": "1-1",
                "score_backup_cn": "0-0 / 1-0",
                "ou_pick_cn": "小2.5仅作辅助判断；若上半场早球，小球方向失效。",
                "ah_confidence_cn": "中高",
            },
            "recommendation_text": {
                "core_judgement_cn": "模型给到受让方向约6.2个百分点优势，且比分路径支持不败保护。",
                "ou_aux_cn": "小2.5仅作辅助判断；若上半场早球，小球方向失效。",
                "live_invalidation_cn": ["候选方向退盘。", "关键首发缺席。", "早球改变节奏。"],
            },
        },
    }


def self_test() -> int:
    samples = [
        sample_call("RECOMMEND", "A-"),
        sample_call("RECOMMEND", "B+"),
        sample_call("OBSERVE", "B"),
        sample_call("PASS", "PASS", failed=["edge_below_threshold"]),
        sample_call("PASS", "PASS", failed=["missing_ah"], candidate=""),
        sample_call("PASS", "PASS", failed=["movement_conflict"], movement=["strong_reverse_movement"]),
    ]
    for row in samples:
        card = build_decision_card(row)
        errors = validation_errors(card, row["policy_result"])
        result = "PASS" if not errors else "FAIL"
        print(
            f"{row['policy_result']['decision_state']} card_type={card.get('card_type')} "
            f"headline={card.get('headline_cn')} main={card.get('main_pick_cn')} "
            f"candidate={card.get('candidate_pick_cn')} reasons={len(card.get('reason_blocks_cn') or [])} checker={result}"
        )
        if errors:
            for err in errors:
                print(f"  - {err}")
            return 1
    print("W1 decision card self-test PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and validate W1 Scout decision cards.")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
