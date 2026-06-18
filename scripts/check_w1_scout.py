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
import re
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
VISIBLE_FORBIDDEN_TOKENS = (
    "p_home",
    "p_draw",
    "p_away",
    "None",
    "null",
    "NaN",
    "undefined",
    "claim",
    "fields",
    "source",
    "availability",
    "weight",
    "历史样本-0",
    "1-历史样本-0",
    "xG若干",
    "若干",
    "LDDL",
    "赢盘",
    "输盘",
    "全赢",
    "走水",
    "不输不赢",
    "无输赢",
    "返还本金",
    "本金",
    "打出",
    "打穿盘口",
    "打穿概率",
    "打穿大球",
    "深穿",
)
WEAK_OVERCLAIM_TOKENS = ("概率较高", "确定", "明显", "强烈", "零封概率较高", "大胜概率较高", "明显打穿", "穿盘路径明确")
MARKET_MISSING_TEXT = "市场赔率数据缺失，暂时无法对比市场倾向。"
MARKET_SCRIPT_MISSING_TEXT = "盘口数据缺失，无法展开让球覆盖或大小球触发判断；本场只保留比赛剧本推演。"
XG_WEAK_TEXT = "xG 样本不足，只作为弱参考。"


def fail(m):
    errors.append(m)


def script_binds_evidence(script: str, evidence_rows: list[dict]) -> bool:
    if not evidence_rows:
        return False
    compact_script = script.replace(" ", "")
    for row in evidence_rows:
        claim = str(row.get("claim") or "").strip()
        if claim and claim in script:
            return True
        compact_claim = claim.replace(" ", "")
        for size in (8, 6, 4):
            for idx in range(0, max(0, len(compact_claim) - size + 1)):
                piece = compact_claim[idx:idx + size]
                if piece and piece in compact_script:
                    return True
    return False


def visible_text_chunks(read: dict) -> list[str]:
    chunks: list[str] = []
    if not isinstance(read, dict):
        return chunks
    for key in ("tilt_cn", "score_band_cn", "vs_market_cn", "regular_script_cn", "high_variance_tail_script_cn", "market_expert_script_cn"):
        if read.get(key):
            chunks.append(str(read.get(key)))
    for key in ("watch_points_cn", "risks_cn", "evidence_chain_cn", "reverse_risks_cn"):
        value = read.get(key)
        if isinstance(value, list):
            chunks.extend(str(item) for item in value if str(item).strip())
        elif value:
            chunks.append(str(value))
    evidence_rows = read.get("evidence")
    if isinstance(evidence_rows, list):
        chunks.extend(str(row.get("claim") or "") for row in evidence_rows if isinstance(row, dict))
    return chunks


def weak_low_evidence(read: dict, readiness: str) -> bool:
    if readiness not in {"中", "低"}:
        return False
    evidence_rows = read.get("evidence") if isinstance(read, dict) else []
    market_missing = False
    xg_weak = False
    if isinstance(evidence_rows, list):
        for row in evidence_rows:
            if not isinstance(row, dict):
                continue
            source = str(row.get("source") or "")
            availability = str(row.get("availability") or "")
            if source == "market" and availability == "missing":
                market_missing = True
            if source == "xg_roll" and availability in {"weak_sample", "partial", "missing"}:
                xg_weak = True
    visible = "\n".join(visible_text_chunks(read))
    if MARKET_MISSING_TEXT in visible or "盘口数据缺失" in visible:
        market_missing = True
    if XG_WEAK_TEXT in visible or "xG样本不足" in visible:
        xg_weak = True
    return market_missing and xg_weak


def validate_data_wording(read: dict, readiness: str) -> list[str]:
    errs: list[str] = []
    visible = "\n".join(visible_text_chunks(read))
    for match in re.finditer(r"近\s*(\d+)\s*场\s*(\d+)\s*胜\s*(\d+)\s*平\s*(\d+)\s*负", visible):
        n, w, d, l = (int(item) for item in match.groups())
        if w + d + l != n:
            errs.append(f"recent form W-D-L sum mismatch: {match.group(0)}")
    for match in re.finditer(r"近\s*(\d+)\s*场[^。；;\n]{0,28}", visible):
        snippet = match.group(0)
        n = int(match.group(1))
        counts = []
        for label in ("胜", "平", "负"):
            token_match = re.search(r"([0-9一二三四五六七八九十两]+)\s*" + label, snippet)
            if token_match:
                counts.append(_small_cn_int(token_match.group(1)))
        if counts and all(item is not None for item in counts) and sum(int(item) for item in counts) != n:
            errs.append(f"recent form W-D-L sum mismatch: {snippet}")
    for match in re.finditer(r"xG\s*(?:为|约|=|:|：)?\s*\d+(?:\.\d+)?\s*[（(][^）)]*\d+\s*场[^）)]*[）)]", visible, flags=re.I):
        start = max(0, match.start() - 24)
        end = min(len(visible), match.end() + 24)
        window = visible[start:end]
        if not any(token in window for token in ("总量", "累计", "场均", "平均", "每场", "avg", "total")):
            errs.append(f"xG wording missing total/avg basis: {match.group(0)}")
    for match in re.finditer(r"[0-9一二三四五六七八九十两]+\s*场[^。；;\n]{0,12}xG\s*(?:为|约|=|:|：)?\s*\d+(?:\.\d+)?", visible, flags=re.I):
        start = max(0, match.start() - 16)
        end = min(len(visible), match.end() + 16)
        window = visible[start:end]
        if not any(token in window for token in ("总量", "累计", "场均", "平均", "每场", "avg", "total")):
            errs.append(f"xG wording missing total/avg basis: {match.group(0)}")
    tail = str(read.get("high_variance_tail_script_cn") or "")
    if weak_low_evidence(read, readiness) and re.search(r"(?:^|[^0-9])(?:[3-9]-0|0-[3-9])(?:[^0-9]|$)", tail):
        errs.append("weak evidence context must not state a strong 3-0/0-3 tail score without sufficient support")
    return errs


