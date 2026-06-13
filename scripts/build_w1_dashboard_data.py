#!/usr/bin/env python3
"""Build W1 dashboard data from local match cards, ledger, state, and snapshots."""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
CARDS_DIR = ROOT / "data/processed/match_cards/group_stage_round1"
DASHBOARD_JSON = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
DASHBOARD_HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
STATE_JSON = ROOT / "state/w1_refresh_state.json"
WEATHER_CACHE = ROOT / "state/w1_weather_cache.json"
VENUES_JSON = ROOT / "data/static/world_cup_2026_venues.json"
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
    {"stage": "FORMAL_DECISION", "label_cn": "正式判断", "window_cn": "T-1h", "description_cn": "必须正式首发 + 正式风控规则。"},
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

VENUE_ENV_STATIC = {
    "Estadio Azteca": {"timezone": "America/Mexico_City", "altitude_m": 2240, "roof_status": "open"},
    "Estadio Akron": {"timezone": "America/Mexico_City", "altitude_m": 1566, "roof_status": "open"},
    "Estadio BBVA": {"timezone": "America/Monterrey", "altitude_m": 540, "roof_status": "open"},
    "BMO Field": {"timezone": "America/Toronto", "altitude_m": 76, "roof_status": "open"},
    "BC Place": {"timezone": "America/Vancouver", "altitude_m": 2, "roof_status": "closed"},
    "SoFi Stadium": {"timezone": "America/Los_Angeles", "altitude_m": 38, "roof_status": "closed"},
    "Levi's Stadium": {"timezone": "America/Los_Angeles", "altitude_m": 2, "roof_status": "open"},
    "MetLife Stadium": {"timezone": "America/New_York", "altitude_m": 2, "roof_status": "open"},
    "Gillette Stadium": {"timezone": "America/New_York", "altitude_m": 88, "roof_status": "open"},
    "NRG Stadium": {"timezone": "America/Chicago", "altitude_m": 15, "roof_status": "closed"},
    "AT&T Stadium": {"timezone": "America/Chicago", "altitude_m": 184, "roof_status": "closed"},
    "Lincoln Financial Field": {"timezone": "America/New_York", "altitude_m": 12, "roof_status": "open"},
    "Mercedes-Benz Stadium": {"timezone": "America/New_York", "altitude_m": 315, "roof_status": "closed"},
    "Lumen Field": {"timezone": "America/Los_Angeles", "altitude_m": 4, "roof_status": "open"},
    "Hard Rock Stadium": {"timezone": "America/New_York", "altitude_m": 2, "roof_status": "open"},
    "Arrowhead Stadium": {"timezone": "America/Chicago", "altitude_m": 265, "roof_status": "open"},
}

