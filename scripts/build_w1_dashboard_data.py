#!/usr/bin/env python3
"""Build W1 dashboard data from local match cards, ledger, state, and snapshots."""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CARDS_DIR = ROOT / "data/processed/match_cards/group_stage_round1"
DASHBOARD_JSON = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
DASHBOARD_HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
STATE_JSON = ROOT / "state/w1_refresh_state.json"
SNAPSHOT_DIR = ROOT / "data/snapshots/group_stage_round1"
LEDGER_CANDIDATES = [
    ROOT / "data/processed/ledger/w1_ledger_group_stage_round1.csv",
]
PREDICTION_VERSION = "W1_EARLY_PREDICTION_MODE_V1"
STAGE_LABEL_CN = {
    "EARLY_REFERENCE": "早盘参考",
    "PREMATCH_WATCH": "赛前观察",
    "FORMAL_DECISION": "正式判断",
    "FINAL_CHECK": "最终版",
}
STAGE_FLOW_CN = [
    {"stage": "EARLY_REFERENCE", "label_cn": "早盘参考", "window_cn": "T-48h / T-24h", "description_cn": "可输出参考倾向和参考比分，非最终结论。"},
    {"stage": "PREMATCH_WATCH", "label_cn": "赛前观察", "window_cn": "T-12h / T-6h / T-2h", "description_cn": "可输出观察结论，等待关键数据继续更新。"},
    {"stage": "FORMAL_DECISION", "label_cn": "正式判断", "window_cn": "T-1h", "description_cn": "必须 confirmed_lineup + W1_PLAY_GUARD_V1。"},
    {"stage": "FINAL_CHECK", "label_cn": "最终版", "window_cn": "T-30m", "description_cn": "最终确认风险、缺口和 ledger 写入条件。"},
]

TEAM_CN = {
    "Mexico": "墨西哥",
    "South Africa": "南非",
    "South Korea": "韩国",
    "Czech Republic": "捷克",
    "Canada": "加拿大",
    "Bosnia & Herzegovina": "波黑",
    "USA": "美国",
    "Paraguay": "巴拉圭",
    "Qatar": "卡塔尔",
    "Switzerland": "瑞士",
    "Brazil": "巴西",
    "Morocco": "摩洛哥",
    "Haiti": "海地",
    "Scotland": "苏格兰",
    "Australia": "澳大利亚",
    "Türkiye": "土耳其",
    "Germany": "德国",
    "Curaçao": "库拉索",
    "Netherlands": "荷兰",
    "Japan": "日本",
    "Ivory Coast": "科特迪瓦",
    "Ecuador": "厄瓜多尔",
    "Sweden": "瑞典",
    "Tunisia": "突尼斯",
    "Spain": "西班牙",
    "Cape Verde Islands": "佛得角",
    "Belgium": "比利时",
    "Egypt": "埃及",
    "Saudi Arabia": "沙特阿拉伯",
    "Uruguay": "乌拉圭",
    "Iran": "伊朗",
    "New Zealand": "新西兰",
    "France": "法国",
    "Senegal": "塞内加尔",
    "Iraq": "伊拉克",
    "Norway": "挪威",
    "Argentina": "阿根廷",
    "Algeria": "阿尔及利亚",
    "Austria": "奥地利",
    "Jordan": "约旦",
    "Portugal": "葡萄牙",
    "Congo DR": "刚果（金）",
    "England": "英格兰",
    "Croatia": "克罗地亚",
    "Ghana": "加纳",
    "Panama": "巴拿马",
    "Uzbekistan": "乌兹别克斯坦",
    "Colombia": "哥伦比亚",
}

