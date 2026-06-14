#!/usr/bin/env python3
"""Validate W1_DASHBOARD_BACKEND_PREDICT_INTEGRATION_V1."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
SERVER = ROOT / "scripts/w1_local_predict_server.py"
SCORE_ENGINE = ROOT / "scripts/w1_score_engine.py"
RHO_PROVENANCE = ROOT / "config/w1_rho_provenance.json"
DECISION_POLICY = ROOT / "config/w1_decision_policy.json"
FIXTURE_ALIASES = ROOT / "data/fixture_aliases.json"


class CheckError(Exception):
    pass


def fail(message: str) -> None:
    raise CheckError(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def assert_api_discovery() -> None:
    text = read(SERVER)
    for token in (
        "ThreadingHTTPServer",
        "SimpleHTTPRequestHandler",
        "def do_GET",
        "def do_POST",
        'path == "/health"',
        'path == "/progress"',
        'path == "/dashboard-data"',
        'path != "/predict"',
        "resolve_predict_match",
        "progress_payload",
        "current_match",
        "steps",
    ):
        if token not in text:
            fail(f"server missing API token: {token}")


def assert_fixture_aliases() -> None:
    aliases = json.loads(read(FIXTURE_ALIASES))
    if aliases.get("66457070") != "1489374" or aliases.get("1489374") != "66457070":
        fail("Germany vs Curacao fixture aliases must map 66457070 <-> 1489374")


def assert_html_backend_wiring() -> None:
    text = read(HTML)
    for token in (
        "backendConnected=false",
        "fetchBackendDashboardData",
        "async function loadData",
        "'/dashboard-data'",
        "markSource(true)",
        "markSource(false)",
        "setInterval(probeBackend, 20000)",
        "async function runPredict",
        "后端未连接",
        "'/predict'",
        "method:'POST'",
        "fixture_id:r.fixture_id",
        "home_team_cn:r.home_team_cn",
        "away_team_cn:r.away_team_cn",
        "stage_cn:selStage",
        "正在抓取 + 预测",
        "async function pollProgress",
        "'/progress'",
        "p.steps",
        "p.status==='done'",
        "已保留当前快照，未覆盖",
        "仅成功时替换快照",
        "fetchBackendDashboardData();backendConnected=true",
    ):
        if token not in text:
            fail(f"dashboard missing backend wiring token: {token}")
    if "const fresh=await loadData();D=fresh" in text:
        fail("runPredict must not use loadData fallback when refreshing after predict")


def assert_display_policy() -> None:
    text = read(HTML)
    for token in ("主比分", "备选比分", "风险路径", "专家展开区", "完整比分矩阵"):
        if token not in text:
            fail(f"dashboard missing recommendation display token: {token}")
    if "非推荐列表" not in text:
        fail("Top8/expert score list must be labeled non-recommendation")
    if re.search(r"TOP 8[^<]{0,80}推荐", text) and "TOP 8<span class=\"r\">按概率排序，非推荐列表" not in text:
        fail("Top8 must not be called recommendation")
    if "expertOpen=false" not in text or "id=\"expert\" class=\"${expertOpen?'open':''}\"" not in text:
        fail("expert score matrix view must be collapsed by default")


def assert_core_unchanged() -> None:
    if "DEFAULT_RHO = -0.057766" not in read(SCORE_ENGINE):
        fail("DEFAULT_RHO changed")
    provenance = json.loads(read(RHO_PROVENANCE))
    if provenance.get("default_rho") != -0.057766 or provenance.get("calibrated") is not True:
        fail("rho provenance changed unexpectedly")
    if "W1_PLAY_GUARD_V1" not in read(DECISION_POLICY):
        fail("PLAY_GUARD missing")
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--",
            str(SCORE_ENGINE.relative_to(ROOT)),
            str(RHO_PROVENANCE.relative_to(ROOT)),
            str(DECISION_POLICY.relative_to(ROOT)),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        fail(result.stderr.strip() or "git diff failed")
    changed = [line for line in result.stdout.splitlines() if line.strip()]
    if changed:
        fail(f"core files changed unexpectedly: {changed}")


def assert_no_forbidden() -> None:
    text = read(HTML)
    for term in ("api_key", "apikey", "secret", "token", "password", "Bearer", "稳赚", "必胜", "保证命中", "建议下注", "推荐投注"):
        if re.search(re.escape(term), text, re.I):
            fail(f"dashboard contains forbidden term: {term}")


def main() -> int:
    try:
        assert_api_discovery()
        assert_fixture_aliases()
        assert_html_backend_wiring()
        assert_display_policy()
        assert_core_unchanged()
        assert_no_forbidden()
    except (CheckError, Exception) as exc:  # noqa: BLE001
        print(f"W1 dashboard backend predict integration check FAIL: {exc}", file=sys.stderr)
        return 1
    print("W1 dashboard backend predict integration check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
