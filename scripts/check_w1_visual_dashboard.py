#!/usr/bin/env python3
"""Validate W1 visual dashboard static artifacts."""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
DATA_JSON = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
LEDGER = ROOT / "data/processed/ledger/w1_ledger_group_stage_round1.csv"
DOC = ROOT / "docs/W1_VISUAL_DASHBOARD.md"
POLICY = ROOT / "docs/W1_UI_REUSE_POLICY.md"
CAPTURE_DIR = Path("/tmp/w1_original_site_capture")

FORBIDDEN_SOURCE_TERMS = [
    "DeepSeek API Key",
    "微信群机器人",
    "付费预测群",
    "bet",
    "stake",
    "profit",
    "guaranteed",
    "稳赚",
    "必胜",
    "Q" + "Q",
    "offi" + "cial",
    "pend" + "ing",
    "V" + "3",
    "V" + "4",
    "M" + "1",
]
FORBIDDEN_DASHBOARD_DISPLAY_TERMS = [
    "missing",
    "latest snapshot",
    "fixture detail snapshot",
    "non-WAIT final_decision",
    "lineup=WAIT",
]


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(read(path))


def assert_no_forbidden_terms(path: Path) -> None:
    text = read(path)
    for term in FORBIDDEN_SOURCE_TERMS:
        if term.isascii():
            if re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", text, re.I):
                fail(f"Forbidden term found in {path.relative_to(ROOT)}: {term}")
            continue
        if term in text:
            fail(f"Forbidden term found in {path.relative_to(ROOT)}: {term}")


def current_fixture_teams() -> set[str]:
    with LEDGER.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 24:
        fail(f"Expected 24 ledger rows, found {len(rows)}")
    teams: set[str] = set()
    for row in rows:
        teams.add(row["home_team"])
        teams.add(row["away_team"])
    if len(teams) != 48:
        fail(f"Expected 48 unique fixture teams, found {len(teams)}")
    return teams


def assert_groups(data: dict) -> None:
    groups = data.get("groups", [])
    if len(groups) != 12:
        fail(f"Expected 12 groups, found {len(groups)}")
    if [group.get("group") for group in groups] != list("ABCDEFGHIJKL"):
        fail("Groups must be A-L in order")

    teams: list[str] = []
    for group in groups:
        group_teams = group.get("teams", [])
        if len(group_teams) != 4:
            fail(f"Group {group.get('group')} must contain 4 teams")
        teams.extend(group_teams)

        if len(group.get("teams_cn", [])) != 4:
            fail(f"Group {group.get('group')} must contain 4 Chinese team names")

        standings = group.get("standings_template", [])
        if len(standings) != 4:
            fail(f"Group {group.get('group')} standings template must contain 4 rows")
        for row in standings:
            for key in ("P", "W", "D", "L", "GF", "GA", "GD", "PTS", "team_cn"):
                if key not in row:
                    fail(f"Standings template missing {key}")
            if row.get("points_label") != f"{row.get('PTS')}分":
                fail(f"Standings points label mismatch in Group {group.get('group')}")

        paths = group.get("qualification_paths", [])
        if len(paths) != 3:
            fail(f"Group {group.get('group')} must contain 3 qualification paths")
        if [path.get("finish") for path in paths] != ["第1名", "第2名", "第3名"]:
            fail(f"Group {group.get('group')} qualification paths must cover first, second, third")
        for path in paths:
            if not path.get("slot") or not path.get("opponent"):
                fail(f"Group {group.get('group')} qualification path missing slot/opponent")

    if len(teams) != 48:
        fail(f"Expected 48 teams, found {len(teams)}")
    if len(set(teams)) != 48:
        fail("Duplicate team found in group context")

    missing = sorted(current_fixture_teams() - set(teams))
    if missing:
        fail(f"Fixture teams missing from group context: {missing}")