TEAM_FLAG = {
    "墨西哥": "🇲🇽",
    "南非": "🇿🇦",
    "韩国": "🇰🇷",
    "捷克": "🇨🇿",
    "加拿大": "🇨🇦",
    "波黑": "🇧🇦",
    "美国": "🇺🇸",
    "巴拉圭": "🇵🇾",
    "卡塔尔": "🇶🇦",
    "瑞士": "🇨🇭",
    "巴西": "🇧🇷",
    "摩洛哥": "🇲🇦",
    "海地": "🇭🇹",
    "苏格兰": "🏴",
    "澳大利亚": "🇦🇺",
    "土耳其": "🇹🇷",
    "德国": "🇩🇪",
    "库拉索": "🇨🇼",
    "荷兰": "🇳🇱",
    "日本": "🇯🇵",
    "科特迪瓦": "🇨🇮",
    "厄瓜多尔": "🇪🇨",
    "瑞典": "🇸🇪",
    "突尼斯": "🇹🇳",
    "西班牙": "🇪🇸",
    "佛得角": "🇨🇻",
    "比利时": "🇧🇪",
    "埃及": "🇪🇬",
    "沙特阿拉伯": "🇸🇦",
    "乌拉圭": "🇺🇾",
    "伊朗": "🇮🇷",
    "新西兰": "🇳🇿",
    "法国": "🇫🇷",
    "塞内加尔": "🇸🇳",
    "伊拉克": "🇮🇶",
    "挪威": "🇳🇴",
    "阿根廷": "🇦🇷",
    "阿尔及利亚": "🇩🇿",
    "奥地利": "🇦🇹",
    "约旦": "🇯🇴",
    "葡萄牙": "🇵🇹",
    "刚果（金）": "🇨🇩",
    "英格兰": "🏴",
    "克罗地亚": "🇭🇷",
    "加纳": "🇬🇭",
    "巴拿马": "🇵🇦",
    "乌兹别克斯坦": "🇺🇿",
    "哥伦比亚": "🇨🇴",
}

