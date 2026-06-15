#!/usr/bin/env python3
"""Validate W1_MARKET_PROBABILITY_PANEL_V1."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts/build_w1_dashboard_data.py"
DATA_JSON = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
SCORE_ENGINE = ROOT / "scripts/w1_score_engine.py"
RHO_PROVENANCE = ROOT / "config/w1_rho_provenance.json"
ODDS_THRESHOLDS = ROOT / "config/w1_odds_movement_thresholds.json"


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def approx(value: float, expected: float, tol: float = 1e-4) -> None:
    if abs(float(value) - expected) > tol:
        fail(f"expected {expected}, got {value}")


def load_builder():
    spec = importlib.util.spec_from_file_location("w1_dashboard_builder", BUILDER)
    if not spec or not spec.loader:
        fail("unable to import build_w1_dashboard_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_math(module) -> None:
    ou_matrix = np.zeros((4, 4), dtype=float)
    ou_matrix[1, 1] = 0.50
    ou_matrix[2, 1] = 0.25
    ou_matrix[0, 0] = 0.25

    ou_20 = module.derive_ou_from_score_matrix(ou_matrix, [2.0])[0]
    approx(ou_20["over_win_prob"], 0.25)
    approx(ou_20["push_prob"], 0.50)
    approx(ou_20["under_win_prob"], 0.25)

    ou_225 = module.derive_ou_from_score_matrix(ou_matrix, [2.25])[0]
    approx(ou_225["over_win_prob"], 0.25)
    approx(ou_225["push_prob"], 0.25)
    approx(ou_225["under_win_prob"], 0.50)

    ah_matrix = np.zeros((3, 3), dtype=float)
    ah_matrix[1, 0] = 0.50
    ah_matrix[1, 1] = 0.25
    ah_matrix[0, 1] = 0.25

    ah_m05 = module.derive_ah_from_score_matrix(ah_matrix, [-0.5])[0]
    approx(ah_m05["home_cover_win_prob"], 0.50)
    approx(ah_m05["home_cover_push_prob"], 0.0)
    approx(ah_m05["home_cover_lose_prob"], 0.50)

    ah_0 = module.derive_ah_from_score_matrix(ah_matrix, [0.0])[0]
    approx(ah_0["home_cover_win_prob"], 0.50)
    approx(ah_0["home_cover_push_prob"], 0.25)
    approx(ah_0["home_cover_lose_prob"], 0.25)

    ah_m075 = module.derive_ah_from_score_matrix(ah_matrix, [-0.75])[0]
    approx(ah_m075["home_cover_win_prob"], 0.25)
    approx(ah_m075["home_cover_push_prob"], 0.25)
    approx(ah_m075["home_cover_lose_prob"], 0.50)


def assert_data() -> None:
    data = json.loads(read(DATA_JSON))
    records = data.get("match_records", [])
    if len(records) < 24:
        fail("dashboard data must contain at least 24 match records")
    for row in records:
        panel = row.get("market_probability_panel")
        if not panel:
            fail(f"{row.get('fixture_id')}: missing market_probability_panel")
        if panel.get("schema_version") != "W1_MARKET_PROBABILITY_PANEL_V1":
            fail(f"{row.get('fixture_id')}: wrong panel schema")
        if panel.get("source") != "score_matrix":
            fail(f"{row.get('fixture_id')}: panel source must be score_matrix")
        if panel.get("status") not in {"ready", "已生成"}:
            continue
        one_x_two = panel.get("one_x_two") or {}
        approx(one_x_two.get("sum_check"), 1.0, 0.002)
        btts = panel.get("btts") or {}
        approx(btts.get("sum_check"), 1.0, 0.002)
        for item in panel.get("totals", []):
            approx(item.get("sum_check"), 1.0, 0.002)
        for item in panel.get("handicap", []):
            approx(item.get("sum_check"), 1.0, 0.002)
        rv = row.get("recommendation_view", {})
        if not rv.get("primary_score"):
            fail(f"{row.get('fixture_id')}: primary_score must remain unique")
        if isinstance(rv.get("secondary_score"), list):
            fail(f"{row.get('fixture_id')}: secondary_score must not become a list")


def assert_static_guards() -> None:
    builder = read(BUILDER)
    for marker in (
        "derive_1x2_from_score_matrix",
        "derive_ou_from_score_matrix",
        "derive_ah_from_score_matrix",
        "derive_btts_from_score_matrix",
        "market_probability_panel_from_score_distribution",
    ):
        if marker not in builder:
            fail(f"builder missing {marker}")
    if "recommendation_view" in builder.split("def market_probability_panel_from_score_distribution", 1)[1].split("def risk_level_cn", 1)[0]:
        fail("market probability panel must not derive from recommendation text")

    html = read(HTML)
    for marker in ("盘口概率面板", "市场复述", "自洽核对", "BTTS"):
        if marker not in html:
            fail(f"dashboard missing display marker: {marker}")
    for marker in (
        "class=\"mgrid\"",
        "class=\"mcard\"",
        "盘口读数摘要",
        "市场复述",
        "自洽核对",
        "未对该盘独立校准",
        "read1x2",
        "readOU",
        "readAH",
        "readBTTS",
        "读数：<b>",
        "双方接近，优势不大",
        "略偏小比分",
        "大小球接近均衡",
        "主队不败读数",
        "双方进球接近五五开",
        "1X2",
        "大小球",
        "让球",
        "默认 O/U 2.5",
        "O2.5",
        "U2.5",
        "Yes",
        "No",
        "主队 ${ah.home_handicap>0?'+':''}${ah.home_handicap} 球",
        "模型 <b>",
        "市场 <b>",
        "差值 <b>",
        "一致",
        "轻微偏离",
        "偏离较大，需复核盘口来源",
        "function pMarketProbabilityExpert",
        "calculation source: score_matrix",
    ):
        if marker not in html:
            fail(f"dashboard missing compact panel marker: {marker}")
    if "row('走盘'" in html:
        fail("ordinary O/U 2.5 card must not render push/walk row")
    if "主队 ${ah.home_handicap>0?'+':''}${ah.home_handicap}`" in html:
        fail("AH label must include 球, not bare 主队 0")
    if "O/U 2.5 · 大" in html or "pMarketProbabilityPanel(r)+pMarketProbabilityPanel" in html:
        fail("dashboard still contains old/debug market panel layout")
    if "grid-template-columns:minmax(64px,1fr) auto" not in html:
        fail("market probability rows must keep labels horizontal on narrow cards")
    if html.count("    pMarketProbabilityPanel(r)+") != 1:
        fail("dashboard must render one ordinary market probability panel")
    if html.count("pMarketProbabilityExpert(r)+pScenarios") != 1:
        fail("dashboard must render one expert market probability panel")
    forbidden = ("投注" + "建议", "下" + "注", "资金" + "建议", "稳" + "赚", "必" + "胜", "保证" + "命中")
    combined = "\n".join([builder, html, read(DATA_JSON)])
    for term in forbidden:
        if term in combined:
            fail(f"forbidden wording found: {term}")
    panel_source = html.split("function pMarketProbabilityPanel", 1)[1].split("function pMarketProbabilityExpert", 1)[0]
    for term in ("EV", "value", "价值"):
        if re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", panel_source, re.I):
            fail(f"forbidden market panel wording found: {term}")

    if "DEFAULT_RHO = -0.057766" not in read(SCORE_ENGINE):
        fail("DEFAULT_RHO changed")
    provenance = json.loads(read(RHO_PROVENANCE))
    if provenance.get("default_rho") != -0.057766:
        fail("rho provenance changed")
    thresholds = json.loads(read(ODDS_THRESHOLDS))
    if thresholds.get("calibrated") != "none" or thresholds.get("tier") != "C":
        fail("odds movement thresholds changed")

    diff = subprocess.run(
        ["git", "diff", "--name-only", "--", "scripts/w1_score_engine.py", "config/w1_odds_movement_thresholds.json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if diff.returncode != 0:
        fail(diff.stderr.strip() or "git diff failed")
    changed = [line for line in diff.stdout.splitlines() if line.strip()]
    if changed:
        fail(f"score matrix core or odds thresholds changed: {changed}")


def main() -> int:
    try:
        module = load_builder()
        assert_math(module)
        assert_data()
        assert_static_guards()
    except Exception as exc:  # noqa: BLE001
        print(f"W1 market probability panel check FAIL: {exc}", file=sys.stderr)
        return 1
    print("W1 market probability panel check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