def assert_dashboard_data(data: dict) -> None:
    if data.get("schema_version") != "W1_VISUAL_DASHBOARD_DATA_BOUND_V1":
        fail("Dashboard data schema_version mismatch")
    if data.get("display_language") != "zh-CN":
        fail("Dashboard must declare zh-CN display language")
    if data.get("team_display_language") != "zh-CN":
        fail("Team display language must be zh-CN")

    assert_groups(data)

    team_map = data.get("team_name_map_cn", {})
    if len(team_map) != 48:
        fail("Chinese team name map must contain 48 teams")
    for required_team in ("墨西哥", "南非", "巴西", "阿根廷", "英格兰", "日本"):
        if required_team not in team_map.values():
            fail(f"Chinese team name missing: {required_team}")

    rules = data.get("advancement_rules", {})
    expected_rules = {
        "direct_qualifiers": 24,
        "best_third_qualifiers": 8,
        "round_of_32_total": 32,
        "groups_total": 12,
        "teams_per_group": 4,
    }
    for key, expected in expected_rules.items():
        if rules.get(key) != expected:
            fail(f"Advancement rule mismatch for {key}: {rules.get(key)}")
    if rules["direct_qualifiers"] + rules["best_third_qualifiers"] != rules["round_of_32_total"]:
        fail("Advancement rule totals do not sum to Round of 32")

    if data.get("status_cards", {}).get("play_guard_version") != "W1_PLAY_GUARD_V1":
        fail("PLAY_GUARD_V1 must remain in dashboard data")
    if "W1_PLAY_GUARD_V1" not in data.get("w1_backend_kept", []):
        fail("W1 backend list must keep W1_PLAY_GUARD_V1")

    boss = data.get("boss_view", {})
    expected_boss = {
        "current_status": "24 场 W1 数据已绑定",
        "first_match_cn": "墨西哥 vs 南非",
        "reference_lean": "墨西哥不败",
        "reference_score": "1-0 / 0-0",
        "current_action": "需要写入 ledger 做赛后验证",
        "formal_review_time_cst": "6月12日 02:00 / 02:30 CST",
    }
    for key, expected in expected_boss.items():
        if boss.get(key) != expected:
            fail(f"Boss view mismatch for {key}")
    if "不绕过 W1 风控" not in boss.get("explanation", ""):
        fail("Boss view must say reference score does not bypass W1 guard")

    first = data.get("first_match_cn", {})
    for key in (
        "match",
        "kickoff",
        "current_conclusion",
        "reference_score",
        "risk_level",
        "supporting_factors",
        "counter_factors",
        "key_gaps",
        "current_action",
        "play_guard_result",
        "public_technical_details",
    ):
        if key not in first:
            fail(f"First match card missing {key}")
    if first["match"] != "墨西哥 vs 南非":
        fail("First match must be Chinese")
    if "正式风控规则" not in first["play_guard_result"]:
        fail("First match must keep formal guard result in Chinese")
    if "未通过" not in first["play_guard_result"]:
        fail("First match must not pass W1 guard")
    if first.get("actual_score_display_cn") != "墨西哥 2-0 南非":
        fail("First match actual score must be bound")
    if first.get("post_match_calibration", {}).get("evaluation_method") != "rps_log_score":
        fail("First match must expose RPS/log score calibration")

    tech = first["public_technical_details"]
    if len(tech) < 5:
        fail("Public technical details must summarize W1 state without raw keys")
    for item in tech:
        if not item.get("label") or not item.get("value"):
            fail("Public technical details must use Chinese label/value pairs")

    cn_labels = [item.get("label") for item in data.get("status_cards_cn", [])]
    for label in ("等待数据", "观察中", "可正式分析", "跳过"):
        if label not in cn_labels:
            fail(f"Missing Chinese status label: {label}")


