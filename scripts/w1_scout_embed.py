#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Embed W1_SCOUT DeepSeek calls into the dashboard so the AI 分析师 panel can render.

Reads state/w1_scout_calls.json and replaces the <script id="w1-scout-calls"> blob in
the dashboard HTML (idempotent). Display-only: does not touch the W1 market base, λ,
score matrix, or build pipeline. Run after the analyst, before opening/serving the page.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "reports/dashboard/W1_VISUAL_DASHBOARD.html"
CALLS = ROOT / "state/w1_scout_calls.json"
TAG_RE = re.compile(r'<script id="w1-scout-calls" type="application/json">.*?</script>', re.S)


def main() -> int:
    calls = json.loads(CALLS.read_text(encoding="utf-8")) if CALLS.is_file() else {"calls": []}
    generated_by = calls.get("generated_by")
    if generated_by == "deepseek:deepseek-v4-pro":
        generated_by = "deepseek:deepseek-pro"
    blob = json.dumps({"generated_by": generated_by, "calls": calls.get("calls", [])}, ensure_ascii=False)
    if "</script>" in blob:
        blob = blob.replace("</script>", "<\\/script>")  # never break out of the tag
    html = HTML.read_text(encoding="utf-8")
    new_tag = f'<script id="w1-scout-calls" type="application/json">{blob}</script>'
    if TAG_RE.search(html):
        html = TAG_RE.sub(lambda _m: new_tag, html, count=1)
    else:
        html = html.replace('<script id="w1-data" type="application/json">',
                            new_tag + "\n" + '<script id="w1-data" type="application/json">', 1)
    HTML.write_text(html, encoding="utf-8")
    print(f"embedded {len(calls.get('calls', []))} scout calls into dashboard ({HTML.relative_to(ROOT)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