def _small_cn_int(text: str) -> int | None:
    text = text.strip()
    if text.isdigit():
        return int(text)
    mapping = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if text in mapping:
        return mapping[text]
    if text == "十":
        return 10
    if text.startswith("十") and len(text) == 2 and text[1] in mapping:
        return 10 + mapping[text[1]]
    if "十" in text:
        left, right = text.split("十", 1)
        if left in mapping:
            return mapping[left] * 10 + (mapping.get(right, 0) if right else 0)
    return None


def validate_visible_text(read: dict, readiness: str) -> list[str]:
    errs: list[str] = []
    chunks = visible_text_chunks(read)
    visible = "\n".join(chunks)
    for token in VISIBLE_FORBIDDEN_TOKENS:
        if token in visible:
            errs.append(f"visible Scout text contains forbidden token: {token}")
    score_band = str(read.get("score_band_cn") or "")
    if "历史样本" in score_band or "若干" in score_band:
        errs.append("score_band_cn must not contain machine fallback tokens")
    market_script = str(read.get("market_expert_script_cn") or "")
    if any(token in market_script for token in ("p_home", "p_draw", "p_away", "None", "null", "NaN", "undefined")):
        errs.append("market_expert_script_cn must not expose market variables or missing sentinels")
    if "盘口数据缺失" in market_script and MARKET_SCRIPT_MISSING_TEXT not in market_script:
        errs.append("market_expert_script_cn must use the approved market-missing sentence")
    if weak_low_evidence(read, readiness):
        for token in WEAK_OVERCLAIM_TOKENS:
            if token in visible:
                errs.append(f"weak evidence context overclaims: {token}")
    errs.extend(validate_data_wording(read, readiness))
    return errs


def market_has_lines(bundle: dict) -> bool:
    market = bundle.get("market") if isinstance(bundle.get("market"), dict) else {}
    availability = bundle.get("availability") if isinstance(bundle.get("availability"), dict) else {}
    has_ah = availability.get("market_ah") == "available" or (
        market.get("ah_line") not in (None, "")
        and isinstance(market.get("ah_home_price"), (int, float))
        and isinstance(market.get("ah_away_price"), (int, float))
    )
    has_ou = availability.get("market_ou") == "available" or (
        market.get("ou_line") not in (None, "")
        and isinstance(market.get("over_price"), (int, float))
        and isinstance(market.get("under_price"), (int, float))
    )
    return bool(has_ah or has_ou)


def market_all_missing(bundle: dict) -> bool:
    availability = bundle.get("availability") if isinstance(bundle.get("availability"), dict) else {}
    return all(availability.get(key) != "available" for key in ("market_1x2", "market_ah", "market_ou"))