def assert_html(data: dict) -> None:
    if not HTML.is_file():
        fail("HTML dashboard is missing")
    assert_no_forbidden_terms(HTML)
    text = read(HTML)
    if "backendConnected=false" in text and "fetchBackendDashboardData" in text:
        required_new = [
            "W1 世界杯赛前预测控制台",
            "backendConnected",
            "/dashboard-data",
            "/predict",
            "/progress",
            "后端未连接",
            "正在抓取 + 预测",
            "已保留当前快照，未覆盖",
            "主比分",
            "备选比分",
            "风险路径",
            "专家展开区",
            "完整比分矩阵",
            "非推荐列表",
            "数据质量",
            "比赛环境",
            "阵容效应",
            "战术效应",
            "赛后校准",
            "不构成投注",
        ]
        for token in required_new:
            if token not in text:
                fail(f"HTML missing backend dashboard token: {token}")
        if "fetch('/api/predict" in text or 'fetch("/api/predict' in text or "worldcup.youliaoyun.com/api" in text:
            fail("HTML must not call the original site prediction API")
        embedded = re.search(r'<script id="w1-data" type="application/json">(.*?)</script>', text, re.S)
        if not embedded:
            fail("HTML must embed dashboard data for file-open use")
        try:
            embedded_data = json.loads(embedded.group(1))
        except json.JSONDecodeError as exc:
            fail(f"Embedded dashboard JSON is not parseable: {exc}")
        if len(embedded_data.get("match_records", [])) < 24:
            fail("Embedded dashboard JSON must include at least 24 match_records")
        qatar = next((row for row in embedded_data.get("match_records", []) if row.get("fixture_id") == "1489373"), None)
        if not qatar:
            fail("Embedded match_records must include fixture_id=1489373")
        for key in ("data_quality", "environment_context", "lineup_effect", "tactical_effect", "live_refresh", "score_matrix_summary", "recommendation_view"):
            if key not in qatar:
                fail(f"Embedded match_records fixture_id=1489373 missing {key}")
        view = qatar.get("recommendation_view", {})
        if view.get("display_score_limit") != 2:
            fail("recommendation_view.display_score_limit must be 2")
        return
    required = [
        "W1 世界杯赛前预测总控台",
        "WHO",
        "WINS?",
        "今日/下一场焦点",
        "对阵预测台",
        "teamA",
        "teamB",
        "stageRow",
        "goBtn",
        "开始预测",
        "result",
        "fix-card",
        "详细解读",
        "风险提示",
        "关键缺口",
        "数据质量",
        "赔率：",
        "首发：",
        "风控：",
        "数据部分缺失",
        "本次实时刷新",
        "实时 API 成功",
        "使用缓存",
        "使用兜底数据",
        "比分分布",
        "比分概率池",
        "比赛打开机制",
        "防线崩盘",
        "深让不等于大胜",
        "平手盘也可能打开",
        "大小球不直接决定比分",
        "赛后校准",
        "比赛环境",
        "球场：",
        "天气：",
        "温度：",
        "湿度：",
        "风速：",
        "海拔：",
        "环境风险：",
        "天气数据暂缺",
        "当前你只需要看这里",
        "24 场 W1 数据已绑定",
        "墨西哥 vs 南非",
        "参考倾向",
        "墨西哥不败",
        "参考比分",
        "2-0",
        "RPS",
        "log score",
        "墨西哥 2-0 南非",
        "当前动作",
        "需要写入 ledger 做赛后验证",
        "正式判断",
        "6月12日 02:00 / 02:30 CST",
        "参考比分是外部参考信号",
        "倾向",
        "理由",
        "风险提示",
        "关键缺口",
        "神算战绩",
        "ledger 做赛后复盘",
        "正式风控规则",
        "首发未确认",
        "裁判未公布",
        "早盘参考",
        "不是最终结论",
        "不构成投注建议",
    ]
    for token in required:
        if token not in text:
            fail(f"HTML missing token: {token}")
    for original_api in ("fetch('/api/predict", 'fetch("/api/predict', "worldcup.youliaoyun.com/api"):
        if original_api in text:
            fail("HTML must not call the original site prediction API")
    for extra_section in ("世界杯分组", "晋级规则"):
        if extra_section in text:
            fail(f"HTML must not include extra dashboard section: {extra_section}")
    for token in ("buildW1Card", "render(", "addEventListener('click'", "两支球队不能相同"):
        if token not in text:
            fail(f"HTML missing local interaction token: {token}")
    for token in ("getFullMatchRecord", "renderDataQualityPanel", "renderQueryResultSummary", "selectDefaultMatch"):
        if token not in text:
            fail(f"HTML missing data-binding function: {token}")
    if "groups.round1_fixtures" in text:
        fail("HTML must not use groups.round1_fixtures as the main display data source")
    if "data.match_records" not in text:
        fail("HTML main panel must reference match_records")
    if text.count('class="arena"') != 1:
        fail("HTML must contain exactly one main prediction panel")
    if text.count('id="result"') != 1:
        fail("HTML must contain exactly one detail result container")
    if "selectDefaultMatch" not in text:
        fail("HTML must include default match selection logic")
    if r"match(/(\\d" in text:
        fail("HTML kickoff parser must use browser regex digits, not escaped literal backslash-d")
    for token in ("isFutureKickoff", "isToday", "uniqueByFixture", "待赛果更新"):
        if token not in text:
            fail(f"HTML missing date-aware focus token: {token}")
    for token in ("首发效应", "核心缺席", "轮换风险", "进攻/防守/中场", "转换速度/定位球/压迫", "是否需要重算参考倾向"):
        if token not in text:
            fail(f"HTML missing lineup effect token: {token}")
    for token in ("战术效应", "主队打法", "客队打法", "边路速度", "转换进攻", "前场冲击", "三中卫", "翼卫推进", "中路保护"):
        if token not in text:
            fail(f"HTML missing tactical effect token: {token}")
    for token in ("live", "not_started", "upcoming", "finished"):
        if token not in text:
            fail(f"Default/focus logic missing priority token: {token}")
    select_idx = text.find("function selectDefaultMatch")
    if select_idx < 0:
        fail("selectDefaultMatch function missing")
    select_body = text[select_idx:select_idx + 1200]
    if not (select_body.find("live") < select_body.find("todayNotStarted") < select_body.find("upcoming") < select_body.find("finished")):
        fail("Default selection must prefer live/not_started/upcoming before finished")
    for raw_key in ("play_guard_pass", "lineup_status", "W1_WAIT"):
        if raw_key in text:
            fail(f"HTML must not expose raw key: {raw_key}")
    for token in FORBIDDEN_DASHBOARD_DISPLAY_TERMS:
        if re.search(re.escape(token), text, re.I):
            fail(f"HTML must not expose English/raw display text: {token}")
    if "keep as a non-blocking gap" in text:
        fail("HTML must not expose old non-blocking English copy")

    embedded = re.search(r'<script id="w1-data" type="application/json">(.*?)</script>', text, re.S)
    if not embedded:
        fail("HTML must embed dashboard data for file-open use")
    try:
        embedded_data = json.loads(embedded.group(1))
    except json.JSONDecodeError as exc:
        fail(f"Embedded dashboard JSON is not parseable: {exc}")
    embedded_text = embedded.group(1)
    for raw_key in ("play_guard_pass", "lineup_status", "W1_WAIT"):
        if raw_key in embedded_text:
            fail(f"Embedded dashboard JSON must not expose raw key: {raw_key}")
    for token in FORBIDDEN_DASHBOARD_DISPLAY_TERMS:
        if re.search(re.escape(token), embedded_text, re.I):
            fail(f"Embedded dashboard JSON must not expose English/raw display text: {token}")
    if embedded_data.get("schema_version") != data.get("schema_version"):
        fail("Embedded dashboard JSON schema version mismatch")
    if len(embedded_data.get("groups", [])) != 12:
        fail("Embedded dashboard JSON must include 12 public groups")
    qatar = next((row for row in embedded_data.get("match_records", []) if row.get("fixture_id") == "1489373"), None)
    if not qatar or "data_quality" not in qatar:
        fail("Embedded match_records must expose data_quality for fixture_id=1489373")
    if "environment_context" not in qatar:
        fail("Embedded match_records must expose environment_context for fixture_id=1489373")
    if "lineup_effect" not in qatar:
        fail("Embedded match_records must expose lineup_effect for fixture_id=1489373")
    if "tactical_effect" not in qatar:
        fail("Embedded match_records must expose tactical_effect for fixture_id=1489373")
    if "live_refresh" not in qatar:
        fail("Embedded match_records must expose live_refresh for fixture_id=1489373")
    lineups = qatar.get("live_refresh", {}).get("modules", {}).get("lineups", {})
    for key in ("source", "status", "fetched_at", "message_cn"):
        if key not in lineups:
            fail(f"Embedded live_refresh.modules.lineups missing {key}")
    if "score_distribution" not in qatar:
        fail("Embedded match_records must expose score_distribution for fixture_id=1489373")
    qatar_score = qatar.get("score_distribution", {})
    for key in ("score_pool", "game_open_trigger", "market_vs_score_risk", "post_match_calibration"):
        if key not in qatar_score:
            fail(f"Embedded score_distribution missing {key}")


