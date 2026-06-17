#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1 FiveDim Primary Read Selector (Stage F) — single research conclusion per match.

Emits exactly one decision per match: PRIMARY_READ / WAIT / SKIP / BLOCKED.
This is a RESEARCH-CONCLUSION selector, NOT a betting selector: PRIMARY_READ packages
the existing market-implied read (direction + bands) with data-quality + Stage-D factor
caveats. Per Stage C it claims no independent edge and changes no probability.

Read-only, offline. Decision uses pre-match fields only; actual_score is audit-only
(used_in_decision=false). Output is gitignored; no tracked file is modified.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "config/w1_primary_read_policy.json").read_text(encoding="utf-8"))
DASH = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
DADJ = ROOT / "state/w1_confidence_adjustment.json"
OUT = ROOT / "state/w1_primary_read.json"
SKIP_MIN_TOP = float(POLICY.get("skip_min_top_prob", 0.40))


def _dq_cn(overall):
    return {"partial": "偏弱", "ok": "可用", "good": "较好", "strong": "较好"}.get(str(overall), "未知")


def _digest(*parts):
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def decide(rec):
    """Pre-match-only decision; ignores the finished-match score entirely."""
    oxt = (rec.get("market_probability_panel") or {}).get("one_x_two") or {}
    ph, pd_, pa = oxt.get("home_win"), oxt.get("draw"), oxt.get("away_win")
    if ph is None or pd_ is None or pa is None or abs((oxt.get("sum_check") or 0) - 1.0) > 0.02:
        return "BLOCKED", ["市场 1X2 不可用或不自洽"], None
    top = max(ph, pd_, pa)
    finished = rec.get("status") == "finished"
    pg = bool(((rec.get("data_quality") or {}).get("play_guard") or {}).get("pass"))
    stage = str(rec.get("prediction_stage_cn") or "")
    early = ("早盘" in stage) or ("赛前观察" in stage)
    if (not finished) and early and (not pg) and (not rec.get("confirmed_lineup_available")):
        return "WAIT", ["关键赛前数据未确认(首发未确认、硬风控未放行),等赛前观察刷新"], top
    if top < SKIP_MIN_TOP:
        return "SKIP", [f"市场太均衡(最大类概率<{SKIP_MIN_TOP}),无足够稳定结论"], top
    return "PRIMARY_READ", [], top


def primary_read_text(rec, d_state):
    sv = rec.get("safe_view") or {}
    direction = rec.get("reference_direction") or (sv.get("favorite_side") or "市场读数")
    margin = ((sv.get("goal_difference_range") or {}).get("most_likely_margin_cn")) or "–"
    total = ((sv.get("total_goals_range") or {}).get("most_likely_band")) or "–"
    dq = _dq_cn((rec.get("data_quality") or {}).get("overall"))
    factor = {"insufficient": "独立支撑不足", "aligned": "与市场一致(无独立增量)",
              "divergent": "市场与历史因子背离,谨慎", "factor_missing": "市场读数不足"}.get(d_state, "独立支撑不足")
    pg = bool(((rec.get("data_quality") or {}).get("play_guard") or {}).get("pass"))
    guard = "W1硬风控已放行" if pg else "W1硬风控未放行(首发未确认)"
    return (f"{direction} · {margin} · 进球区间 {total} · 数据可信度{dq} · {factor} · {guard}"
            "（≈市场共识 · 非独立优势 · 非推介 · 别当真）")


def build_all():
    dash = json.loads(DASH.read_text(encoding="utf-8")).get("match_records", []) if DASH.is_file() else []
    dadj = {}
    if DADJ.is_file():
        for r in json.loads(DADJ.read_text(encoding="utf-8")).get("adjustments", []):
            dadj[str(r.get("fixture_id"))] = r.get("market_vs_factor")
    rows = []
    for rec in dash:
        fid = str(rec.get("fixture_id"))
        d_state = dadj.get(fid, "insufficient")
        decision, reasons, top = decide(rec)
        read_cn = primary_read_text(rec, d_state) if decision == "PRIMARY_READ" else None
        sv = rec.get("safe_view") or {}
        row = {
            "fixture_id": fid, "match": rec.get("match"),
            "decision": decision,
            "primary_read_cn": read_cn,
            "reasons_cn": reasons,
            "market_lean_cn": rec.get("reference_direction"),
            "margin_band_cn": ((sv.get("goal_difference_range") or {}).get("most_likely_margin_cn")),
            "total_band": ((sv.get("total_goals_range") or {}).get("most_likely_band")),
            "data_quality": (rec.get("data_quality") or {}).get("overall"),
            "w1_play_guard_pass": bool(((rec.get("data_quality") or {}).get("play_guard") or {}).get("pass")),
            "factor_state_stage_d": d_state,
            "basis": "market_implied", "independent_edge": False, "prob_unchanged": True,
            "locked_inputs_digest": _digest(rec.get("market_probability_panel"), sv.get("total_goals_range"),
                                            sv.get("goal_difference_range"), rec.get("prediction_stage_cn")),
            "audit": {"status": rec.get("status"),
                      "actual_score": rec.get("actual_score") if rec.get("status") == "finished" else None,
                      "used_in_decision": False},
        }
        rows.append(row)
    # one PRIMARY_READ per match holds by construction (one row per fixture)
    return {
        "stage": "W1_FIVEDIM_PRIMARY_READ_SELECTOR_F",
        "basis": "market_implied", "research_only": True, "production_wired": False,
        "is_betting_selector": False, "independent_edge_claimed": False, "prob_unchanged": True,
        "skip_min_top_prob": SKIP_MIN_TOP,
        "n": len(rows), "reads": rows,
    }


def main() -> int:
    payload = build_all()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    from collections import Counter
    dist = Counter(r["decision"] for r in payload["reads"])
    print(f"primary read built: n={payload['n']} decisions={dict(dist)} -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