def validate_call_against_bundle(call: dict, bundle: dict) -> list[str]:
    errs: list[str] = []
    read = call.get("read") if isinstance(call.get("read"), dict) else {}
    market_script = str(read.get("market_expert_script_cn") or "")
    if market_has_lines(bundle):
        if "盘口数据缺失" in market_script or "无法展开盘口剧本" in market_script or "不展开盘口剧本" in market_script:
            errs.append("market AH/OU available but call still says market data is missing")
        if not ("让球" in market_script and "大小球" in market_script and any(token in market_script for token in REVERSE_FAILURE_TOKENS + TAIL_TRIGGER_TOKENS)):
            errs.append("market AH/OU available but market_expert_script_cn lacks handicap/totals/condition language")
    elif market_all_missing(bundle):
        has_market_terms = any(token in market_script for token in MARKET_TERMS)
        has_missing = any(token in market_script for token in MARKET_MISSING_TERMS)
        if has_market_terms and not has_missing:
            errs.append("market all missing but call invents market expert script")
    return errs


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
    errs.extend(validate_visible_text(read, str(readiness or "")))
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
        availability = b.get("availability") or {}
        for key in ("market_1x2", "market_ah", "market_ou"):
            if availability.get(key) not in {"available", "missing"}:
                fail(f"bundle {b.get('fixture_id')} availability.{key} missing or invalid")
        market = b.get("market") or {}
        for key in ("p_home", "p_draw", "p_away", "ah_line", "ah_home_price", "ah_away_price", "ou_line", "over_price", "under_price", "bookmaker_count", "market_source", "odds_updated_at"):
            if key not in market:
                fail(f"bundle {b.get('fixture_id')} market missing key {key}")

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
        bundle_by_fixture = {str(bundle.get("fixture_id")): bundle for bundle in bundles}
        seen = set()
        for c in calls:
            fid = c.get("fixture_id")
            if fid in seen:
                fail(f"duplicate call for fixture {fid}")
            seen.add(fid)
            for e in validate_call(c, policy):
                fail(f"call {fid}: {e}")
            if str(fid) in bundle_by_fixture:
                for e in validate_call_against_bundle(c, bundle_by_fixture[str(fid)]):
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
    if not validate_call(missing_market_script, policy):
        fail("reverse: short market-data-missing script must be rejected in favor of the approved sentence")
    approved_missing_market_script = dict(base, read={**base["read"], "market_expert_script_cn": MARKET_SCRIPT_MISSING_TEXT})
    if validate_call(approved_missing_market_script, policy):
        fail("reverse: approved market-data-missing script should pass")
    bad_visible_text = dict(base, read={
        **base["read"],
        "score_band_cn": "偏 1-历史样本-0",
        "evidence_chain_cn": ["市场读数 p_home=None", "数据claim 暴露了结构词"],
        "regular_script_cn": "常规剧本来自 claim 字段拼接。",
    })
    if not validate_call(bad_visible_text, policy):
        fail("reverse: visible machine/debug tokens must be rejected")
    weak_overclaim = dict(base, data_readiness="低", read={
        **base["read"],
        "evidence": [
            {"claim": "市场赔率数据缺失，暂时无法对比市场倾向。", "source": "market", "fields": ["market"], "availability": "missing", "weight": "low"},
            {"claim": "xG 样本不足，只作为弱参考。", "source": "xg_roll", "fields": ["xg_for"], "availability": "weak_sample", "weight": "low"},
        ],
        "evidence_chain_cn": ["市场赔率数据缺失，暂时无法对比市场倾向。", "xG 样本不足，只作为弱参考。"],
        "regular_script_cn": "常规剧本是市场赔率数据缺失，暂时无法对比市场倾向，但主队零封概率较高。",
        "high_variance_tail_script_cn": "如果 xG 样本不足，只作为弱参考，同时出现早球，尾部剧本打开。",
        "market_expert_script_cn": MARKET_SCRIPT_MISSING_TEXT,
    })
    if not validate_call(weak_overclaim, policy):
        fail("reverse: weak evidence overclaim must be rejected")
    bad_wdl = dict(base, read={**base["read"], "evidence_chain_cn": ["近期状态：近5场2胜3平2负。", "阵容信息部分缺失,只作降权证据"]})
    if not validate_call(bad_wdl, policy):
        fail("reverse: impossible recent form W-D-L count must be rejected")
    bad_cn_wdl = dict(base, read={**base["read"], "evidence_chain_cn": ["近期状态：近 5 场两平一负一胜。", "阵容信息部分缺失,只作降权证据"]})
    if not validate_call(bad_cn_wdl, policy):
        fail("reverse: impossible Chinese W-D-L count must be rejected")
    bad_xg_basis = dict(base, read={**base["read"], "evidence_chain_cn": ["xG 3.2（5场）", "阵容信息部分缺失,只作降权证据"]})
    if not validate_call(bad_xg_basis, policy):
        fail("reverse: xG number without total/avg basis must be rejected")
    bad_tail_score = dict(weak_overclaim, read={**weak_overclaim["read"], "regular_script_cn": "常规剧本是市场赔率数据缺失，暂时无法对比市场倾向，主队只有倾向。", "high_variance_tail_script_cn": "如果 xG 样本不足，只作为弱参考，同时出现早球，比分可能直接走到 3-0。"})
    if not validate_call(bad_tail_score, policy):
        fail("reverse: weak evidence strong tail score must be rejected")
    market_bundle = {"availability": {"market_ah": "available", "market_ou": "available"}, "market": {"ah_line": "-1", "ah_home_price": 1.9, "ah_away_price": 1.9, "ou_line": "2.5", "over_price": 1.9, "under_price": 1.9}}
    if not validate_call_against_bundle(approved_missing_market_script, market_bundle):
        fail("reverse: AH/OU available but missing-market script must be rejected")
    missing_bundle = {"availability": {"market_1x2": "missing", "market_ah": "missing", "market_ou": "missing"}, "market": {}}
    invented_market = dict(base, read={**base["read"], "market_expert_script_cn": "若临场让球盘口保持主队低水，大小球触发看早球。"})
    if not validate_call_against_bundle(invented_market, missing_bundle):
        fail("reverse: all-missing market bundle must reject invented market script")
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