def assert_docs() -> None:
    for path in (DOC, POLICY):
        if not path.is_file():
            fail(f"Missing artifact: {path.relative_to(ROOT)}")
        assert_no_forbidden_terms(path)
    policy_text = read(POLICY)
    for token in ("只复用中文 UI", "不复用该项目的 prompt 预测逻辑", "不能绕过 W1_PLAY_GUARD_V1"):
        if token not in policy_text:
            fail(f"UI reuse policy missing token: {token}")


def assert_original_site_capture() -> None:
    if not CAPTURE_DIR.is_dir():
        return
    required = [
        "original_home_full.png",
        "original_first_view.png",
        "original_groups_viewport.png",
        "original_match_card_viewport.png",
        "original_rules_viewport.png",
        "original_dom_summary.json",
    ]
    for name in required:
        path = CAPTURE_DIR / name
        if not path.is_file() or path.stat().st_size == 0:
            fail(f"Original site capture missing: {path}")


def main() -> int:
    try:
        if not DATA_JSON.is_file():
            fail("Dashboard data JSON is missing")
        assert_no_forbidden_terms(DATA_JSON)
        data = load_json(DATA_JSON)
        assert_dashboard_data(data)
        assert_html(data)
        assert_docs()
        assert_original_site_capture()
    except CheckError as exc:
        print(f"W1 visual dashboard self-test FAIL: {exc}", file=sys.stderr)
        return 1

    print("W1 visual dashboard self-test PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
