#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1_S0 output safe-view checker.

Validates the display-only safe view without asserting any model change:
  1. every ready match_record has safe_view with total/margin ranges + tail_mass.
  2. tail_mass separates favorite_loss (true 热门输) from blowout_margin_3_plus (净胜≥3).
  3. recommendation output policy intact: primary unique, secondary <= 1.
  4. HTML: expert区 default folded; the old mislabel wiring is gone and the
     corrected scene labels are present.
  5. no betting / money / hit-rate promissory wording.

It does NOT recompute the model; model fingerprint invariance is covered by
check_w1_score_matrix / check_w1_rho_calibration.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"

# Promissory terms that must never appear (negated disclaimers are checked separately).
FORBIDDEN = ["稳赚", "必中", "保证命中", "投注建议", "跟单", "下注", "资金管理", "包赢", "稳胆"]

errors: list[str] = []


def fail(m: str) -> None:
    errors.append(m)


def main() -> int:
    data = json.loads(DASH.read_text(encoding="utf-8"))
    html = HTML.read_text(encoding="utf-8")
    records = data.get("match_records", [])
    if not records:
        fail("no match_records in dashboard data")

    ready = 0
    for r in records:
        fid = r.get("fixture_id")
        sv = r.get("safe_view") or {}
        st = sv.get("status")
        if st not in ("ready", "skipped"):
            fail(f"{fid}: safe_view.status invalid ({st})")
            continue
        if st != "ready":
            continue
        ready += 1
        # (1) range fields
        tg = sv.get("total_goals_range") or {}
        for k in ("band_0_1", "band_2_3", "band_4_plus", "most_likely_band"):
            if tg.get(k) is None:
                fail(f"{fid}: safe_view.total_goals_range missing {k}")
        gd = sv.get("goal_difference_range") or {}
        for k in ("draw", "favorite_win_by_1", "favorite_win_by_3_plus", "most_likely_margin_cn"):
            if gd.get(k) is None:
                fail(f"{fid}: safe_view.goal_difference_range missing {k}")
        # (2) tail_mass separates favorite_loss from blowout
        tm = sv.get("tail_mass") or {}
        if tm.get("favorite_loss") is None or tm.get("blowout_margin_3_plus") is None:
            fail(f"{fid}: safe_view.tail_mass must expose favorite_loss AND blowout_margin_3_plus")
        if not sv.get("distribution_shape_summary_cn"):
            fail(f"{fid}: safe_view.distribution_shape_summary_cn missing")

        # (3) output policy intact
        rv = r.get("recommendation_view") or {}
        ps, ss = rv.get("primary_score"), rv.get("secondary_score")
        if ps is not None and not isinstance(ps, str):
            fail(f"{fid}: primary_score must be a single value (got {type(ps).__name__})")
        if ss is not None and not isinstance(ss, str):
            fail(f"{fid}: secondary_score must be at most one value")
        if ps and ss and ps == ss:
            fail(f"{fid}: secondary_score must differ from primary_score")

    if ready == 0:
        fail("no ready safe_view found")

    # (4) HTML checks
    if "#expert{display:none}" not in html.replace(" ", ""):
        fail("expert区 must default to display:none")
    if "sms.collapse_mass" in html and "热门输" in html.split("sms.collapse_mass")[0][-80:]:
        fail("old mislabel wiring '热门输 <- collapse_mass(blowout)' still present")
    if "热门被翻盘（热门输）" not in html or "tm.favorite_loss" not in html:
        fail("corrected '热门被翻盘（热门输）' (favorite_loss) scene row missing")
    if "大胜（净胜≥3）" not in html:
        fail("corrected '大胜（净胜≥3）' (blowout) scene row missing")
    if "不构成收益承诺" not in html:
        fail("safe disclaimer '不构成收益承诺' missing from dashboard")

    # (5) no promissory wording anywhere in dashboard data + html
    blob = json.dumps(data, ensure_ascii=False) + html
    for t in FORBIDDEN:
        if t in blob:
            fail(f"forbidden promissory term present: {t}")

    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        print(f"W1 output safe-view check FAIL ({len(errors)} error(s))")
        return 1
    print(f"W1 output safe-view check PASS (ready_safe_view={ready}/{len(records)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
