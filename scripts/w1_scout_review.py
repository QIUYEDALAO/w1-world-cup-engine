#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1_SCOUT post-match review.

Reads immutable pre-match Scout locks plus local finished results, then asks an
OpenAI-compatible model to write an honest post-match review. Reviews are runtime
state (`state/scout_reviews.jsonl`) and are never used to rewrite pre-match reads.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request

from w1_results_overlay import load_results_map

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "state/scout_lock.jsonl"
REVIEWS = ROOT / "state/scout_reviews.jsonl"

FORBIDDEN = ("投注", "下注", "资金", "稳赢", "稳赚", "必中", "必胜", "保证命中", "打败市场", "战胜市场")


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def digest_read(call: dict[str, Any]) -> str:
    blob = json.dumps(call, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def results_map() -> dict[str, dict[str, Any]]:
    return load_results_map()


def outcome(score: dict[str, Any]) -> str:
    h, a = score.get("home"), score.get("away")
    if not isinstance(h, int) or not isinstance(a, int):
        return "unknown"
    return "home" if h > a else "away" if a > h else "draw"


def provider_cfg() -> dict[str, str]:
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("W1_SCOUT_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY / W1_SCOUT_API_KEY not configured; no reviews written")
    return {
        "base_url": os.environ.get("W1_SCOUT_BASE_URL", "https://api.deepseek.com/chat/completions"),
        "model": os.environ.get("W1_SCOUT_MODEL", "deepseek-v4-pro"),
        "api_key": key,
    }


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    decoder = json.JSONDecoder()
    for idx, char in enumerate(cleaned):
        if char != "{":
            continue
        try:
            payload, _end = decoder.raw_decode(cleaned[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("model response did not contain JSON object")


def call_model(cfg: dict[str, str], prompt: str) -> dict[str, Any]:
    body = json.dumps({
        "model": cfg["model"],
        "temperature": 0.2,
        "max_tokens": 900,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "你是足球赛后复盘分析师。只做赛后对照,不许嘴硬,不许把赛后事实包装成赛前判断。只输出 JSON。"},
            {"role": "user", "content": prompt},
        ],
    }).encode("utf-8")
    req = request.Request(cfg["base_url"], data=body, headers={"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"})
    with request.urlopen(req, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return extract_json_object(str(payload["choices"][0]["message"]["content"]))


def validate_review(payload: dict[str, Any], expected_digest: str) -> list[str]:
    errors: list[str] = []
    for key in ("fixture_id", "review_cn", "honesty_label"):
        if key not in payload:
            errors.append(f"missing {key}")
    if payload.get("prematch_read_digest") != expected_digest:
        errors.append("prematch_read_digest mismatch")
    if payload.get("honesty_label") != "AI 复盘·赛后对照":
        errors.append("honesty_label must be AI 复盘·赛后对照")
    text = json.dumps(payload, ensure_ascii=False)
    for token in FORBIDDEN:
        if token in text:
            errors.append(f"forbidden term: {token}")
    return errors


def build_prompt(lock: dict[str, Any], result: dict[str, Any], digest: str) -> str:
    return (
        f"[fixture_id] {lock.get('fixture_id')}\n"
        f"[赛前锁定 digest] {digest}\n"
        f"[赛前解读原文] {json.dumps(lock.get('call'), ensure_ascii=False)}\n"
        f"[实际结果/本地赛果] {json.dumps(result, ensure_ascii=False)}\n"
        "请输出 JSON: fixture_id, prematch_read_digest, actual{score,outcome,key_stats}, "
        "review_cn, honesty_label。review_cn 必须诚实说明赛前读对了什么、读漏了什么、为什么。"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate W1_SCOUT post-match reviews from immutable locks and local results.")
    parser.add_argument("--fixture", action="append", help="Review selected fixture id; may be repeated.")
    parser.add_argument("--dry-run", action="store_true", help="List eligible reviews without calling model or writing state.")
    args = parser.parse_args()

    locks = read_jsonl(LOCK)
    results = results_map()
    done = {str(row.get("fixture_id")) for row in read_jsonl(REVIEWS)}
    wanted = set(args.fixture or [])
    eligible = [lock for lock in locks if str(lock.get("fixture_id")) in results and str(lock.get("fixture_id")) not in done and (not wanted or str(lock.get("fixture_id")) in wanted)]

    if args.dry_run:
        print(f"scout review dry-run: eligible={len(eligible)} output={REVIEWS.relative_to(ROOT)}")
        return 0
    if not eligible:
        print("scout review: no finished locked fixture awaiting review")
        return 0

    try:
        cfg = provider_cfg()
    except RuntimeError as exc:
        print(f"FAIL: {exc}")
        return 2

    pending: list[dict[str, Any]] = []
    for lock in eligible:
        fid = str(lock.get("fixture_id"))
        digest = lock.get("prematch_read_digest") or digest_read(lock.get("call") or {})
        result = results[fid]
        score = result.get("actual_score") or {}
        candidate = call_model(cfg, build_prompt(lock, result, digest))
        candidate["fixture_id"] = fid
        candidate["reviewed_at_utc"] = now()
        candidate["prematch_read_digest"] = digest
        candidate["actual"] = {
            "score": f"{score.get('home')}-{score.get('away')}",
            "outcome": outcome(score),
            "key_stats": result.get("key_stats") or {},
        }
        candidate["honesty_label"] = "AI 复盘·赛后对照"
        errors = validate_review(candidate, digest)
        if errors:
            raise RuntimeError(f"review validation failed for {fid}: {errors}")
        pending.append(candidate)

    REVIEWS.parent.mkdir(parents=True, exist_ok=True)
    with REVIEWS.open("a", encoding="utf-8") as fh:
        for candidate in pending:
            fh.write(json.dumps(candidate, ensure_ascii=False) + "\n")
    written = len(pending)
    print(f"scout review PASS: wrote {written} review(s) -> {REVIEWS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
