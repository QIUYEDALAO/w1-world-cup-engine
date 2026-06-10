#!/usr/bin/env python3
"""Validate W1_VISUAL_DASHBOARD_V1 static artifacts."""

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
FORBIDDEN_TERMS = ["Q" + "Q", "offi" + "cial", "pend" + "ing", "V" + "3", "V" + "4", "M" + "1"]


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
    for term in FORBIDDEN_TERMS:
        if term in text:
            fail(f"Forbidden term found in {path.relative_to(ROOT)}")


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


def assert_dashboard_data(data: dict) -> None:
    if data.get("schema_version") != "W1_VISUAL_DASHBOARD_V2_CN":
        fail("Dashboard data schema_version mismatch")
    if data.get("display_language") != "zh-CN":
        fail("Dashboard must declare zh-CN display language")

    groups = data.get("groups", [])
    if len(groups) != 12:
        fail(f"Expected 12 groups, found {len(groups)}")
    expected_letters = list("ABCDEFGHIJKL")
    if [group.get("group") for group in groups] != expected_letters:
        fail("Groups must be A-L in order")

    teams: list[str] = []
    for group in groups:
        group_teams = group.get("teams", [])
        if len(group_teams) != 4:
            fail(f"Group {group.get('group')} must contain 4 teams")
        teams.extend(group_teams)
        template = group.get("standings_template", [])
        if len(template) != 4:
            fail(f"Group {group.get('group')} standings template must contain 4 rows")
        for row in template:
            for key in ("P", "W", "D", "L", "GF", "GA", "GD", "PTS"):
                if key not in row:
                    fail(f"Standings template missing {key}")
            if row.get("points_label") != f"{row.get('PTS')}分":
                fail(f"Standings points label mismatch in Group {group.get('group')}")
        paths = group.get("qualification_paths", [])
        if len(paths) != 3:
            fail(f"Group {group.get('group')} must contain 3 qualification paths")
        finishes = [path.get("finish") for path in paths]
        if finishes != ["第1名", "第2名", "第3名"]:
            fail(f"Group {group.get('group')} qualification paths must cover first, second, third")
        for path in paths:
            if not path.get("slot") or not path.get("opponent"):
                fail(f"Group {group.get('group')} qualification path missing slot/opponent")

    if len(teams) != 48:
        fail(f"Expected 48 teams, found {len(teams)}")
    if len(set(teams)) != 48:
        fail("Duplicate team found in group context")
    if data.get("team_display_language") != "zh-CN":
        fail("Team display language must be zh-CN")
    team_map = data.get("team_name_map_cn", {})
    if len(team_map) != 48:
        fail("Chinese team name map must contain 48 teams")
    for group in groups:
        if len(group.get("teams_cn", [])) != 4:
            fail(f"Group {group.get('group')} must contain 4 Chinese team names")
    for required_team in ("墨西哥", "南非", "巴西", "阿根廷", "英格兰", "日本"):
        if required_team not in team_map.values():
            fail(f"Chinese team name missing: {required_team}")

    fixture_teams = current_fixture_teams()
    missing = sorted(fixture_teams - set(teams))
    if missing:
        fail(f"Fixture teams missing from group context: {missing}")

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
    for key in ("points", "goal_diff", "goals_for", "fair_play", "drawing_of_lots"):
        if key not in rules.get("third_place_tiebreakers", []):
            fail(f"Missing third-place tiebreaker: {key}")

    if len(data.get("third_place_ranking_template", [])) != 12:
        fail("Third-place ranking template must contain 12 rows")
    if data.get("standings_compact_headers_cn") != ["球队", "赛", "净胜", "积分"]:
        fail("Compact standings headers mismatch")
    if "小组第三的具体落位" not in data.get("knockout_path_note_cn", ""):
        fail("Knockout path note must explain third-place uncertainty")

    first = data.get("first_match", {})
    if first.get("match") != "Mexico vs South Africa":
        fail("First match must be Mexico vs South Africa")
    if first.get("decision") != "W1_WAIT":
        fail("First match decision must be W1_WAIT")
    if first.get("odds_status") != "READY":
        fail("First match odds status must be READY")
    if first.get("play_guard_pass") is not False:
        fail("First match play_guard_pass must be false while lineup is missing")

    boss = data.get("boss_view", {})
    if boss.get("current_conclusion") != "全部等待首发/裁判等关键数据":
        fail("Boss view conclusion mismatch")
    if boss.get("first_match_cn") != "墨西哥 vs 南非":
        fail("Boss view first match must be Chinese")

    cn_labels = [item.get("label") for item in data.get("status_cards_cn", [])]
    for label in ("等待数据", "观察中", "可正式分析", "跳过"):
        if label not in cn_labels:
            fail(f"Missing Chinese status label: {label}")


def assert_html(data: dict) -> None:
    if not HTML.is_file():
        fail("HTML dashboard is missing")
    assert_no_forbidden_terms(HTML)
    text = read(HTML)
    required = [
        "W1 世界杯赛前总控台",
        "小组赛程、晋级规则、赛前状态与风险提醒。当前不输出投注建议。",
        "当前你只需要看这里",
        "等待数据",
        "观察中",
        "可正式分析",
        "跳过",
        "刷新器版本",
        "风控规则",
        "下次刷新",
        "W1_PLAY_GUARD_V1",
        "全部等待首发/裁判等关键数据",
        "墨西哥 vs 南非",
        "巴西",
        "阿根廷",
        "英格兰",
        "日本",
        "正式判断时间",
        "等待，不下结论",
        "世界杯小组总览",
        "每组前2名直接晋级",
        "当前积分与晋级后潜在对阵",
        "0分",
        "32强席位",
        "潜在对手",
        "小组第三的具体落位",
        "对 B组第2名",
        "若成为8个最佳第三之一",
        "12个小组，每组4队",
        "12个小组第三中成绩最好的8队晋级",
        "共32队进入淘汰赛",
        "比赛",
        "开赛时间",
        "当前状态",
        "首发",
        "裁判",
        "赔率",
        "风控是否通过",
        "颜色 / 标签解释",
        "关键数据没齐",
        "有信号但风险较高",
        "通过量化风控",
        "风险过高或数据冲突",
    ]
    for token in required:
        if token not in text:
            fail(f"HTML missing token: {token}")
    if "fetch(" in text:
        fail("HTML should not require fetch for double-click use")

    embedded = re.search(r'<script id="w1-data" type="application/json">(.*?)</script>', text, re.S)
    if not embedded:
        fail("HTML must embed dashboard data for file-open use")
    try:
        embedded_data = json.loads(embedded.group(1))
    except json.JSONDecodeError as exc:
        fail(f"Embedded dashboard JSON is not parseable: {exc}")
    if embedded_data != data:
        fail("Embedded dashboard JSON must match asset data JSON")


def main() -> int:
    try:
        for path in (DATA_JSON, DOC):
            if not path.is_file():
                fail(f"Missing artifact: {path.relative_to(ROOT)}")
            assert_no_forbidden_terms(path)
        data = load_json(DATA_JSON)
        assert_dashboard_data(data)
        assert_html(data)
    except CheckError as exc:
        print(f"W1 visual dashboard self-test FAIL: {exc}", file=sys.stderr)
        return 1

    print("W1 visual dashboard self-test PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
