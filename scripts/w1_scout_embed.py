#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Embed W1_SCOUT DeepSeek reads/reviews into the dashboard.

Reads state/w1_scout_calls.json, state/scout_reviews.jsonl, and
state/scout_calibration.json, then replaces dashboard embedded blobs idempotently.
Display-only: does not touch the W1 market base, λ, score matrix, or build pipeline.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
CALLS = ROOT / "state/w1_scout_calls.json"
REVIEWS = ROOT / "state/scout_reviews.jsonl"
CALIBRATION = ROOT / "state/scout_calibration.json"
TAG_RE = re.compile(r'<script id="w1-scout-calls" type="application/json">.*?</script>', re.S)
REVIEWS_TAG_RE = re.compile(r'<script id="w1-scout-reviews" type="application/json">.*?</script>', re.S)
CALIBRATION_TAG_RE = re.compile(r'<script id="w1-scout-calibration" type="application/json">.*?</script>', re.S)


def read_reviews() -> list[dict]:
    if not REVIEWS.is_file():
        return []
    return [json.loads(line) for line in REVIEWS.read_text(encoding="utf-8").splitlines() if line.strip()]


def upsert_tag(html: str, tag_id: str, payload: dict, regex: re.Pattern[str]) -> str:
    blob = json.dumps(payload, ensure_ascii=False)
    if "</script>" in blob:
        blob = blob.replace("</script>", "<\\/script>")
    new_tag = f'<script id="{tag_id}" type="application/json">{blob}</script>'
    if regex.search(html):
        return regex.sub(lambda _m: new_tag, html, count=1)
    return html.replace('<script id="w1-data" type="application/json">',
                        new_tag + "\n" + '<script id="w1-data" type="application/json">', 1)


def main() -> int:
    calls = json.loads(CALLS.read_text(encoding="utf-8")) if CALLS.is_file() else {"calls": []}
    generated_by = calls.get("generated_by")
    if generated_by == "deepseek:deepseek-v4-pro":
        generated_by = "deepseek:deepseek-pro"
    html = HTML.read_text(encoding="utf-8")
    html = upsert_tag(html, "w1-scout-calls", {"generated_by": generated_by, "calls": calls.get("calls", [])}, TAG_RE)
    html = upsert_tag(html, "w1-scout-reviews", {"reviews": read_reviews()}, REVIEWS_TAG_RE)
    calibration = json.loads(CALIBRATION.read_text(encoding="utf-8")) if CALIBRATION.is_file() else {"schema_version": "W1_SCOUT_CALIBRATION_V1", "note_cn": "这是 Scout 解读的自我体检与校准,不是战胜市场的证据。"}
    html = upsert_tag(html, "w1-scout-calibration", calibration, CALIBRATION_TAG_RE)
    HTML.write_text(html, encoding="utf-8")
    print(f"embedded {len(calls.get('calls', []))} scout reads into dashboard ({HTML.relative_to(ROOT)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
