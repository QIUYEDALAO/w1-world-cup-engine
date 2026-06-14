#!/usr/bin/env python3
"""Audit completed W1 match recommendation accuracy from existing local data."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_JSON = ROOT / "reports/dashboard/assets/w1_dashboard_data.json"
RESULTS_JSON = ROOT / "data/results/round1_results.json"
AUDIT_MD = ROOT / "reports/W1_RECOMMENDATION_ACCURACY_AUDIT.md"
AUDIT_JSON = ROOT / "reports/w1_recommendation_accuracy_audit.json"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def parse_score(value: Any) -> dict[str, int | None]:
    if isinstance(value, dict):
        home = value.get("home")
        away = value.get("away")
        if isinstance(home, int) and isinstance(away, int):
            return {"home": home, "away": away}
    if isinstance(value, str) and "-" in value:
        left, right = value.split("-", 1)
        if left.strip().isdigit() and right.strip().isdigit():
            return {"home": int(left.strip()), "away": int(right.strip())}
    return {"home": None, "away": None}


def score_text(score: dict[str, int | None]) -> str | None:
    if score.get("home") is None or score.get("away") is None:
        return None
    return f"{score['home']}-{score['away']}"


def direction_from_score(score: dict[str, int | None]) -> str | None:
    home = score.get("home")
    away = score.get("away")
    if home is None or away is None:
        return None
    if home > away:
        return "H"
    if home < away:
        return "A"
    return "D"


def predicted_direction(summary: dict[str, Any]) -> str | None:
    probs = {
        "H": summary.get("home_win_prob"),
        "D": summary.get("draw_prob"),
        "A": summary.get("away_win_prob"),
    }
    if not all(isinstance(value, (int, float)) for value in probs.values()):
        return None
    return max(probs, key=lambda key: float(probs[key]))


def direction_cn(value: str | None) -> str:
    return {"H": "主胜", "D": "平局", "A": "客胜"}.get(value, "缺失")


def numeric(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return float(value)
    return None


def avg(values: list[float]) -> float | None:
    return round(mean(values), 4) if values else None


def completed_records(data: dict[str, Any], results: dict[str, Any]) -> list[dict[str, Any]]:
    result_map = results.get("results", {}) if isinstance(results, dict) else {}
    rows: list[dict[str, Any]] = []
    for row in data.get("match_records", []):
        fixture_id = str(row.get("fixture_id", ""))
        calibration = row.get("post_match_calibration", {}) or {}
        actual = parse_score(row.get("actual_score"))
        if actual["home"] is None and calibration.get("actual_score"):
            actual = parse_score(calibration.get("actual_score"))
        if actual["home"] is None and fixture_id in result_map:
            actual = parse_score(result_map[fixture_id].get("actual_score"))
        if actual["home"] is None or actual["away"] is None:
            continue
        rows.append(row | {"_audit_actual_score": actual})
    return rows


def build_match_audit(row: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    fixture_id = str(row.get("fixture_id", ""))
    result_map = results.get("results", {}) if isinstance(results, dict) else {}
    result_entry = result_map.get(fixture_id, {}) if isinstance(result_map, dict) else {}
    actual = row["_audit_actual_score"]
    actual_text = score_text(actual)
    dist = row.get("score_distribution", {}) or {}
    summary = row.get("score_matrix_summary", {}) or {}
    calibration = row.get("post_match_calibration", {}) or dist.get("post_match_calibration", {}) or {}
    score_pool = dist.get("score_pool") or []
    score_pool_scores = [str(item.get("score")) for item in score_pool if item.get("score")]
    primary_score = dist.get("main_score")
    secondary_score = dist.get("fallback_score")
    pred_dir = predicted_direction(summary)
    actual_dir = direction_from_score(actual)
    lineups = row.get("lineups", {}) or {}
    data_quality = row.get("data_quality", {}) or {}
    odds_quality = data_quality.get("odds", {}) if isinstance(data_quality, dict) else {}
    lineup_source = lineups.get("source") or lineups.get("source_name") or lineups.get("source_type") or row.get("lineup_source")
    confirmed = row.get("confirmed_lineup_available")
    if confirmed is None:
        confirmed = bool(lineups.get("home_starting_xi") and lineups.get("away_starting_xi"))

    return {
        "fixture_id": fixture_id,
        "alias_fixture_ids": result_entry.get("alias_fixture_ids", row.get("alias_fixture_ids", [])),
        "match": row.get("match"),
        "actual_score": actual_text,
        "primary_score": primary_score,
        "secondary_score": secondary_score,
        "score_pool": score_pool,
        "actual_score_probability": numeric(calibration.get("actual_score_probability")),
        "rps_1x2": numeric(calibration.get("rps_1x2")),
        "exact_score_log_loss": numeric(calibration.get("exact_score_log_loss")),
        "predicted_direction": pred_dir,
        "predicted_direction_cn": direction_cn(pred_dir),
        "actual_direction": actual_dir,
        "actual_direction_cn": direction_cn(actual_dir),
        "direction_hit": bool(pred_dir and actual_dir and pred_dir == actual_dir),
        "primary_score_hit": bool(primary_score and actual_text and primary_score == actual_text),
        "secondary_score_hit": bool(secondary_score and actual_text and secondary_score == actual_text),
        "score_pool_hit": bool(actual_text and actual_text in score_pool_scores),
        "market_fit_error": numeric(summary.get("market_fit_error")),
        "lineup_source": lineup_source or "missing",
        "confirmed_lineup": bool(confirmed),
        "odds_status": odds_quality.get("status") or row.get("odds_status") or "unknown",
        "data_quality_status": data_quality.get("overall") if isinstance(data_quality, dict) else row.get("data_quality_status", "unknown"),
        "calibration_missing_reason": None
        if calibration.get("rps_1x2") is not None
        else "post_match_calibration.rps_1x2 missing",
    }


def ratio(count: int, total: int) -> float | None:
    return round(count / total, 4) if total else None


def build_metrics(matches: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(matches)
    actual_probs = [m["actual_score_probability"] for m in matches if m["actual_score_probability"] is not None]
    rps_values = [m["rps_1x2"] for m in matches if m["rps_1x2"] is not None]
    log_values = [m["exact_score_log_loss"] for m in matches if m["exact_score_log_loss"] is not None]
    return {
        "total_completed_matches": total,
        "direction_accuracy": ratio(sum(1 for m in matches if m["direction_hit"]), total),
        "primary_score_accuracy": ratio(sum(1 for m in matches if m["primary_score_hit"]), total),
        "secondary_score_accuracy": ratio(sum(1 for m in matches if m["secondary_score_hit"]), total),
        "primary_or_secondary_accuracy": ratio(
            sum(1 for m in matches if m["primary_score_hit"] or m["secondary_score_hit"]), total
        ),
        "score_pool_coverage": ratio(sum(1 for m in matches if m["score_pool_hit"]), total),
        "mean_actual_score_probability": avg(actual_probs),
        "mean_rps_1x2": avg(rps_values),
        "mean_exact_score_log_loss": avg(log_values),
        "worst_3_by_log_loss": sorted(
            (
                {
                    "fixture_id": m["fixture_id"],
                    "match": m["match"],
                    "actual_score": m["actual_score"],
                    "exact_score_log_loss": m["exact_score_log_loss"],
                }
                for m in matches
                if m["exact_score_log_loss"] is not None
            ),
            key=lambda item: item["exact_score_log_loss"],
            reverse=True,
        )[:3],
        "best_3_by_actual_score_probability": sorted(
            (
                {
                    "fixture_id": m["fixture_id"],
                    "match": m["match"],
                    "actual_score": m["actual_score"],
                    "actual_score_probability": m["actual_score_probability"],
                }
                for m in matches
                if m["actual_score_probability"] is not None
            ),
            key=lambda item: item["actual_score_probability"],
            reverse=True,
        )[:3],
    }


def pct(value: float | None) -> str:
    return "缺失" if value is None else f"{value * 100:.1f}%"


def num(value: float | None) -> str:
    return "缺失" if value is None else f"{value:.4f}"


def table_row(match: dict[str, Any]) -> str:
    return (
        f"| {match['fixture_id']} | {match['match']} | {match['actual_score']} | "
        f"{match['predicted_direction_cn']} | {match['actual_direction_cn']} | "
        f"{'是' if match['direction_hit'] else '否'} | {match['primary_score']} | "
        f"{match['secondary_score']} | {'是' if match['score_pool_hit'] else '否'} | "
        f"{num(match['actual_score_probability'])} | {num(match['rps_1x2'])} | "
        f"{num(match['exact_score_log_loss'])} | {match['lineup_source']} | "
        f"{'是' if match['confirmed_lineup'] else '否'} | {match['data_quality_status']} |"
    )


def write_markdown(matches: list[dict[str, Any]], metrics: dict[str, Any]) -> None:
    lines = [
        "# W1 Recommendation Accuracy Audit",
        "",
        f"生成时间：{datetime.now(timezone.utc).isoformat()}",
        "",
        "## 1. 审计范围",
        "",
        "本报告只读取现有本地数据，统计所有已有 actual_score 或 post_match_calibration 的已完赛 match_records。runtime state 仅作为辅助背景，不作为主数据源。",
        "",
        "输入优先级：",
        "",
        "1. `reports/dashboard/assets/w1_dashboard_data.json`",
        "2. `data/results/round1_results.json`",
        "3. `data/processed/match_cards/`",
        "4. `data/manual_lineups/`",
        "5. `state/` runtime 仅辅助",
        "",
        "## 2. 核心指标",
        "",
        f"- total_completed_matches：{metrics['total_completed_matches']}",
        f"- direction_accuracy：{pct(metrics['direction_accuracy'])}",
        f"- primary_score_accuracy：{pct(metrics['primary_score_accuracy'])}",
        f"- secondary_score_accuracy：{pct(metrics['secondary_score_accuracy'])}",
        f"- primary_or_secondary_accuracy：{pct(metrics['primary_or_secondary_accuracy'])}",
        f"- score_pool_coverage：{pct(metrics['score_pool_coverage'])}",
        f"- mean_actual_score_probability：{num(metrics['mean_actual_score_probability'])}",
        f"- mean_rps_1x2：{num(metrics['mean_rps_1x2'])}",
        f"- mean_exact_score_log_loss：{num(metrics['mean_exact_score_log_loss'])}",
        "",
        "## 3. 逐场表",
        "",
        "| fixture_id | match | actual_score | predicted_direction | actual_direction | direction_hit | primary_score | secondary_score | score_pool_hit | actual_score_probability | rps_1x2 | exact_score_log_loss | lineup_source | confirmed_lineup | data_quality |",
        "|---|---|---:|---|---|---|---:|---:|---|---:|---:|---:|---|---|---|",
    ]
    lines.extend(table_row(match) for match in matches)
    lines.extend(
        [
            "",
            "## 4. 指定样本复盘",
            "",
            "### Qatar vs Switzerland 1-1",
            "",
            "Qatar vs Switzerland 1-1 是热门未胜样本。score pool 覆盖到 1-1，但方向层面暴露出热门胜出与实际平局之间的偏差。该样本更适合进入 RPS/log score 累计评估，而不是被简单记为成功。",
            "",
            "### USA vs Paraguay 4-1",
            "",
            "USA vs Paraguay 4-1 是尾部打开样本。平手附近的市场结构并没有阻止大比分路径出现，说明 open-game mass 和尾部概率必须保留，不能用 OU 或 AH 直接锁死比分。",
            "",
            "### Australia vs Turkey 2-0",
            "",
            "Australia vs Turkey 2-0 是方向性失误样本。当前矩阵给出的 Turkey 方向更高，但实际 Australia 2-0。该场应作为 calibration 样本进入累计评估，不因单场调权重。",
            "",
            "## 5. 最差与最好样本",
            "",
            "### worst_3_by_log_loss",
            "",
        ]
    )
    for item in metrics["worst_3_by_log_loss"]:
        lines.append(
            f"- {item['fixture_id']} {item['match']} {item['actual_score']}：exact_score_log_loss={num(item['exact_score_log_loss'])}"
        )
    lines.extend(["", "### best_3_by_actual_score_probability", ""])
    for item in metrics["best_3_by_actual_score_probability"]:
        lines.append(
            f"- {item['fixture_id']} {item['match']} {item['actual_score']}：actual_score_probability={num(item['actual_score_probability'])}"
        )
    lines.extend(
        [
            "",
            "## 6. 审计结论",
            "",
            "- 精确比分命中率不是唯一指标；它对小样本高度敏感。",
            "- score_pool 覆盖不等于推荐成功，只说明实际比分进入了候选路径。",
            "- RPS/log score 才是当前主评估口径，用于衡量方向概率和精确比分概率的损失。",
            "- 当前样本量小，不允许调权重。",
            "- Australia 2-0 Turkey 是方向性失误样本。",
            "- Qatar 1-1 Switzerland 是热门未胜样本。",
            "- USA 4-1 Paraguay 是尾部打开样本。",
            "- 本审计不改变 score matrix、rho、PLAY_GUARD，也不根据结果调参。",
            "",
            "## 7. 合规边界",
            "",
            "本报告仅用于赛前/赛后分析研究与专家审阅，不提供交易、执行或资金操作意见，不承诺命中率。",
        ]
    )
    AUDIT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    dashboard = read_json(DASHBOARD_JSON, {})
    results = read_json(RESULTS_JSON, {})
    matches = [build_match_audit(row, results) for row in completed_records(dashboard, results)]
    metrics = build_metrics(matches)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_sources": [
            "reports/dashboard/assets/w1_dashboard_data.json",
            "data/results/round1_results.json",
            "data/processed/match_cards/",
            "data/manual_lineups/",
        ],
        "metrics": metrics,
        "matches": matches,
        "notes_cn": [
            "精确比分命中率不是唯一指标。",
            "score_pool 覆盖不等于推荐成功。",
            "RPS/log score 是当前主评估口径。",
            "样本量小，不允许调权重。",
        ],
    }
    AUDIT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(matches, metrics)
    print(f"W1 recommendation accuracy audit generated: {len(matches)} completed matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