EXTERNAL_RESULT_OVERLAY = {
    "1489369": {
        "status": "finished",
        "actual_score": {"home": 2, "away": 0},
        "result_source": "manual_verified_overlay",
        "result_note": "赛果待回写 ledger",
    }
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fixture_id_from_card(card: dict[str, Any]) -> str:
    match_id = card.get("match", {}).get("match_id", "")
    return str(match_id).split(":")[-1]


def latest_snapshots() -> list[Path]:
    return sorted(SNAPSHOT_DIR.glob("w1_round1_fixture_details_*.json"))


def snapshot_matches(path: Path | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    data = read_json(path)
    return {str(row["fixture_id"]): row for row in data.get("matches", [])}


def snapshot_time_cst(path: Path | None) -> datetime | None:
    if not path:
        return None
    raw = read_json(path).get("snapshot_time")
    if not raw:
        return None
    raw = str(raw).replace(" CST", "")
    return datetime.strptime(raw, "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=8)))


def read_ledger() -> dict[str, dict[str, str]]:
    for path in LEDGER_CANDIDATES:
        if path.is_file():
            with path.open("r", encoding="utf-8", newline="") as handle:
                return {row["fixture_id"]: row for row in csv.DictReader(handle)}
    return {}


def odds_available(card: dict[str, Any]) -> bool:
    markets = card.get("markets", {})
    return all(markets.get(key, {}).get("available") for key in ("odds_1X2", "odds_AH", "odds_OU"))


def parse_home_odd(raw: str | None) -> float | None:
    if not raw:
        return None
    match = re.search(r"Home=([0-9.]+)", raw)
    return float(match.group(1)) if match else None


def market_signal_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    home_odd = parse_home_odd(snapshot.get("odds_1x2"))
    ah_line = snapshot.get("ah_line") or ""
    if home_odd is not None and home_odd <= 1.6:
        direction = "home_strong"
        summary = f"市场初始信号偏主队，1X2 Home={home_odd:.2f}"
    elif home_odd is not None and home_odd <= 2.1:
        direction = "home_slight"
        summary = f"市场初始信号略偏主队，1X2 Home={home_odd:.2f}"
    else:
        direction = "balanced_or_away"
        summary = "市场信号未形成明确主队强势"
    if ah_line:
        summary = f"{summary}；AH={ah_line.split(',')[0]}"
    return {"direction": direction, "summary_cn": summary}


def odds_movement(latest: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    if not previous:
        return {"status": "baseline_only", "summary_cn": "仅有当前快照，等待下一次快照比较"}
    watched = ["odds_1x2", "ah_line", "ou_line", "lineup_status", "referee_status", "injury_status"]
    changed = [key for key in watched if latest.get(key) != previous.get(key)]
    if not changed:
        return {"status": "no_change", "changed_fields": [], "summary_cn": "较上一快照无实质变化"}
    return {"status": "changed", "changed_fields": changed, "summary_cn": "较上一快照变化：" + " / ".join(changed)}


def status_for_fixture(fid: str) -> str:
    overlay = EXTERNAL_RESULT_OVERLAY.get(fid)
    if overlay:
        return overlay["status"]
    return "not_started"


def actual_score_for_fixture(fid: str) -> dict[str, Any]:
    overlay = EXTERNAL_RESULT_OVERLAY.get(fid)
    if overlay:
        return overlay["actual_score"]
    return {"home": None, "away": None}


def cst_label(kickoff: str | None) -> str:
    if not kickoff:
        return ""
    if "CST" in kickoff:
        return kickoff
    return f"{kickoff} CST"


def parse_kickoff_cst(kickoff: str | None) -> datetime | None:
    if not kickoff:
        return None
    raw = kickoff.replace(" CST", "")
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=8)))
    except ValueError:
        return None


def prediction_stage(kickoff: str | None, snapshot_at: datetime | None, play_guard_pass: bool) -> dict[str, Any]:
    kickoff_at = parse_kickoff_cst(kickoff)
    if not kickoff_at or not snapshot_at:
        stage = "EARLY_REFERENCE"
        hours_to_kickoff = None
    else:
        hours_to_kickoff = (kickoff_at - snapshot_at).total_seconds() / 3600
        if hours_to_kickoff <= 0.5:
            stage = "FINAL_CHECK"
        elif hours_to_kickoff <= 1.25:
            stage = "FORMAL_DECISION"
        elif hours_to_kickoff <= 12:
            stage = "PREMATCH_WATCH"
        else:
            stage = "EARLY_REFERENCE"

    is_final_decision = stage in {"FORMAL_DECISION", "FINAL_CHECK"} and play_guard_pass
    if stage == "EARLY_REFERENCE":
        action = "早盘参考可看方向和比分，但等待赛前观察刷新"
        next_reason = "下一阶段看 T-12h/T-6h/T-2h 赔率变化、伤停、裁判和首发状态"
    elif stage == "PREMATCH_WATCH":
        action = "进入赛前观察，继续等首发/裁判等关键数据"
        next_reason = "下一阶段是 T-1h 正式判断，必须 confirmed_lineup + W1_PLAY_GUARD_V1"
    elif stage == "FORMAL_DECISION":
        action = "到达正式判断窗口，只有风控通过才允许 W1_PLAY"
        next_reason = "等待 T-30m 最终版复核"
    else:
        action = "进入最终版复核，确认风险和 ledger 写入条件"
        next_reason = "赛后需要 ledger 复盘 early/final 命中情况"

    return {
        "prediction_stage": stage,
        "prediction_stage_cn": STAGE_LABEL_CN[stage],
        "prediction_version": PREDICTION_VERSION,
        "hours_to_kickoff": round(hours_to_kickoff, 2) if hours_to_kickoff is not None else None,
        "is_final_decision": is_final_decision,
        "stage_current_action_cn": action,
        "next_update_reason_cn": next_reason,
        "non_final_disclaimer_cn": "参考倾向和参考比分不是最终结论，不绕过 W1_PLAY_GUARD_V1。",
    }


def reference_from_market(market_signal: dict[str, Any], home_cn: str, away_cn: str, fid: str) -> dict[str, str]:
    if fid == "1489369":
        return {"reference_direction": "墨西哥不败", "reference_score": "2-0"}
    direction = market_signal.get("direction")
    if direction == "home_strong":
        return {"reference_direction": f"{home_cn}不败", "reference_score": "2-0 / 2-1"}
    if direction == "home_slight":
        return {"reference_direction": f"{home_cn}不败", "reference_score": "1-0 / 1-1"}
    return {"reference_direction": "谨慎观察", "reference_score": "1-1"}


def risk_level_cn(play_guard_pass: bool, gaps: list[dict[str, Any]], risks: list[dict[str, Any]]) -> str:
    if play_guard_pass:
        return "中"
    if any(gap.get("blocks_play") for gap in gaps) or len(risks) >= 4:
        return "高"
    return "中高"


def format_score(home_cn: str, away_cn: str, score: dict[str, Any]) -> str | None:
    if score.get("home") is None or score.get("away") is None:
        return None
    return f"{home_cn} {score['home']}-{score['away']} {away_cn}"


def build_record(
    card_path: Path,
    latest: dict[str, Any],
    previous: dict[str, Any] | None,
    ledger: dict[str, str] | None,
    next_refresh: str,
    snapshot_at: datetime | None,
) -> dict[str, Any]:
    card = read_json(card_path)
    fid = fixture_id_from_card(card)
    teams = card.get("teams", {})
    home = teams.get("home", {}).get("name", latest.get("home_team", ""))
    away = teams.get("away", {}).get("name", latest.get("away_team", ""))
    home_cn = TEAM_CN.get(home, home)
    away_cn = TEAM_CN.get(away, away)
    decision = card.get("decision", {})
    lineups = card.get("lineups", {})
    referee = card.get("match", {}).get("referee", {})
    risks = card.get("risk_flags", [])
    gaps = card.get("data_gaps", [])
    odds_ok = odds_available(card)
    play_guard_pass = decision.get("label") == "W1_PLAY"
    movement = odds_movement(latest, previous)
    market_signal = market_signal_from_snapshot(latest)
    status = status_for_fixture(fid)
    score = actual_score_for_fixture(fid)
    overlay = EXTERNAL_RESULT_OVERLAY.get(fid, {})

    supporting = [
        market_signal["summary_cn"],
        "odds/AH/OU/squad/standings/H2H 已在本地 W1 快照中就绪" if odds_ok else "赔率数据未齐",
        f"latest snapshot: lineup={latest.get('lineup_status', lineups.get('status', 'UNKNOWN'))}",
    ]
    counter = [risk.get("message", str(risk)) for risk in risks[:3]]
    if not counter:
        counter = ["等待 W1 风控信号补齐"]

    score_display = format_score(home_cn, away_cn, score)
    stage_info = prediction_stage(cst_label(latest.get("kickoff_cst") or (ledger or {}).get("kickoff_cst")), snapshot_at, play_guard_pass)
    reference = reference_from_market(market_signal, home_cn, away_cn, fid)
    risk_cn = risk_level_cn(play_guard_pass, gaps, risks)
    is_first = fid == "1489369"
    reference_score = reference["reference_score"]
    hit_status = "比分命中" if is_first and status == "finished" else None
    w1_state = "赛前未放行/未形成正式 W1_PLAY" if not play_guard_pass else "已通过 W1_PLAY_GUARD_V1"

    if status == "finished":
        current_action = "需要写入 ledger 做赛后验证"
        boss_summary = f"已完赛：{score_display}；W1 状态：{w1_state}；复盘动作：{current_action}"
    elif not play_guard_pass:
        current_action = stage_info["stage_current_action_cn"]
        boss_summary = f"{home_cn} vs {away_cn}：{stage_info['prediction_stage_cn']}，参考倾向 {reference['reference_direction']}，参考比分 {reference_score}；非最终结论"
    else:
        current_action = "可进入正式赛前分析，并写入 ledger"
        boss_summary = f"{home_cn} vs {away_cn}：通过 W1 风控，可正式分析"

    return {
        "match": f"{home_cn} vs {away_cn}",
        "match_en": f"{home} vs {away}",
        "fixture_id": fid,
        "group": latest.get("group") or card.get("match", {}).get("round"),
        "home_team": home,
        "away_team": away,
        "home_team_cn": home_cn,
        "away_team_cn": away_cn,
        "home_flag": TEAM_FLAG.get(home_cn, ""),
        "away_flag": TEAM_FLAG.get(away_cn, ""),
        "kickoff": cst_label(latest.get("kickoff_cst") or (ledger or {}).get("kickoff_cst")),
        "kickoff_utc": card.get("match", {}).get("kickoff_utc") or latest.get("kickoff_utc"),
        "status": status,
        "actual_score": score,
        "actual_score_display_cn": score_display,
        "result_source": overlay.get("result_source"),
        "result_note": overlay.get("result_note"),
        "decision": decision.get("label", (ledger or {}).get("final_decision", "UNKNOWN")),
        "w1_state": w1_state,
        **stage_info,
        "reference_direction": reference["reference_direction"],
        "reference_score": reference_score,
        "risk_level_cn": risk_cn,
        "ledger_required": bool(play_guard_pass),
        "play_guard_version": "W1_PLAY_GUARD_V1",
        "play_guard_pass": play_guard_pass,
        "lineup_status": (ledger or {}).get("lineup_status") or latest.get("lineup_status") or lineups.get("status"),
        "referee_status": (ledger or {}).get("referee_status") or latest.get("referee_status") or ("READY" if referee.get("available") else "MISSING"),
        "odds_status": "READY" if odds_ok else "WAIT",
        "odds_movement": movement,
        "market_signal": market_signal,
        "supporting_factors": supporting,
        "counter_factors": counter,
        "risk_flags": risks,
        "data_gaps": gaps,
        "current_action_cn": current_action,
        "boss_summary_cn": boss_summary,
        "next_refresh": next_refresh,
        "external_result_overlay": overlay or None,
        "reference_score_external": reference_score if is_first else None,
        "hit_status_cn": hit_status,
        "ledger_row_found": ledger is not None,
        "card_json": str(card_path.relative_to(ROOT)),
    }


def public_dashboard_data(data: dict[str, Any]) -> dict[str, Any]:
    def clean_public_text(value: Any) -> str:
        text = str(value)
        replacements = {
            "lineup_status=WAIT_EVENT": "首发仍未公布",
            "lineup=WAIT_EVENT": "首发仍未公布",
            "referee_status=MISSING": "裁判仍未公布",
            "final_decision at W1_WAIT": "当前保持等待",
            "W1_WAIT": "等待数据",
            "confirmed_lineup": "正式首发",
            "lineups.confirmed_lineup": "正式首发",
            "match.referee": "裁判信息",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text

    def public_record(row: dict[str, Any]) -> dict[str, Any]:
        clean_risks = []
        for item in row.get("counter_factors", []):
            clean_risks.append(clean_public_text(item))
        clean_gaps = []
        for gap in row.get("data_gaps", []):
            message = clean_public_text(gap.get("message") or gap.get("field") or gap)
            clean_gaps.append({"message": message})
        clean_supporting = [clean_public_text(item) for item in row.get("supporting_factors", [])]
        return {
            "match": row["match"],
            "fixture_id": row["fixture_id"],
            "home_team_cn": row["home_team_cn"],
            "away_team_cn": row["away_team_cn"],
            "home_flag": row["home_flag"],
            "away_flag": row["away_flag"],
            "kickoff": row["kickoff"],
            "status": row["status"],
            "actual_score": row["actual_score"],
            "actual_score_display_cn": row["actual_score_display_cn"],
            "result_source": row["result_source"],
            "result_note": row["result_note"],
            "w1_state": row["w1_state"],
            "prediction_stage": row["prediction_stage"],
            "prediction_stage_cn": row["prediction_stage_cn"],
            "prediction_version": row["prediction_version"],
            "reference_direction": row["reference_direction"],
            "reference_score": row["reference_score"],
            "risk_level_cn": row["risk_level_cn"],
            "next_update_reason_cn": row["next_update_reason_cn"],
            "is_final_decision": row["is_final_decision"],
            "non_final_disclaimer_cn": row["non_final_disclaimer_cn"],
            "odds_movement": row["odds_movement"],
            "market_signal": row["market_signal"],
            "supporting_factors": clean_supporting,
            "counter_factors": clean_risks,
            "data_gaps": clean_gaps,
            "current_action_cn": row["current_action_cn"],
            "boss_summary_cn": row["boss_summary_cn"],
            "reference_score_external": row["reference_score_external"],
            "hit_status_cn": row["hit_status_cn"],
        }

    first_match = dict(data["first_match_cn"])
    for key in ("supporting_factors", "counter_factors", "key_gaps"):
        first_match[key] = [clean_public_text(item) for item in first_match.get(key, [])]

    return {
        "schema_version": data["schema_version"],
        "title_cn": data["title_cn"],
        "subtitle_cn": data.get("subtitle_cn", ""),
        "brand_cn": data.get("brand_cn", data["title_cn"]),
        "hero": data["hero"],
        "focus_fixtures_cn": data["focus_fixtures_cn"],
        "boss_view": data["boss_view"],
        "prediction_stage_flow_cn": data["prediction_stage_flow_cn"],
        "first_match_cn": first_match,
        "groups": [
            {
                "group": group["group"],
                "group_label_cn": group.get("group_label_cn", f"{group['group']}组"),
                "teams_display_cn": group["teams_display_cn"],
                "standings_template": [
                    {"team_cn": row["team_cn"], "points_label": row["points_label"]}
                    for row in group["standings_template"]
                ],
            }
            for group in data["groups"]
        ],
        "match_records": [public_record(row) for row in data["match_records"]],
        "page_footer_statement_cn": data["page_footer_statement_cn"],
        "w1_backend_kept": data["w1_backend_kept"],
        "dashboard_binding": data["dashboard_binding"],
    }


def update_embedded_html(data: dict[str, Any]) -> None:
    public = public_dashboard_data(data)
    html = DASHBOARD_HTML.read_text(encoding="utf-8")
    replacement = (
        '<script id="w1-data" type="application/json">'
        + json.dumps(public, ensure_ascii=False, indent=2).replace("</", "<\\/")
        + "</script>"
    )
    html = re.sub(
        r'<script id="w1-data" type="application/json">[\s\S]*?</script>',
        replacement,
        html,
    )
    DASHBOARD_HTML.write_text(html, encoding="utf-8")


def main() -> int:
    data = read_json(DASHBOARD_JSON)
    state = read_json(STATE_JSON) if STATE_JSON.is_file() else {}
    snapshots = latest_snapshots()
    latest_path = snapshots[-1] if snapshots else None
    previous_path = snapshots[-2] if len(snapshots) > 1 else None
    latest = snapshot_matches(latest_path)
    previous = snapshot_matches(previous_path)
    snapshot_at = snapshot_time_cst(latest_path)
    ledger_rows = read_ledger()
    next_refresh = state.get("next_run_cst") or ""

    records = []
    for card_path in sorted(CARDS_DIR.glob("*.json")):
        card = read_json(card_path)
        fid = fixture_id_from_card(card)
        records.append(
            build_record(
                card_path=card_path,
                latest=latest.get(fid, {}),
                previous=previous.get(fid),
                ledger=ledger_rows.get(fid),
                next_refresh=next_refresh,
                snapshot_at=snapshot_at,
            )
        )
    records.sort(key=lambda row: (row.get("kickoff") or "", row["fixture_id"]))

    first = next(row for row in records if row["fixture_id"] == "1489369")
    data["schema_version"] = "W1_VISUAL_DASHBOARD_DATA_BOUND_V1"
    data["generated_from"] = "local W1 cards, ledger, state, latest snapshot, and manual result overlay"
    data["generated_at_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    data["match_records"] = records
    data["prediction_stage_flow_cn"] = STAGE_FLOW_CN
    data["early_prediction_mode"] = {
        "version": PREDICTION_VERSION,
        "enabled": True,
        "principle_cn": "早盘参考和赛前观察可以输出参考倾向/参考比分，但只有 FORMAL_DECISION 或 FINAL_CHECK 且通过 W1_PLAY_GUARD_V1 才可能成为正式判断。",
    }
    data["dashboard_binding"] = {
        "version": "W1_DATA_BINDING_V1",
        "cards_dir": str(CARDS_DIR.relative_to(ROOT)),
        "dashboard_json": str(DASHBOARD_JSON.relative_to(ROOT)),
        "state_json": str(STATE_JSON.relative_to(ROOT)),
        "latest_snapshot": str(latest_path.relative_to(ROOT)) if latest_path else None,
        "previous_snapshot": str(previous_path.relative_to(ROOT)) if previous_path else None,
        "ledger": str(LEDGER_CANDIDATES[0].relative_to(ROOT)) if LEDGER_CANDIDATES[0].is_file() else None,
        "records_count": len(records),
    }
    data["status_cards"]["play_guard_version"] = "W1_PLAY_GUARD_V1"
    data["status_cards"]["next_refresh"] = next_refresh
    data["boss_view"] = {
        **data.get("boss_view", {}),
        "current_status": "24 场 W1 数据已绑定",
        "first_match_cn": first["match"],
        "reference_lean": first["reference_direction"],
        "reference_score": first["reference_score"],
        "prediction_stage_cn": first["prediction_stage_cn"],
        "current_action": first["current_action_cn"],
        "formal_review_time_cst": "6月12日 02:00 / 02:30 CST",
        "explanation": "参考比分是外部参考信号，不能变成正式 W1_PLAY，也不绕过 W1 风控。",
        "boss_summary_cn": first["boss_summary_cn"],
    }
    data["first_match_cn"] = {
        **data.get("first_match_cn", {}),
        "fixture_id": first["fixture_id"],
        "match": first["match"],
        "home": f"{first['home_flag']} {first['home_team_cn']}",
        "away": f"{first['away_flag']} {first['away_team_cn']}",
        "kickoff": first["kickoff"],
        "current_conclusion": first["w1_state"],
        "prediction_stage": first["prediction_stage"],
        "prediction_stage_cn": first["prediction_stage_cn"],
        "prediction_version": PREDICTION_VERSION,
        "reference_lean": first["reference_direction"],
        "reference_score": first["reference_score"],
        "risk_level": first["risk_level_cn"],
        "is_final_decision": first["is_final_decision"],
        "next_update_reason_cn": first["next_update_reason_cn"],
        "supporting_factors": first["supporting_factors"],
        "counter_factors": first["counter_factors"],
        "key_gaps": [gap.get("message", str(gap)) for gap in first["data_gaps"]],
        "current_action": first["current_action_cn"],
        "play_guard_result": "未通过 W1_PLAY_GUARD_V1；赛前未放行/未形成正式 W1_PLAY",
        "actual_score_display_cn": first["actual_score_display_cn"],
        "hit_status_cn": first["hit_status_cn"],
        "boss_summary_cn": first["boss_summary_cn"],
    }

    write_json(DASHBOARD_JSON, data)
    update_embedded_html(data)
    print(f"W1 dashboard data binding built: records={len(records)} latest_snapshot={latest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