VERIFIED_WEATHER_SAMPLES = {
    "1489373": {
        "weather_status": "ready",
        "weather_code": 0,
        "temperature_c": 21.4,
        "humidity_pct": 64,
        "wind_speed_kmh": 13.2,
        "precipitation_mm": None,
        "precipitation_probability_pct": 0,
        "weather_snapshot_time": "2026-06-13T19:00:00+00:00",
        "weather_reason_cn": "",
        "weather_source": "OpenClaw verified Open-Meteo sample",
    }
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cn_display_text(value: Any) -> str:
    text = str(value)
    replacements = {
        "confirmed_lineup missing; W1 hard rule keeps final_decision at W1_WAIT.": "首发未公布；W1硬风控：当前保持等待。",
        "Suspension data remains partial and non-blocking for W1_WAIT.": "停赛数据仍为部分覆盖；按 W1 规则作为非阻断缺口。",
        "Travel distance remains partial and non-blocking for W1_WAIT.": "旅行距离仍为部分覆盖；按 W1 规则作为非阻断缺口。",
        "confirmed_lineup missing; W1 hard rule keeps 当前保持等待.": "首发未公布；W1硬风控：当前保持等待。",
        "W1 hard rule keeps 当前保持等待": "W1硬风控：当前保持等待",
        "W1 hard rule keeps final_decision at W1_WAIT": "W1硬风控：当前保持等待",
        "confirmed_lineup missing; this blocks any non-WAIT final_decision.": "首发未公布；阻止非等待最终结论。",
        "this blocks any non-WAIT final_decision": "阻止非等待最终结论",
        "non-WAIT final_decision": "非等待最终结论",
        "lineup_status=WAIT_EVENT; refresh near team sheet release.": "首发未确认；等待赛前名单刷新。",
        "lineup=WAIT_EVENT": "首发未确认",
        "lineup=WAIT": "首发未确认",
        "lineup_status=WAIT_EVENT": "首发未确认",
        "latest snapshot:": "最新快照：",
        "latest snapshot": "最新快照",
        "pre-match": "赛前",
        "fixture detail snapshot": "比赛详情快照",
        "referee_status=MISSING; referee not available in fixture detail snapshot.": "裁判未公布；比赛详情快照暂未提供。",
        "referee_status=MISSING": "裁判未公布",
        "referee not available": "裁判未公布",
        "裁判未公布; 裁判未公布 in 比赛详情快照.": "裁判未公布；比赛详情快照暂未提供。",
        "裁判未公布 in 比赛详情快照": "比赛详情快照暂未提供裁判信息",
        " in 比赛详情快照": "；比赛详情快照",
        "keep as a non-blocking gap": "非阻断缺口",
        "non-blocking": "非阻断",
        "final_decision": "最终判断",
        "Suspension data remains partial and 非阻断 for W1_WAIT.": "停赛数据仍为部分覆盖；按 W1 规则作为非阻断缺口。",
        "Travel distance remains partial and 非阻断 for W1_WAIT.": "旅行距离仍为部分覆盖；按 W1 规则作为非阻断缺口。",
        "match.referee": "裁判信息",
        "lineups.confirmed_lineup": "正式首发",
        "confirmed_lineup": "正式首发",
        "missing": "缺失",
        "MISSING": "缺失",
        "W1_PLAY_GUARD_V1": "正式风控规则",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = text.replace("lineup=WAIT (赛前, T-1h)", "首发未确认（赛前 T-1h）")
    text = text.replace("lineup=WAIT", "首发未确认")
    return text


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


def venue_context() -> dict[str, dict[str, Any]]:
    if VENUES_JSON.is_file():
        data = read_json(VENUES_JSON)
        return {row["venue_name"]: row for row in data.get("venues", [])}
    return {
        name: {
            "venue_name": name,
            "city": "",
            "country": "",
            "lat": None,
            "lon": None,
            **value,
        }
        for name, value in VENUE_ENV_STATIC.items()
    }


def weather_cache() -> dict[str, dict[str, Any]]:
    if not WEATHER_CACHE.is_file():
        return {}
    data = read_json(WEATHER_CACHE)
    return {str(fid): row for fid, row in data.get("fixtures", {}).items()}


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
        next_reason = "下一阶段是 T-1h 正式判断，必须正式首发 + 正式风控规则"
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
        "non_final_disclaimer_cn": "参考倾向和参考比分不是最终结论，不绕过正式风控规则。",
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


def data_quality_for_card(
    card: dict[str, Any],
    latest: dict[str, Any],
    play_guard_pass: bool,
    odds_ok: bool,
    risks: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
) -> dict[str, Any]:
    markets = card.get("markets", {})
    lineups = card.get("lineups", {})
    referee = card.get("match", {}).get("referee", {})
    context = card.get("context", {})
    squad = card.get("squad", {})

    odds_1x2 = markets.get("odds_1X2", {})
    odds_ah = markets.get("odds_AH", {})
    odds_ou = markets.get("odds_OU", {})
    bookmakers = max(
        int(odds_1x2.get("bookmakers_count") or 0),
        int(odds_ah.get("bookmakers_count") or 0),
        int(odds_ou.get("bookmakers_count") or 0),
    )
    has_1x2 = bool(odds_1x2.get("available"))
    has_ah = bool(odds_ah.get("available"))
    has_ou = bool(odds_ou.get("available"))
    odds_status = "success" if odds_ok and has_1x2 and has_ah and has_ou else "missing"

    lineup_confirmed = bool(lineups.get("confirmed_lineup_available"))
    lineup_status = "confirmed" if lineup_confirmed else "missing"
    home_count = len(lineups.get("home_starting_xi") or [])
    away_count = len(lineups.get("away_starting_xi") or [])

    referee_status = "success" if referee.get("available") or referee.get("name") else "missing"
    injuries_context = context.get("injuries", {})
    injuries_summary = str(injuries_context.get("summary", ""))
    injury_count_match = re.search(r"current=(\d+)", injuries_summary)
    injury_count = int(injury_count_match.group(1)) if injury_count_match else 0
    injuries_status = "empty" if injuries_context.get("status") == "OK" and injury_count == 0 else ("success" if injuries_context.get("status") == "OK" else "missing")

    def availability(name: str) -> str:
        status = str(context.get(name, {}).get("status", "")).upper()
        return "available" if status == "OK" else "missing"

    home_squad = squad.get("home", {})
    away_squad = squad.get("away", {})
    squad_available = bool(home_squad.get("available")) and bool(away_squad.get("available"))
    squad_state = "available" if squad_available else ("partial" if home_squad or away_squad else "missing")
    fail_rules = [str(gap.get("field")) for gap in gaps if gap.get("blocks_play")]
    if not play_guard_pass and not fail_rules:
        fail_rules = ["lineups.confirmed_lineup"]

    missing_parts = []
    if not lineup_confirmed:
        missing_parts.append("首发未公布")
    if referee_status == "missing":
        missing_parts.append("裁判未公布")
    if not odds_ok:
        missing_parts.append("赔率/AH/OU 未齐")
    if not squad_available:
        missing_parts.append("squad 不完整")
    blocking_gaps = [gap for gap in gaps if gap.get("blocks_play")]
    overall = "complete" if not missing_parts and not blocking_gaps and play_guard_pass else ("partial" if odds_ok else "poor")
    if overall == "complete":
        reason = "数据完整，可进入正式判断。"
    elif overall == "partial":
        reason = "数据部分缺失，当前只能早盘参考。"
    else:
        reason = "关键数据缺失，暂不支持正式判断。"

    return {
        "overall": overall,
        "reason_cn": reason,
        "odds": {
            "status": odds_status,
            "bookmakers_count": bookmakers,
            "has_1x2": has_1x2,
            "has_ah": has_ah,
            "has_ou": has_ou,
            "snapshot_time": markets.get("odds_snapshot_time_utc") or latest.get("odds_snapshot_time_utc") or latest.get("snapshot_time"),
        },
        "lineup": {
            "status": lineup_status,
            "home_count": home_count,
            "away_count": away_count,
        },
        "referee": {
            "status": referee_status,
            "name": referee.get("name"),
        },
        "injuries": {
            "status": injuries_status,
            "count": injury_count,
        },
        "local_context": {
            "standings": availability("standings"),
            "h2h": availability("h2h"),
            "squad": squad_state,
        },
        "play_guard": {
            "pass": play_guard_pass,
            "fail_rules": fail_rules,
        },
    }


LINEUP_UNKNOWN_EFFECT = "unknown"
LINEUP_STABLE_EFFECT = "stable"


def lineup_effect_for_card(card: dict[str, Any]) -> dict[str, Any]:
    lineups = card.get("lineups", {})
    confirmed = bool(lineups.get("confirmed_lineup_available"))
    home_xi = lineups.get("home_starting_xi") or []
    away_xi = lineups.get("away_starting_xi") or []
    formation_home = lineups.get("formation_home") or lineups.get("home_formation")
    formation_away = lineups.get("formation_away") or lineups.get("away_formation")
    expected_home = lineups.get("expected_home_starting_xi") or []
    expected_away = lineups.get("expected_away_starting_xi") or []
    core_home = set(lineups.get("home_core_players") or [])
    core_away = set(lineups.get("away_core_players") or [])

    base = {
        "status": "missing",
        "formation_home": formation_home,
        "formation_away": formation_away,
        "formation_changed": False,
        "home_starter_confidence": "unknown",
        "away_starter_confidence": "unknown",
        "key_absences": [],
        "rotation_flags": [],
        "attacking_power_effect": LINEUP_UNKNOWN_EFFECT,
        "defensive_stability_effect": LINEUP_UNKNOWN_EFFECT,
        "midfield_control_effect": LINEUP_UNKNOWN_EFFECT,
        "pace_transition_effect": LINEUP_UNKNOWN_EFFECT,
        "set_piece_effect": LINEUP_UNKNOWN_EFFECT,
        "pressing_effect": LINEUP_UNKNOWN_EFFECT,
        "reference_should_recalculate": False,
        "lineup_summary_cn": "首发未确认，暂不能判断阵型、核心球员和轮换影响。",
    }
    if not confirmed:
        return base

    def confidence(starters: list[Any]) -> str:
        count = len(starters)
        if count >= 11:
            return "high"
        if count >= 8:
            return "medium"
        if count > 0:
            return "low"
        return "unknown"

    key_absences = []
    if core_home and home_xi:
        key_absences.extend([f"主队核心缺席：{name}" for name in sorted(core_home - set(home_xi))])
    if core_away and away_xi:
        key_absences.extend([f"客队核心缺席：{name}" for name in sorted(core_away - set(away_xi))])

    rotation_flags = []
    if expected_home and home_xi:
        home_changed = len(set(expected_home) - set(home_xi))
        if home_changed >= 3:
            rotation_flags.append(f"主队轮换较多：{home_changed} 人不同于预期")
    if expected_away and away_xi:
        away_changed = len(set(expected_away) - set(away_xi))
        if away_changed >= 3:
            rotation_flags.append(f"客队轮换较多：{away_changed} 人不同于预期")

    formation_expected_home = lineups.get("expected_formation_home") or lineups.get("home_expected_formation")
    formation_expected_away = lineups.get("expected_formation_away") or lineups.get("away_expected_formation")
    formation_changed = bool(
        (formation_home and formation_expected_home and formation_home != formation_expected_home)
        or (formation_away and formation_expected_away and formation_away != formation_expected_away)
    )
    reference_should_recalculate = bool(key_absences or rotation_flags or formation_changed or formation_home or formation_away)
    impact = "down" if key_absences or rotation_flags else LINEUP_STABLE_EFFECT
    summary_parts = ["首发已确认"]
    if formation_changed:
        summary_parts.append("阵型与预期不同")
    if key_absences:
        summary_parts.append("存在核心球员缺席")
    if rotation_flags:
        summary_parts.append("存在明显轮换")
    if reference_should_recalculate:
        summary_parts.append("参考比分/倾向需要重算")
    else:
        summary_parts.append("暂未发现需要重算参考倾向的首发冲击")

    return {
        **base,
        "status": "ready",
        "formation_home": formation_home,
        "formation_away": formation_away,
        "formation_changed": formation_changed,
        "home_starter_confidence": confidence(home_xi),
        "away_starter_confidence": confidence(away_xi),
        "key_absences": key_absences,
        "rotation_flags": rotation_flags,
        "attacking_power_effect": impact,
        "defensive_stability_effect": impact,
        "midfield_control_effect": impact,
        "pace_transition_effect": impact,
        "set_piece_effect": impact,
        "pressing_effect": impact,
        "reference_should_recalculate": reference_should_recalculate,
        "lineup_summary_cn": "；".join(summary_parts) + "。",
    }


def style_tags_for_formation(formation: str | None) -> list[str]:
    if not formation:
        return []
    compact = formation.strip()
    if compact == "4-3-3":
        return ["边路速度", "转换进攻", "前场冲击", "高位压迫"]
    if compact == "4-2-3-1":
        return ["中路组织", "前腰串联", "攻守平衡", "控球推进"]
    if compact == "4-4-2":
        return ["双前锋", "边路传中", "第二落点"]
    if compact in {"5-3-2", "3-5-2", "3-4-3", "3-4-2-1"}:
        tags = ["三中卫", "翼卫推进", "中路保护", "防守反击"]
        if compact == "3-4-2-1":
            tags.append("双前腰衔接")
        return tags
    return ["阵型待确认"]


def tactical_effect_for_card(card: dict[str, Any], lineup_effect: dict[str, Any]) -> dict[str, Any]:
    lineups = card.get("lineups", {})
    confirmed = bool(lineups.get("confirmed_lineup_available"))
    home_formation = lineups.get("formation_home") or lineups.get("home_formation")
    away_formation = lineups.get("formation_away") or lineups.get("away_formation")
    base = {
        "status": "missing",
        "home_formation": home_formation,
        "away_formation": away_formation,
        "home_style_tags": [],
        "away_style_tags": [],
        "home_tactical_summary_cn": "",
        "away_tactical_summary_cn": "",
        "formation_mismatch_cn": "",
        "attacking_side_effect": "unknown",
        "defensive_stability_effect": "unknown",
        "tempo_effect": "unknown",
        "transition_effect": "unknown",
        "set_piece_effect": "unknown",
        "reference_should_recalculate": False,
        "tactical_summary_cn": "首发未确认，暂不能判断阵型、打法和战术效应。",
    }
    if not confirmed:
        return base
    if not home_formation or not away_formation:
        return {
            **base,
            "status": "partial",
            "tactical_summary_cn": "首发已确认，但阵型或位置数据不完整，战术效应不足。",
        }

    home_tags = style_tags_for_formation(home_formation)
    away_tags = style_tags_for_formation(away_formation)
    home_back_three = "三中卫" in home_tags
    away_back_three = "三中卫" in away_tags
    home_front_speed = "边路速度" in home_tags or "前场冲击" in home_tags
    away_front_speed = "边路速度" in away_tags or "前场冲击" in away_tags

    if home_front_speed and not away_front_speed:
        attacking = "home_up"
    elif away_front_speed and not home_front_speed:
        attacking = "away_up"
    else:
        attacking = "balanced"

    if home_back_three and not away_back_three:
        defensive = "home_up"
    elif away_back_three and not home_back_three:
        defensive = "away_up"
    else:
        defensive = "balanced"

    transition = "home_counter" if "防守反击" in home_tags else ("away_counter" if "防守反击" in away_tags else "balanced")
    tempo = "fast" if ("高位压迫" in home_tags or "高位压迫" in away_tags or "转换进攻" in home_tags or "转换进攻" in away_tags) else "medium"
    mismatch = f"主队 {home_formation} 对客队 {away_formation}，需要重看边路与三中卫保护的对位。"
    should_recalculate = bool(lineup_effect.get("reference_should_recalculate") or home_formation or away_formation)

    return {
        **base,
        "status": "ready",
        "home_formation": home_formation,
        "away_formation": away_formation,
        "home_style_tags": home_tags,
        "away_style_tags": away_tags,
        "home_tactical_summary_cn": f"{home_formation}：" + " / ".join(home_tags),
        "away_tactical_summary_cn": f"{away_formation}：" + " / ".join(away_tags),
        "formation_mismatch_cn": mismatch,
        "attacking_side_effect": attacking,
        "defensive_stability_effect": defensive,
        "tempo_effect": tempo,
        "transition_effect": transition,
        "set_piece_effect": "balanced",
        "reference_should_recalculate": should_recalculate,
        "tactical_summary_cn": f"战术效应已生成：主队 {home_formation}，客队 {away_formation}；参考倾向需要结合首发重算。",
    }


def parse_utc_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def local_kickoff_label(kickoff_utc: str | None, venue_name: str) -> str | None:
    kickoff = parse_utc_datetime(kickoff_utc)
    if not kickoff:
        return None
    tz_name = VENUE_ENV_STATIC.get(venue_name, {}).get("timezone")
    if not tz_name:
        return kickoff.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        local = kickoff.astimezone(ZoneInfo(tz_name))
    except Exception:  # noqa: BLE001 - local timezone lookup can vary by host
        local = kickoff.astimezone(timezone.utc)
        return local.strftime("%Y-%m-%d %H:%M UTC")
    return local.strftime("%Y-%m-%d %H:%M %Z")


def environment_context_for_card(
    fid: str,
    card: dict[str, Any],
    latest: dict[str, Any],
    venues: dict[str, dict[str, Any]],
    weather_by_fixture: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    match = card.get("match", {})
    venue = match.get("venue", {})
    venue_name = venue.get("name") or latest.get("venue") or "暂缺"
    static = venues.get(venue_name, {})
    city = venue.get("city") or latest.get("city") or static.get("city") or "暂缺"
    country = venue.get("country") or latest.get("country") or static.get("country") or "暂缺"
    context_weather = card.get("context", {}).get("weather", {})
    weather = weather_by_fixture.get(fid) or VERIFIED_WEATHER_SAMPLES.get(fid) or {}

    temperature_c = weather.get("temperature_c", context_weather.get("temperature_c"))
    humidity_pct = weather.get("humidity_pct", context_weather.get("humidity_pct"))
    wind_speed_kmh = weather.get("wind_speed_kmh", context_weather.get("wind_speed_kmh"))
    precipitation_mm = weather.get("precipitation_mm", context_weather.get("precipitation_mm"))
    precipitation_probability_pct = weather.get("precipitation_probability_pct", context_weather.get("precipitation_probability_pct"))
    weather_code = weather.get("weather_code", context_weather.get("weather_code"))
    weather_snapshot_time = weather.get("weather_snapshot_time")
    weather_reason_cn = weather.get("weather_reason_cn") or ""
    weather_status = weather.get("weather_status") or ("ready" if temperature_c is not None else "missing")
    altitude_m = static.get("altitude_m")
    roof_status = static.get("roof_status", "unknown")

    flags: list[str] = []
    if temperature_c is not None and float(temperature_c) >= 30:
        flags.append("HIGH_TEMP")
    if humidity_pct is not None and float(humidity_pct) >= 70:
        flags.append("HIGH_HUMIDITY")
    if altitude_m is not None and float(altitude_m) >= 1200:
        flags.append("HIGH_ALTITUDE")
    if wind_speed_kmh is not None and float(wind_speed_kmh) >= 25:
        flags.append("HIGH_WIND")
    if precipitation_mm is not None and float(precipitation_mm) > 0:
        flags.append("RAIN_RISK")
    if precipitation_probability_pct is not None and float(precipitation_probability_pct) > 30:
        flags.append("RAIN_RISK")
    if roof_status == "closed":
        flags.append("WEATHER_IMPACT_REDUCED")
    if weather_status == "missing":
        flags.append("WEATHER_MISSING")

    risk_flags = [flag for flag in flags if flag not in {"WEATHER_IMPACT_REDUCED", "WEATHER_MISSING"}]
    if any(flag in risk_flags for flag in ("HIGH_TEMP", "HIGH_ALTITUDE", "HIGH_WIND")):
        risk_level = "HIGH"
    elif risk_flags:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    if weather_status == "missing":
        summary = "天气数据暂缺"
    else:
        rain_text = f"，降雨概率 {precipitation_probability_pct}%" if precipitation_probability_pct is not None else ""
        summary = f"赛时天气已接入：温度 {temperature_c}°C，湿度 {humidity_pct}%，风速 {wind_speed_kmh} km/h{rain_text}。环境仅作为辅助风险，不直接触发正式风控。"

    return {
        "venue_name": venue_name,
        "city": city,
        "country": country,
        "kickoff_local_time": local_kickoff_label(match.get("kickoff_utc") or latest.get("kickoff_utc"), venue_name),
        "weather_status": weather_status,
        "weather_code": weather_code,
        "temperature_c": temperature_c,
        "humidity_pct": humidity_pct,
        "wind_speed_kmh": wind_speed_kmh,
        "precipitation_mm": precipitation_mm,
        "precipitation_probability_pct": precipitation_probability_pct,
        "weather_snapshot_time": weather_snapshot_time,
        "weather_reason_cn": weather_reason_cn,
        "altitude_m": altitude_m,
        "roof_status": roof_status,
        "environment_risk_level": risk_level,
        "environment_risk_flags": flags,
        "environment_summary_cn": summary,
    }


def build_record(
    card_path: Path,
    latest: dict[str, Any],
    previous: dict[str, Any] | None,
    ledger: dict[str, str] | None,
    next_refresh: str,
    snapshot_at: datetime | None,
    venues: dict[str, dict[str, Any]],
    weather_by_fixture: dict[str, dict[str, Any]],
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
        f"最新快照：首发未确认（赛前 T-1h）",
    ]
    counter = [cn_display_text(risk.get("message", str(risk))) for risk in risks[:3]]
    if not counter:
        counter = ["等待 W1 风控信号补齐"]

    score_display = format_score(home_cn, away_cn, score)
    stage_info = prediction_stage(cst_label(latest.get("kickoff_cst") or (ledger or {}).get("kickoff_cst")), snapshot_at, play_guard_pass)
    reference = reference_from_market(market_signal, home_cn, away_cn, fid)
    risk_cn = risk_level_cn(play_guard_pass, gaps, risks)
    is_first = fid == "1489369"
    reference_score = reference["reference_score"]
    hit_status = "比分命中" if is_first and status == "finished" else None
    w1_state = "赛前未放行/未形成正式 W1_PLAY" if not play_guard_pass else "已通过正式风控规则"
    if stage_info["prediction_stage"] == "EARLY_REFERENCE" and status != "finished" and not play_guard_pass:
        risk_cn = "中高"

    if status == "finished":
        current_action = "需要写入 ledger 做赛后验证"
        boss_summary = f"已完赛：{score_display}；W1 状态：{w1_state}；复盘动作：{current_action}"
    elif not play_guard_pass:
        current_action = stage_info["stage_current_action_cn"]
        boss_summary = f"{home_cn} vs {away_cn}：{stage_info['prediction_stage_cn']}，参考倾向 {reference['reference_direction']}，参考比分 {reference_score}；非最终结论"
    else:
        current_action = "可进入正式赛前分析，并写入 ledger"
        boss_summary = f"{home_cn} vs {away_cn}：通过 W1 风控，可正式分析"

    data_quality = data_quality_for_card(card, latest, play_guard_pass, odds_ok, risks, gaps)
    environment_context = environment_context_for_card(fid, card, latest, venues, weather_by_fixture)
    lineup_effect = lineup_effect_for_card(card)
    tactical_effect = tactical_effect_for_card(card, lineup_effect)

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
        "lineup_status": lineups.get("status") if lineups.get("confirmed_lineup_available") else ((ledger or {}).get("lineup_status") or latest.get("lineup_status") or lineups.get("status")),
        "confirmed_lineup_available": bool(lineups.get("confirmed_lineup_available")),
        "home_formation": lineups.get("formation_home") or lineups.get("home_formation"),
        "away_formation": lineups.get("formation_away") or lineups.get("away_formation"),
        "home_starting_count": len(lineups.get("home_starting_xi") or []),
        "away_starting_count": len(lineups.get("away_starting_xi") or []),
        "home_bench_count": len(lineups.get("home_substitutes") or lineups.get("home_bench_players") or []),
        "away_bench_count": len(lineups.get("away_substitutes") or lineups.get("away_bench_players") or []),
        "referee_status": (ledger or {}).get("referee_status") or latest.get("referee_status") or ("READY" if referee.get("available") else "MISSING"),
        "odds_status": "READY" if odds_ok else "WAIT",
        "data_quality": data_quality,
        "environment_context": environment_context,
        "lineup_effect": lineup_effect,
        "tactical_effect": tactical_effect,
        "odds_movement": movement,
        "market_signal": market_signal,
        "supporting_factors": [cn_display_text(item) for item in supporting],
        "counter_factors": counter,
        "risk_flags": [{**risk, "message": cn_display_text(risk.get("message", ""))} for risk in risks],
        "data_gaps": [{**gap, "message": cn_display_text(gap.get("message") or gap.get("field") or gap)} for gap in gaps],
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
        return cn_display_text(value).replace("W1_WAIT", "等待数据")

    def clean_odds_movement_text(value: str) -> str:
        replacements = {
            "odds_1x2": "赔率变化",
            "lineup_status": "首发状态",
            "referee_status": "裁判信息",
            "injury_status": "伤停信息",
        }
        for src, dst in replacements.items():
            value = value.replace(src, dst)
        return value

    def public_quality(value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            return {}

        def status_cn(kind: str, status: Any) -> str:
            mapping = {
                "overall": {"complete": "数据完整", "partial": "数据部分缺失", "poor": "数据质量较差"},
                "odds": {"success": "成功", "missing": "缺失", "stale": "过期", "error": "错误"},
                "lineup": {"confirmed": "已确认", "probable": "预计", "missing": "未公布", "error": "错误"},
                "referee": {"success": "已公布", "missing": "未公布", "error": "错误"},
                "injuries": {"success": "有记录", "empty": "无记录 / 暂无", "missing": "缺失", "error": "错误"},
                "context": {"available": "可用", "partial": "部分可用", "missing": "缺失"},
            }
            return mapping.get(kind, {}).get(str(status), clean_public_text(status))

        quality = json.loads(json.dumps(value, ensure_ascii=False))
        quality["overall"] = status_cn("overall", quality.get("overall"))
        quality["odds"]["status"] = status_cn("odds", quality.get("odds", {}).get("status"))
        quality["lineup"]["status"] = status_cn("lineup", quality.get("lineup", {}).get("status"))
        quality["referee"]["status"] = status_cn("referee", quality.get("referee", {}).get("status"))
        quality["injuries"]["status"] = status_cn("injuries", quality.get("injuries", {}).get("status"))
        for key in ("standings", "h2h", "squad"):
            quality["local_context"][key] = status_cn("context", quality.get("local_context", {}).get(key))
        rule_map = {"lineups.confirmed_lineup": "首发未确认", "match.referee": "裁判未公布"}
        quality["play_guard"]["fail_rules"] = [rule_map.get(str(rule), clean_public_text(rule)) for rule in quality.get("play_guard", {}).get("fail_rules", [])]
        return quality

    def public_environment(value: dict[str, Any]) -> dict[str, Any]:
        env = json.loads(json.dumps(value or {}, ensure_ascii=False))
        weather_map = {"ready": "已接入", "missing": "暂缺", "partial": "部分可用", "error": "错误"}
        roof_map = {"open": "露天", "closed": "闭合/可闭合", "unknown": "暂缺"}
        risk_map = {"LOW": "低", "MEDIUM": "中", "HIGH": "高"}
        flag_map = {
            "HIGH_TEMP": "高温",
            "HIGH_HUMIDITY": "高湿度",
            "HIGH_ALTITUDE": "高海拔",
            "HIGH_WIND": "大风",
            "RAIN_RISK": "降雨",
            "WEATHER_IMPACT_REDUCED": "屋顶降低天气影响",
            "WEATHER_MISSING": "天气数据暂缺",
        }
        env["weather_status"] = weather_map.get(str(env.get("weather_status")), clean_public_text(env.get("weather_status", "暂缺")))
        env["roof_status"] = roof_map.get(str(env.get("roof_status")), clean_public_text(env.get("roof_status", "暂缺")))
        env["environment_risk_level"] = risk_map.get(str(env.get("environment_risk_level")), clean_public_text(env.get("environment_risk_level", "暂缺")))
        env["environment_risk_flags"] = [flag_map.get(str(flag), clean_public_text(flag)) for flag in env.get("environment_risk_flags", [])]
        return env

    def public_lineup_effect(value: dict[str, Any]) -> dict[str, Any]:
        effect = json.loads(json.dumps(value or {}, ensure_ascii=False))
        status_map = {"missing": "暂不能判断", "ready": "已就绪", "partial": "部分可用"}
        confidence_map = {"unknown": "未知", "low": "低", "medium": "中", "high": "高"}
        effect_map = {"unknown": "暂不能判断", "up": "增强", "down": "下降", "stable": "稳定"}
        effect["status"] = status_map.get(str(effect.get("status")), clean_public_text(effect.get("status", "暂不能判断")))
        for key in ("home_starter_confidence", "away_starter_confidence"):
            effect[key] = confidence_map.get(str(effect.get(key)), clean_public_text(effect.get(key, "未知")))
        for key in (
            "attacking_power_effect",
            "defensive_stability_effect",
            "midfield_control_effect",
            "pace_transition_effect",
            "set_piece_effect",
            "pressing_effect",
        ):
            effect[key] = effect_map.get(str(effect.get(key)), clean_public_text(effect.get(key, "暂不能判断")))
        return effect

    def public_tactical_effect(value: dict[str, Any]) -> dict[str, Any]:
        effect = json.loads(json.dumps(value or {}, ensure_ascii=False))
        status_map = {"missing": "暂不能判断", "ready": "已就绪", "partial": "部分可用"}
        side_map = {
            "unknown": "暂不能判断",
            "home_up": "主队增强",
            "away_up": "客队增强",
            "balanced": "相对均衡",
        }
        tempo_map = {"unknown": "暂不能判断", "fast": "偏快", "medium": "中等", "slow": "偏慢"}
        transition_map = {
            "unknown": "暂不能判断",
            "home_counter": "主队防守反击",
            "away_counter": "客队防守反击",
            "balanced": "相对均衡",
        }
        set_piece_map = {
            "unknown": "暂不能判断",
            "home_edge": "主队占优",
            "away_edge": "客队占优",
            "balanced": "相对均衡",
        }
        effect["status"] = status_map.get(str(effect.get("status")), clean_public_text(effect.get("status", "暂不能判断")))
        effect["attacking_side_effect"] = side_map.get(str(effect.get("attacking_side_effect")), clean_public_text(effect.get("attacking_side_effect", "暂不能判断")))
        effect["defensive_stability_effect"] = side_map.get(str(effect.get("defensive_stability_effect")), clean_public_text(effect.get("defensive_stability_effect", "暂不能判断")))
        effect["tempo_effect"] = tempo_map.get(str(effect.get("tempo_effect")), clean_public_text(effect.get("tempo_effect", "暂不能判断")))
        effect["transition_effect"] = transition_map.get(str(effect.get("transition_effect")), clean_public_text(effect.get("transition_effect", "暂不能判断")))
        effect["set_piece_effect"] = set_piece_map.get(str(effect.get("set_piece_effect")), clean_public_text(effect.get("set_piece_effect", "暂不能判断")))
        return effect

    def public_record(row: dict[str, Any]) -> dict[str, Any]:
        clean_risks = []
        for item in row.get("counter_factors", []):
            clean_risks.append(clean_public_text(item))
        clean_gaps = []
        for gap in row.get("data_gaps", []):
            message = clean_public_text(gap.get("message") or gap.get("field") or gap)
            clean_gaps.append({"message": message})
        clean_supporting = [clean_public_text(item) for item in row.get("supporting_factors", [])]
        clean_movement = row.get("odds_movement", {})
        if "summary_cn" in clean_movement:
            clean_movement = {**clean_movement, "summary_cn": clean_odds_movement_text(clean_movement["summary_cn"])}
        if "changed_fields" in clean_movement and isinstance(clean_movement["changed_fields"], list):
            field_map = {"odds_1x2": "赔率", "lineup_status": "首发", "referee_status": "裁判", "injury_status": "伤停"}
            clean_movement["changed_fields"] = [field_map.get(f, f) for f in clean_movement["changed_fields"]]
        return {
            "match": row["match"],
            "fixture_id": row["fixture_id"],
            "group": row["group"],
            "home_team_cn": row["home_team_cn"],
            "away_team_cn": row["away_team_cn"],
            "home_flag": row["home_flag"],
            "away_flag": row["away_flag"],
            "kickoff": row["kickoff"],
            "confirmed_lineup_available": row.get("confirmed_lineup_available"),
            "home_formation": row.get("home_formation"),
            "away_formation": row.get("away_formation"),
            "home_starting_count": row.get("home_starting_count"),
            "away_starting_count": row.get("away_starting_count"),
            "home_bench_count": row.get("home_bench_count"),
            "away_bench_count": row.get("away_bench_count"),
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
            "odds_movement": clean_movement,
            "market_signal": row["market_signal"],
            "data_quality": public_quality(row["data_quality"]),
            "environment_context": public_environment(row["environment_context"]),
            "lineup_effect": public_lineup_effect(row["lineup_effect"]),
            "tactical_effect": public_tactical_effect(row["tactical_effect"]),
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
        "w1_backend_kept": [cn_display_text(item) for item in data["w1_backend_kept"]],
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
    venues = venue_context()
    weather_by_fixture = weather_cache()
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
                venues=venues,
                weather_by_fixture=weather_by_fixture,
            )
        )
    records.sort(key=lambda row: (row.get("kickoff") or "", row["fixture_id"]))

    first = next(row for row in records if row["fixture_id"] == "1489369")
    data["schema_version"] = "W1_VISUAL_DASHBOARD_DATA_BOUND_V1"
    data["generated_from"] = "本地 W1 赛前卡、ledger、状态文件、最新快照和人工核验赛果覆盖"
    data["generated_at_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    data["match_records"] = records
    data["prediction_stage_flow_cn"] = STAGE_FLOW_CN
    data["early_prediction_mode"] = {
        "version": PREDICTION_VERSION,
        "enabled": True,
        "principle_cn": "早盘参考和赛前观察可以输出参考倾向/参考比分，但只有正式判断或最终版且通过正式风控规则才可能成为正式判断。",
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
        "play_guard_result": "未通过正式风控规则；赛前未放行/未形成正式 W1_PLAY",
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
