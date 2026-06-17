#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Checker for W1_SCOUT (AI analyst loop).

Guards: bundle is pre-match-only (no post-match leakage); every AI call is bold but
honest (states a stance, gives real reasoning — not bare translation; FADE_MARKET only
at HIGH conviction; carries an 'AI 观点' honesty label; independent_edge=false; no
betting/guarantee wording). Only ADDS assertions; each safety rule has a reverse test.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_P = ROOT / "config/w1_scout_policy.json"
SCHEMA_P = ROOT / "schemas/w1_scout_bundle_schema.json"
BUNDLE_MOD = ROOT / "scripts/w1_scout_bundle.py"
FETCHER = ROOT / "scripts/w1_scout_fetch_api_football.py"
ANALYST = ROOT / "scripts/w1_scout_analyst.py"
BUNDLES_P = ROOT / "state/w1_scout_bundles.json"
CALLS_P = ROOT / "state/w1_scout_calls.json"
TRACK_P = ROOT / "state/scout_track_record.json"
LESSONS_P = ROOT / "state/scout_lessons.md"
AUDIT_P = ROOT / "state/scout_audit.jsonl"
LOCK_P = ROOT / "state/scout_lock.jsonl"
SCOUT_DIR = ROOT / "data/scout"

errors: list[str] = []


def fail(m):
    errors.append(m)


def validate_call(c: dict, policy: dict) -> list[str]:
    errs: list[str] = []
    for f in policy["call_required_fields"]:
        if f not in c:
            errs.append(f"missing field {f}")
    call = c.get("call") or {}
    for f in policy["call_subfields"]["call"]:
        if f not in call:
            errs.append(f"call.{f} missing")
    md = c.get("market_divergence") or {}
    for f in policy["call_subfields"]["market_divergence"]:
        if f not in md:
            errs.append(f"market_divergence.{f} missing")
    stance = md.get("stance")
    if stance not in policy["stances"]:
        errs.append(f"invalid stance {stance}")
    # not-just-translation: must give real reasoning + factors
    if not (md.get("why_cn") and (c.get("key_factors_cn") or [])):
        errs.append("bare translation rejected: need why_cn + key_factors_cn")
    conv = c.get("conviction")
    if conv not in policy["conviction_levels"]:
        errs.append(f"invalid conviction {conv}")
    # boldness gates (MEDIUM dial)
    if stance == "FADE_MARKET" and conv != "HIGH":
        errs.append("FADE_MARKET requires conviction=HIGH")
    if stance == "LEAN_DIFFERENT" and conv not in ("MEDIUM", "HIGH"):
        errs.append("LEAN_DIFFERENT requires conviction>=MEDIUM")
    if policy["honesty"]["honesty_label_required_substr"] not in str(c.get("honesty_label", "")):
        errs.append("honesty_label must contain 'AI 观点'")
    if c.get("independent_edge") is not False:
        errs.append("independent_edge must be false")
    text = json.dumps(c, ensure_ascii=False)
    for t in policy["forbidden_terms"]:
        if t in text:
            errs.append(f"forbidden term: {t}")
    return errs


def bundle_leak(bundles, forbidden) -> list:
    hits = []
    for b in bundles:
        low = json.dumps(b, ensure_ascii=False).lower()
        for f in forbidden:
            if f.lower() in low:
                hits.append((b.get("fixture_id"), f))
        if b.get("asof_pre_kickoff") is not True:
            hits.append((b.get("fixture_id"), "asof_pre_kickoff!=true"))
    return hits


def validate_scout_payload(payload: dict, label: str, forbidden: list[str]) -> list[str]:
    errs: list[str] = []
    for key in ("fixture_id", "asof_pre_kickoff", "availability"):
        if key not in payload:
            errs.append(f"{label} missing {key}")
    if payload.get("asof_pre_kickoff") is not True:
        errs.append(f"{label} asof_pre_kickoff must be true")
    availability = payload.get("availability") or {}
    if not isinstance(availability, dict):
        errs.append(f"{label} availability must be object")
    else:
        bad = {k: v for k, v in availability.items() if v not in {"available", "partial", "missing"}}
        if bad:
            errs.append(f"{label} invalid availability values: {bad}")
    leaks = bundle_leak([payload], forbidden)
    for _, field in leaks:
        errs.append(f"{label} leaked post-match field: {field}")
    return errs


