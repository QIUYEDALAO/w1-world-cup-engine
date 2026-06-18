#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Checker for W1_SCOUT (AI analyst loop).

Guards: bundle is pre-match-only (no post-match leakage); every AI output is a
structured match read, not a prediction selector (has tilt/watch points/risks,
uses honest score-band language, carries an 'AI 解读' honesty label,
independent_edge=false, and avoids betting/guarantee/edge wording). Only ADDS
assertions; each safety rule has a reverse test.
"""
from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from w1_results_overlay import load_results_map  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
POLICY_P = ROOT / "config/w1_scout_policy.json"
SCHEMA_P = ROOT / "schemas/w1_scout_bundle_schema.json"
BUNDLE_MOD = ROOT / "scripts/w1_scout_bundle.py"
FETCHER = ROOT / "scripts/w1_scout_fetch_api_football.py"
ANALYST = ROOT / "scripts/w1_scout_analyst.py"
REVIEW_MOD = ROOT / "scripts/w1_scout_review.py"
CALIBRATION_MOD = ROOT / "scripts/w1_scout_calibration.py"
BUNDLES_P = ROOT / "state/w1_scout_bundles.json"
CALLS_P = ROOT / "state/w1_scout_calls.json"
TRACK_P = ROOT / "state/scout_track_record.json"
LESSONS_P = ROOT / "state/scout_lessons.md"
AUDIT_P = ROOT / "state/scout_audit.jsonl"
LOCK_P = ROOT / "state/scout_lock.jsonl"
REVIEWS_P = ROOT / "state/scout_reviews.jsonl"
SCOUT_DIR = ROOT / "data/scout"

errors: list[str] = []

TAIL_TRIGGER_TOKENS = ("如果", "若", "一旦", "前 30 分钟", "前30分钟", "早球", "红牌", "被迫前压", "转换", "定位球", "门将失误")
REVERSE_FAILURE_TOKENS = ("如果上半场仍是 0-0", "如果上半场仍是0-0", "如果久攻不下", "如果低位防守成功", "如果首发进攻点缺席", "如果射门质量无法转化", "该剧本降权", "大比分剧本失效", "失效")
MARKET_TERMS = ("盘口", "让球", "大小球", "水位", "早盘", "临场", "盘口样本", "隐含")
MARKET_MISSING_TERMS = ("盘口数据缺失", "无法展开盘口剧本", "不展开盘口剧本")


def fail(m):
    errors.append(m)


def script_binds_evidence(script: str, evidence_rows: list[dict]) -> bool:
    if not evidence_rows:
        return False
    compact_script = script.replace(" ", "")
    for row in evidence_rows:
        claim = str(row.get("claim") or "").strip()
        source = str(row.get("source") or "").strip()
        if claim and claim in script:
            return True
        if source and source in script:
            return True
        for field in row.get("fields") or []:
            if str(field) and str(field) in script:
                return True
        compact_claim = claim.replace(" ", "")
        for size in (8, 6, 4):
            for idx in range(0, max(0, len(compact_claim) - size + 1)):
                piece = compact_claim[idx:idx + size]
                if piece and piece in compact_script:
                    return True
    return False


def validate_call(c: dict, policy: dict) -> list[str]:
    errs: list[str] = []
    for f in policy["read_required_fields"]:
        if f not in c:
            errs.append(f"missing field {f}")
    read = c.get("read") or {}
    if not isinstance(read, dict):
        errs.append("read must be object")
        read = {}
    for f in policy["read_subfields"]["read"]:
        if f not in read:
            errs.append(f"read.{f} missing")
    watch = read.get("watch_points_cn")
    risks = read.get("risks_cn")
    if not isinstance(watch, list) or len([x for x in watch if str(x).strip()]) < 2:
        errs.append("bare translation rejected: need at least 2 watch_points_cn")
    if not isinstance(risks, list) or len([x for x in risks if str(x).strip()]) < 1:
        errs.append("bare translation rejected: need at least 1 risks_cn")
    evidence_contract = policy.get("evidence_contract") or {}
    evidence_rows = read.get("evidence")
    if not isinstance(evidence_rows, list) or len(evidence_rows) < int(evidence_contract.get("min_items", 2)):
        errs.append("read.evidence must include at least 2 structured evidence rows")
        evidence_rows = []
    allowed_sources = set(evidence_contract.get("sources") or [])
    allowed_availability = set(evidence_contract.get("availability") or [])
    allowed_weight = set(evidence_contract.get("weight") or [])
    required_evidence_fields = set(evidence_contract.get("required_fields") or [])
    for idx, row in enumerate(evidence_rows):
        if not isinstance(row, dict):
            errs.append(f"read.evidence[{idx}] must be object")
            continue
        missing = required_evidence_fields - set(row)
        if missing:
            errs.append(f"read.evidence[{idx}] missing fields: {sorted(missing)}")
        if str(row.get("source") or "") not in allowed_sources:
            errs.append(f"read.evidence[{idx}] invalid source {row.get('source')}")
        if str(row.get("availability") or "") not in allowed_availability:
            errs.append(f"read.evidence[{idx}] invalid availability {row.get('availability')}")
        if str(row.get("weight") or "") not in allowed_weight:
            errs.append(f"read.evidence[{idx}] invalid weight {row.get('weight')}")
        fields = row.get("fields")
        if not isinstance(fields, list) or not fields or not all(isinstance(x, str) and x.strip() for x in fields):
            errs.append(f"read.evidence[{idx}] fields must be a non-empty string array")
        if not str(row.get("claim") or "").strip():
            errs.append(f"read.evidence[{idx}] claim must be non-empty")
    evidence = read.get("evidence_chain_cn")
    if not isinstance(evidence, list) or len([x for x in evidence if str(x).strip()]) < 2:
        errs.append("evidence_chain_cn must include at least 2 data evidence bullets")
    reverse_risks = read.get("reverse_risks_cn")
    if not isinstance(reverse_risks, list) or len([x for x in reverse_risks if str(x).strip()]) < 1:
        errs.append("reverse_risks_cn must include at least 1 reverse path")
    regular_script = str(read.get("regular_script_cn") or "")
    if len(regular_script.strip()) < 8:
        errs.append("regular_script_cn must describe the normal match script")
    if evidence_rows and not script_binds_evidence(regular_script, evidence_rows):
        errs.append("regular_script_cn must bind at least 1 structured evidence row")
    tail_script = str(read.get("high_variance_tail_script_cn") or "")
    if not any(token in tail_script for token in ("高方差", "早球", "红牌", "转换", "定位球", "门将", "尾部")):
        errs.append("high_variance_tail_script_cn must describe a tail/high-variance script")
    if not any(token in tail_script for token in TAIL_TRIGGER_TOKENS):
        errs.append("high_variance_tail_script_cn must include a concrete trigger condition")
    if evidence_rows and not script_binds_evidence(tail_script, evidence_rows):
        errs.append("high_variance_tail_script_cn must bind at least 1 structured evidence claim verbatim")
    reverse_text = "\n".join(str(x) for x in reverse_risks) if isinstance(reverse_risks, list) else ""
    if not any(token in reverse_text for token in REVERSE_FAILURE_TOKENS):
        errs.append("reverse_risks_cn must include at least 1 failure/invalidating condition")
    market_script = str(read.get("market_expert_script_cn") or "")
    market_has_terms = any(token in market_script for token in MARKET_TERMS)
    market_missing = any(token in market_script for token in MARKET_MISSING_TERMS)
    market_has_condition = any(token in market_script for token in TAIL_TRIGGER_TOKENS + REVERSE_FAILURE_TOKENS)
    if not ((market_has_terms and market_has_condition) or market_missing):
        errs.append("market_expert_script_cn must either use market-language with a condition or explicitly say market data is missing")
    score_band = str(read.get("score_band_cn") or "")
    if not any(token in score_band for token in ("区间", "分布", "别当真", "偏")):
        errs.append("score_band_cn must use band/distribution language")
    readiness = c.get("data_readiness")
    if readiness not in policy["readiness_levels"]:
        errs.append(f"invalid data_readiness {readiness}")
    if policy["honesty"]["honesty_label_required_substr"] not in str(c.get("honesty_label", "")):
        errs.append("honesty_label must contain 'AI 解读'")
    if c.get("independent_edge") is not False:
        errs.append("independent_edge must be false")
    for old in ("call", "market_divergence", "key_factors_cn", "conviction", "track_record_context_cn"):
        if old in c:
            errs.append(f"old prediction field forbidden: {old}")
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


def jsonl_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def digest_read(call: dict) -> str:
    blob = json.dumps(call, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def result_fixture_ids() -> set[str]:
    return set(load_results_map())


def validate_review_rows(reviews: list[dict], locks: dict[str, dict], finished: set[str], policy: dict) -> list[str]:
    errs: list[str] = []
    for row in reviews:
        fid = str(row.get("fixture_id"))
        if fid not in finished:
            errs.append(f"review {fid} has no local finished result")
        lock = locks.get(fid)
        if not lock:
            errs.append(f"review {fid} missing immutable lock")
            continue
        expected = lock.get("prematch_read_digest") or digest_read(lock.get("call") or {})
        if row.get("prematch_read_digest") != expected:
            errs.append(f"review {fid} prematch_read_digest mismatch")
        if row.get("honesty_label") != policy["honesty"]["review_label_exact"]:
            errs.append(f"review {fid} honesty label mismatch")
        text = json.dumps(row, ensure_ascii=False)
        for token in policy["forbidden_terms"]:
            if token in text:
                errs.append(f"review {fid} forbidden term: {token}")
    return errs


def validate_memory_consistency(track: dict, audit_rows: int) -> list[str]:
    overall = track.get("overall") or {}
    if "n" not in overall:
        return ["track_record overall.n missing"]
    if overall.get("n") != audit_rows:
        return [f"track_record overall.n={overall.get('n')} does not match scout_audit rows={audit_rows}"]
    return []


def main() -> int:
    for p in (POLICY_P, SCHEMA_P, BUNDLE_MOD, FETCHER, ANALYST, REVIEW_MOD, CALIBRATION_MOD, BUNDLES_P, TRACK_P, LESSONS_P, AUDIT_P, LOCK_P):
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
    for token in (
        "read{tilt_cn,score_band_cn,watch_points_cn[],risks_cn[],vs_market_cn",
        "evidence[{claim,source,fields[],availability,weight}]",
        "evidence_chain_cn",
        "regular_script_cn",
        "high_variance_tail_script_cn",
        "reverse_risks_cn",
        "market_expert_script_cn",
        "AI 解读·非预测·非推介·可能错",
    ):
        if token not in analyst:
            fail(f"analyst missing read-schema token: {token}")
    for token in ("actual_score", "fulltime", "ft_score", "post_match_calibration", "w1_score_engine", "DEFAULT_RHO"):
        if token in analyst:
            fail(f"analyst must not read/use redline or post-match token: {token}")
    if "https://api.anthropic.com" in analyst or "ANTHROPIC_API_KEY" in analyst:
        fail("analyst must follow the T5 OpenAI-compatible route, not Anthropic-only routes")
    if "deepseek-chat" in analyst:
        fail("analyst must use fixed DeepSeek-V4-Pro (API id: deepseek-v4-pro) for the DeepSeek route")
    for token in ("previous_calls", "reused previous valid scout call"):
        if token in analyst:
            fail(f"analyst must not fallback to previous calls: {token}")
    review_src = REVIEW_MOD.read_text(encoding="utf-8")
    for token in ("prematch_read_digest", "AI 复盘·赛后对照", "state/scout_reviews.jsonl", "不许嘴硬", "hashlib.sha256"):
        if token not in review_src:
            fail(f"review script missing token: {token}")
    ledger_src = (ROOT / "scripts/w1_scout_ledger.py").read_text(encoding="utf-8")
    if "hashlib.sha256" not in ledger_src:
        fail("ledger digest must use sha256 canonical JSON")
    calibration_src = CALIBRATION_MOD.read_text(encoding="utf-8")
    for token in ("state/scout_calibration.json", "direction_calibration", "avg_readiness_dims", "不是战胜市场的证据"):
        if token not in calibration_src:
            fail(f"calibration script missing token: {token}")

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
    for k in ("overall", "updated_at"):
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
    locks = {str(row.get("fixture_id")): row for row in jsonl_rows(LOCK_P)}
    finished = result_fixture_ids()
    for err in validate_review_rows(jsonl_rows(REVIEWS_P), locks, finished, policy):
        fail(err)

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
    base = {"fixture_id": "X",
            "read": {"tilt_cn": "主队小优", "score_band_cn": "偏 1-0/2-0,但单场看区间、别当真",
                     "watch_points_cn": ["主队边路推进", "客队转换防守"], "risks_cn": ["早球会改变节奏"],
                     "vs_market_cn": "与市场差异不大,仅作讨论点",
                     "evidence": [
                         {"claim": "市场读数主队略低水", "source": "market", "fields": ["market"], "availability": "partial", "weight": "medium"},
                         {"claim": "阵容信息部分缺失", "source": "lineups", "fields": ["lineup"], "availability": "partial", "weight": "low"},
                     ],
                     "evidence_chain_cn": ["市场读数主队略低水", "阵容信息部分缺失,只作降权证据"],
                     "regular_script_cn": "常规剧本是市场读数主队略低水支撑主队压住节奏,通过边路和二点球慢慢建立优势。",
                     "high_variance_tail_script_cn": "如果市场读数主队略低水被早球或红牌打穿,尾部高方差剧本会让比赛脱离常规节奏。",
                     "reverse_risks_cn": ["如果低位防守成功,客队拖慢节奏后主队优势可能只停留在场面,大比分剧本失效。"],
                     "market_expert_script_cn": "若临场盘口样本仍显示早盘让球倾向主队,水位与样本厚度只作为读盘语境。"},
            "data_readiness": "中", "honesty_label": "AI 解读·非预测·非推介·可能错",
            "independent_edge": False}
    if validate_call(base, policy):
        fail("reverse: a clean match read should pass")
    legacy = dict(base, call={"outcome_lean": "主", "scoreline_lean": "1-0", "confidence": "LOW"})
    if not validate_call(legacy, policy):
        fail("reverse: old prediction call field must be rejected")
    bare = dict(base, read={"tilt_cn": "主队小优", "score_band_cn": "1-0", "watch_points_cn": [], "risks_cn": [], "vs_market_cn": ""})
    if not validate_call(bare, policy):
        fail("reverse: bare translation (no watch/risks/band wording) must be rejected")
    no_evidence = dict(base, read={**base["read"], "evidence_chain_cn": []})
    if not validate_call(no_evidence, policy):
        fail("reverse: missing evidence chain must be rejected")
    bad_structured_evidence = dict(base, read={**base["read"], "evidence": [{"claim": "x", "source": "made_up", "fields": [], "availability": "ok", "weight": "strong"}]})
    if not validate_call(bad_structured_evidence, policy):
        fail("reverse: invalid structured evidence must be rejected")
    no_tail_trigger = dict(base, read={**base["read"], "high_variance_tail_script_cn": "尾部高方差剧本来自节奏变化。"})
    if not validate_call(no_tail_trigger, policy):
        fail("reverse: high variance script without trigger must be rejected")
    no_reverse_failure = dict(base, read={**base["read"], "reverse_risks_cn": ["客队也可能拖慢节奏"]})
    if not validate_call(no_reverse_failure, policy):
        fail("reverse: reverse risks without failure condition must be rejected")
    no_market_script = dict(base, read={**base["read"], "market_expert_script_cn": "普通自然语言描述"})
    if not validate_call(no_market_script, policy):
        fail("reverse: market expert script without market-language terms must be rejected")
    missing_market_script = dict(base, read={**base["read"], "market_expert_script_cn": "盘口数据缺失,不展开盘口剧本。"})
    if validate_call(missing_market_script, policy):
        fail("reverse: explicit market-data-missing script should pass")
    betting = dict(base, read={**base["read"], "watch_points_cn": ["稳赢", "主队边路推进"]})
    if not validate_call(betting, policy):
        fail("reverse: forbidden promise term must be caught")
    if not bundle_leak([{"fixture_id": "Z", "asof_pre_kickoff": True, "actual_score": "2-1"}], forbidden_pm):
        fail("reverse: a bundle with actual_score must be caught")
    bad_scout = {"fixture_id": "Z", "asof_pre_kickoff": False, "availability": {"form": "made_up"}}
    if not validate_scout_payload(bad_scout, "reverse_bad_scout", forbidden_pm):
        fail("reverse: bad scout file shape must be catchable")
    if not validate_memory_consistency({"overall": {"n": audit_rows + 1}}, audit_rows):
        fail("reverse: memory n/audit row mismatch must be caught")
    fake_review = [{"fixture_id": "NO_RESULT", "prematch_read_digest": "bad", "honesty_label": "AI 复盘·赛后对照"}]
    if not validate_review_rows(fake_review, locks, finished, policy):
        fail("reverse: review without finished result / digest match must be caught")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print(f"W1 scout check FAIL ({len(errors)})")
        return 1
    print(f"W1 scout check PASS (bundles={len(bundles)}, reads={n_calls}, audit_rows={audit_rows}, no leakage, "
          "structured read contract, memory consistent, no betting/edge wording)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
