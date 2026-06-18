#!/usr/bin/env python3
"""Auto-Scout wrapper for the local W1 dashboard server.

This wrapper keeps the original ``w1_local_predict_server.py`` intact, but changes
local-development defaults so the dashboard button behaves as the user expects:

- manual refresh triggers the Scout/DeepSeek pre-match read by default;
- missing APIFOOTBALL_KEY degrades live API modules to cache/local data instead of
  blocking Scout, as long as DEEPSEEK_API_KEY/W1_SCOUT_API_KEY is available;
- served dashboard copy makes the button/top banner say that AI read generation is
  part of manual refresh.

Disable the default Scout trigger with ``W1_MANUAL_REFRESH_TRIGGER_SCOUT=0``.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import w1_local_predict_server as base  # noqa: E402

TEAM_CN = {
    "Czechia": "捷克",
    "Czech Republic": "捷克",
}

HTML_REPLACEMENTS = {
    "手动强刷基础数据": "手动强刷 + AI解读",
    "若服务端启用 W1_MANUAL_REFRESH_TRIGGER_SCOUT=1 且 key 齐备，会追加生成本场 Scout 解读。": (
        "手动强刷会刷新基础数据；若 DeepSeek key 可用，将追加生成本场 Scout 解读；"
        "实时 API 缺失时使用本地缓存，不伪造数据。"
    ),
    "Czechia": "捷克",
    "主 -": "未开赛",
}


def patch_dashboard_html(text: str) -> str:
    for old, new in HTML_REPLACEMENTS.items():
        text = text.replace(old, new)
    return text


def localize_team(value):
    return TEAM_CN.get(str(value or ""), value)


def patch_dashboard_payload(payload):
    data = copy.deepcopy(payload)
    records = data.get("match_records")
    if isinstance(records, list):
        for row in records:
            if not isinstance(row, dict):
                continue
            for side in ("home", "away"):
                raw_key = f"{side}_team"
                cn_key = f"{side}_team_cn"
                mapped = localize_team(row.get(raw_key))
                if mapped != row.get(raw_key):
                    row[cn_key] = mapped
            if row.get("home_team_cn") and row.get("away_team_cn"):
                row["match_cn"] = f"{row['home_team_cn']} vs {row['away_team_cn']}"
    return data


def manual_scout_enabled_default() -> bool:
    return os.environ.get("W1_MANUAL_REFRESH_TRIGGER_SCOUT", "1") != "0"


def scout_not_blocked_by_api_key(env: dict[str, str]) -> bool:
    """Manual Scout should not be blocked just because live football API is absent.

    The base data refresh modules already degrade to local/cache data when
    APIFOOTBALL_KEY is missing. Scout itself is run with W1_SCOUT_SKIP_FETCH=1 from
    manual refresh, so DeepSeek can still analyze the existing local bundle without
    fabricating live API values.
    """
    return True


class AutoScoutHandler(base.Handler):
    def _send_html_text(self, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - stdlib API
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"/", "/reports/dashboard/W1_VISUAL_DASHBOARD.html", "/W1_VISUAL_DASHBOARD.html"}:
            if base.DASHBOARD_HTML.is_file():
                self._send_html_text(patch_dashboard_html(base.DASHBOARD_HTML.read_text(encoding="utf-8")))
                return
        if path == "/dashboard-data":
            try:
                data = patch_dashboard_payload(base.load_json(base.DASHBOARD_DATA))
            except Exception as exc:  # noqa: BLE001 - preserve server API behavior
                self.send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self.send_json({"ok": True, "data": data})
            return
        return super().do_GET()


def main() -> None:
    os.environ.setdefault("W1_MANUAL_REFRESH_TRIGGER_SCOUT", "1")
    base.manual_scout_enabled = manual_scout_enabled_default
    base.api_football_key_available = scout_not_blocked_by_api_key
    base.Handler = AutoScoutHandler
    base.main()


if __name__ == "__main__":
    main()