def validate_scout_file(path: Path, forbidden: list[str]) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path.relative_to(ROOT)} invalid JSON: {exc}"]
    errs = validate_scout_payload(payload, path.relative_to(ROOT).as_posix(), forbidden)
    return errs


def count_jsonl_rows(path: Path) -> int:
    rows = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows += 1
    return rows


def validate_memory_consistency(track: dict, audit_rows: int) -> list[str]:
    overall = track.get("overall") or {}
    if "n" not in overall:
        return ["track_record overall.n missing"]
    if overall.get("n") != audit_rows:
        return [f"track_record overall.n={overall.get('n')} does not match scout_audit rows={audit_rows}"]
    return []


def main() -> int:
    for p in (POLICY_P, SCHEMA_P, BUNDLE_MOD, FETCHER, ANALYST, BUNDLES_P, TRACK_P, LESSONS_P, AUDIT_P, LOCK_P):
        if not p.is_file():
            fail(f"missing artifact: {p.relative_to(ROOT)}")
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print("W1 scout check FAIL")
        return 1

    policy = json.loads(POLICY_P.read_text(encoding="utf-8"))
    forbidden_pm = policy["leakage"]["forbidden_postmatch_fields"]
    bundles = json.loads(BUNDLES_P.read_text(encoding="utf-8")).get("bundles", [])

    # bundle source must not read post-match results
    src = BUNDLE_MOD.read_text(encoding="utf-8")
    for tok in ("actual_score", "fulltime", "ft_score", "post_match_calibration"):
        # allowed only inside the leakage-guard comment, not as a field read
        if f'rec.get("{tok}")' in src or f"rec['{tok}']" in src:
            fail(f"bundle assembler reads post-match field: {tok}")

    fetcher = FETCHER.read_text(encoding="utf-8")
    for token in ("SCOUT_DIR", "data/scout", "load_api_key", "APIFOOTBALL_", "OPENCLAW_APIFOOTBALL_KEY"):
        if token not in fetcher:
            fail(f"fetcher missing token: {token}")
    for token in ("/fixtures?team=&season=&status=FT", "/fixtures/statistics?fixture=", "dt < kickoff"):
        if token not in fetcher:
            fail(f"fetcher missing pre-match rolling-data guard token: {token}")
    for token in ("--retries", "api-football retry", "failed fixtures after retries"):
        if token not in fetcher:
            fail(f"fetcher missing transient retry/continue guard token: {token}")
    for token in ("FORBIDDEN_POSTMATCH_KEYS", "strip_forbidden_postmatch_fields", "build_api_pred"):
        if token not in fetcher:
            fail(f"fetcher missing api response post-match scrub token: {token}")
    for token in ("external_api_prediction", "third_party_model", "not_independent_edge"):
        if token not in fetcher:
            fail(f"api_pred must be labelled as third-party comparison only: {token}")
    if "write_json(RESULTS" in fetcher or "RESULTS_JSON" in fetcher:
        fail("fetcher must not write result ledger")
    if "w1_score_engine" in fetcher or "DEFAULT_RHO" in fetcher:
        fail("fetcher must not import/alter score engine")

    analyst = ANALYST.read_text(encoding="utf-8")
    for token in (
        "DEEPSEEK_API_KEY",
        "W1_SCOUT_LLM",
        "W1_SCOUT_BASE_URL",
        "https://api.deepseek.com/chat/completions",
        "deepseek-v4-pro",
        "validate_call",
        "state/w1_scout_calls.json",
        "honesty_label",
        "independent_edge",
        "--dry-run",
    ):
        if token not in analyst:
            fail(f"analyst missing token: {token}")
    for token in ("actual_score", "fulltime", "ft_score", "post_match_calibration", "w1_score_engine", "DEFAULT_RHO"):
        if token in analyst:
            fail(f"analyst must not read/use redline or post-match token: {token}")
    if "https://api.anthropic.com" in analyst or "ANTHROPIC_API_KEY" in analyst:
        fail("analyst must follow the T5 OpenAI-compatible route, not Anthropic-only routes")
    if "deepseek-chat" in analyst:
        fail("analyst must use fixed DeepSeek-V4-Pro (API id: deepseek-v4-pro) for the DeepSeek route")

    # bundle leakage
    leaks = bundle_leak(bundles, forbidden_pm)
    if leaks:
        fail(f"scout bundle post-match leakage: {leaks[:5]}")
    if len(bundles) < 1:
        fail("no scout bundles built")
    for b in bundles:
        if (b.get("availability") or {}).get("market") not in {"available", "partial", "missing"}:
            fail(f"bundle {b.get('fixture_id')} availability.market missing or invalid")

    if SCOUT_DIR.is_dir():
        for path in sorted(SCOUT_DIR.glob("*.json")):
            for err in validate_scout_file(path, forbidden_pm):
                fail(err)

    # growth files structure
    track = json.loads(TRACK_P.read_text(encoding="utf-8"))
    for k in ("overall", "by_conviction", "by_stance", "updated_at"):
        if k not in track:
            fail(f"track_record missing section {k}")
    audit_rows = count_jsonl_rows(AUDIT_P)
    for err in validate_memory_consistency(track, audit_rows):
        fail(err)
    lessons_text = LESSONS_P.read_text(encoding="utf-8").strip()
    if not lessons_text:
        fail("scout_lessons.md must be non-empty")
    for t in policy["forbidden_terms"]:
        if t in lessons_text:
            fail(f"scout_lessons.md contains forbidden term: {t}")
    for memory_path in (AUDIT_P, TRACK_P, LESSONS_P, LOCK_P):
        text = memory_path.read_text(encoding="utf-8")
        for secret_token in ("DEEPSEEK_API_KEY", "APIFOOTBALL_KEY", "OPENCLAW_APIFOOTBALL_KEY", "Bearer ", "sk-"):
            if secret_token in text:
                fail(f"Scout memory file contains secret-like token {secret_token}: {memory_path.relative_to(ROOT)}")

    # calls (validate if present)
    n_calls = 0
    if CALLS_P.is_file():
        calls = json.loads(CALLS_P.read_text(encoding="utf-8")).get("calls", [])
        n_calls = len(calls)
        seen = set()
        for c in calls:
            fid = c.get("fixture_id")
            if fid in seen:
                fail(f"duplicate call for fixture {fid}")
            seen.add(fid)
            for e in validate_call(c, policy):
                fail(f"call {fid}: {e}")

    # --- reverse tests ---
    base = {"fixture_id": "X", "call": {"outcome_lean": "主", "scoreline_lean": "1-0", "confidence": 0.5},
            "market_divergence": {"stance": "AGREE", "where_cn": "-", "why_cn": "市场与近况一致"},
            "key_factors_cn": ["近况"], "conviction": "LOW",
            "track_record_context_cn": "暂无", "honesty_label": "AI 观点·未验证·仅研究·可能错",
            "independent_edge": False}
    if validate_call(base, policy):
        fail("reverse: a clean AGREE call should pass")
    bad_fade = dict(base, market_divergence={"stance": "FADE_MARKET", "where_cn": "x", "why_cn": "y"}, conviction="LOW")
    if not validate_call(bad_fade, policy):
        fail("reverse: FADE_MARKET at LOW conviction must be rejected")
    bare = dict(base, market_divergence={"stance": "AGREE", "where_cn": "-", "why_cn": ""}, key_factors_cn=[])
    if not validate_call(bare, policy):
        fail("reverse: bare translation (no why/factors) must be rejected")
    betting = dict(base, key_factors_cn=["稳赢"])
    if not validate_call(betting, policy):
        fail("reverse: forbidden betting term must be caught")
    if not bundle_leak([{"fixture_id": "Z", "asof_pre_kickoff": True, "actual_score": "2-1"}], forbidden_pm):
        fail("reverse: a bundle with actual_score must be caught")
    bad_scout = {"fixture_id": "Z", "asof_pre_kickoff": False, "availability": {"form": "made_up"}}
    if not validate_scout_payload(bad_scout, "reverse_bad_scout", forbidden_pm):
        fail("reverse: bad scout file shape must be catchable")
    if not validate_memory_consistency({"overall": {"n": audit_rows + 1}}, audit_rows):
        fail("reverse: memory n/audit row mismatch must be caught")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"W1 scout check FAIL ({len(errors)})")
        return 1
    print(f"W1 scout check PASS (bundles={len(bundles)}, calls={n_calls}, audit_rows={audit_rows}, no leakage, "
          "bold-but-honest call contract, memory consistent, FADE gated at HIGH conviction, no betting wording)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
