#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Checker for W1 FiveDim Lite Stage A.

Stage A is a read-only data availability layer. This checker guards the core
contract: no post-match leakage, no independent edge claims, no network access,
and no production/model/dashboard wiring.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/w1_fivedim_card_schema.json"
POLICY_PATH = ROOT / "config/w1_fivedim_lite_policy.json"
BUILDER_PATH = ROOT / "scripts/w1_fivedim_lite.py"
OUTPUT_PATH = ROOT / "state/w1_fivedim_lite_cards.json"
CARDS_DIR = ROOT / "data/processed/match_cards/group_stage_round1"

DIMENSIONS = [
    "market_view",
    "strength_view",
    "tactical_view",
    "chemistry_view",
    "environment_view",
]

FORBIDDEN_NETWORK_IMPORTS = [
    "requests",
    "httpx",
    "aiohttp",
    "urllib",
    "socket",
    "selenium",
    "playwright",
    "bs4",
    "BeautifulSoup",
]

REDLINE_PATHS = [
    "scripts/w1_score_engine.py",
    "scripts/build_w1_dashboard_data.py",
    "config/w1_decision_policy.json",
    "config/w1_odds_movement_thresholds.json",
    "reports/dashboard/W1_VISUAL_DASHBOARD.html",
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def walk(obj: Any, path: str = "$") -> Iterable[tuple[str, Any]]:
    yield path, obj
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from walk(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            yield from walk(value, f"{path}[{idx}]")


def walk_view_fields(card: dict[str, Any]) -> Iterable[tuple[str, str, Any]]:
    for dim in DIMENSIONS:
        view = card.get(dim)
        if isinstance(view, dict):
            for path, value in walk(view, dim):
                yield dim, path, value


def forbidden_key_hits(payload: Any, blacklist: set[str]) -> list[str]:
    hits: list[str] = []
    for path, value in walk(payload):
        if not isinstance(value, dict):
            continue
        for key in value:
            if str(key).lower() in blacklist:
                hits.append(f"{path}.{key}")
    return hits


def independent_edge_hits(payload: Any) -> list[str]:
    return [
        path
        for path, value in walk(payload)
        if isinstance(value, dict) and value.get("independent_edge") is True
    ]


def forbidden_text_hits(payload: Any, forbidden_terms: list[str]) -> list[str]:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    hits: list[str] = []
    for term in forbidden_terms:
        if re.search(re.escape(term), text, re.IGNORECASE):
            hits.append(term)
    return hits


def assert_reverse_tests(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    blacklist = {str(x).lower() for x in policy.get("post_match_only_blacklist", [])}
    forbidden_terms = list(policy.get("forbidden_terms", []))

    bad_post_match = {"market_view": {"actual_score": {"value": "2-1"}}}
    if not forbidden_key_hits(bad_post_match, blacklist):
        errors.append("reverse test failed: actual_score did not trip post_match_only guard")

    bad_edge = {"strength_view": {"home_elo_rating": {"independent_edge": True}}}
    if not independent_edge_hits(bad_edge):
        errors.append("reverse test failed: independent_edge=true did not trip guard")

    bad_text = {"market_view": {"summary": "建议下注"}}
    if not forbidden_text_hits(bad_text, forbidden_terms):
        errors.append("reverse test failed: forbidden recommendation term did not trip guard")

    return errors


def assert_no_network_imports(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    for name in FORBIDDEN_NETWORK_IMPORTS:
        patterns = [
            rf"^\s*import\s+{re.escape(name)}(\s|$)",
            rf"^\s*from\s+{re.escape(name)}(\.|\s+import\s)",
        ]
        for pattern in patterns:
            if re.search(pattern, text, re.MULTILINE):
                errors.append(f"{path.relative_to(ROOT)} imports network/scrape library: {name}")
                break
    if "round1_results" in text:
        errors.append(f"{path.relative_to(ROOT)} references round1_results in pre-match builder")
    return errors


def assert_redline_files_clean() -> list[str]:
    cmd = ["git", "diff", "--name-only", "--"] + REDLINE_PATHS
    result = subprocess.run(cmd, cwd=ROOT, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        return [f"git diff redline check failed: {result.stderr.strip()}"]
    touched = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return [f"redline file has local diff: {path}" for path in touched]


def assert_output(payload: dict[str, Any], schema: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    basis_enum = set(schema.get("basis_enum", []))
    availability_enum = set(schema.get("availability_enum", []))
    top_keys = set(schema.get("required_top_level_keys", []))
    blacklist = {str(x).lower() for x in policy.get("post_match_only_blacklist", [])}
    forbidden_terms = list(policy.get("forbidden_terms", []))

    if payload.get("stage") != "W1_FIVEDIM_LITE_STAGE_A":
        errors.append("output stage mismatch")
    if payload.get("research_only") is not True:
        errors.append("research_only must be true")
    if payload.get("production_wired") is not False:
        errors.append("production_wired must be false")
    if payload.get("external_fetch_performed") is not False:
        errors.append("external_fetch_performed must be false")

    expected_cards = len(list(CARDS_DIR.glob("*.json")))
    cards = payload.get("cards", [])
    if payload.get("cards_count") != expected_cards or len(cards) != expected_cards:
        errors.append(f"cards_count mismatch: got {payload.get('cards_count')} cards={len(cards)} expected={expected_cards}")

    forbidden_terms_hits = forbidden_text_hits(payload, forbidden_terms)
    if forbidden_terms_hits:
        errors.append(f"forbidden recommendation language in output: {', '.join(sorted(set(forbidden_terms_hits)))}")

    for idx, card in enumerate(cards):
        prefix = f"cards[{idx}] fixture={card.get('metadata', {}).get('fixture_id')}"
        missing_top = sorted(top_keys - set(card))
        if missing_top:
            errors.append(f"{prefix}: missing top-level keys {missing_top}")
        for dim in DIMENSIONS:
            if dim not in card:
                errors.append(f"{prefix}: missing {dim}")

        market = card.get("market_view", {})
        if market.get("basis") != "market_implied":
            errors.append(f"{prefix}: market_view basis must be market_implied")
        if market.get("source") != "scripts/w1_candidate_builder.py":
            errors.append(f"{prefix}: market_view must wrap scripts/w1_candidate_builder.py")
        if market.get("independent_edge") is not False:
            errors.append(f"{prefix}: market_view independent_edge must be false")
        if market.get("calibrated") is not False:
            errors.append(f"{prefix}: market_view calibrated must be false")
        candidate_payload = market.get("candidate_payload", {})
        if candidate_payload.get("basis") != "market_implied_score_matrix":
            errors.append(f"{prefix}: candidate_payload basis must be market_implied_score_matrix")
        if candidate_payload.get("independent_edge") is not False:
            errors.append(f"{prefix}: candidate_payload independent_edge must be false")
        if candidate_payload.get("calibrated") is not False:
            errors.append(f"{prefix}: candidate_payload calibrated must be false")

        for dim, path, value in walk_view_fields(card):
            if isinstance(value, dict) and {"value", "source", "basis", "availability", "independent_edge"} <= set(value):
                if value.get("basis") not in basis_enum:
                    errors.append(f"{prefix}: {path} invalid basis={value.get('basis')}")
                if value.get("availability") not in availability_enum:
                    errors.append(f"{prefix}: {path} invalid availability={value.get('availability')}")
                if value.get("independent_edge") is not False:
                    errors.append(f"{prefix}: {path} independent_edge must be false")
            elif dim != "market_view" and path.count(".") == 1:
                errors.append(f"{prefix}: {path} is not a valid leaf")

        post_match_hits = forbidden_key_hits({k: card.get(k) for k in DIMENSIONS}, blacklist)
        if post_match_hits:
            errors.append(f"{prefix}: post-match-only keys in pre-match views: {post_match_hits[:5]}")

        edge_hits = independent_edge_hits(card)
        if edge_hits:
            errors.append(f"{prefix}: independent_edge=true at {edge_hits[:5]}")

        redline = card.get("redline_flags", {})
        expected_false = [
            "independent_edge",
            "calibrated",
            "external_fetch",
            "post_match_only_in_prematch_view",
        ]
        for key in expected_false:
            if redline.get(key) is not False:
                errors.append(f"{prefix}: redline_flags.{key} must be false")

    return errors


def main() -> int:
    errors: list[str] = []

    for path in [SCHEMA_PATH, POLICY_PATH, BUILDER_PATH, OUTPUT_PATH]:
        if not path.is_file():
            errors.append(f"missing required file: {path.relative_to(ROOT)}")

    if errors:
        print("FAIL")
        for err in errors:
            print(f"  - {err}")
        return 1

    schema = read_json(SCHEMA_PATH)
    policy = read_json(POLICY_PATH)
    payload = read_json(OUTPUT_PATH)

    errors.extend(assert_reverse_tests(policy))
    errors.extend(assert_no_network_imports(BUILDER_PATH))
    errors.extend(assert_redline_files_clean())
    errors.extend(assert_output(payload, schema, policy))

    if errors:
        print("FAIL: W1 FiveDim Lite Stage A")
        for err in errors:
            print(f"  - {err}")
        return 1

    cards = payload.get("cards", [])
    dim_counts: dict[str, dict[str, int]] = {dim: {"available": 0, "degraded": 0, "missing": 0} for dim in DIMENSIONS}
    for card in cards:
        for dim in DIMENSIONS:
            state = card.get("availability_flags", {}).get(dim)
            if state in dim_counts[dim]:
                dim_counts[dim][state] += 1

    print("PASS: W1 FiveDim Lite Stage A")
    print(f"  cards={payload.get('cards_count')}")
    for dim in DIMENSIONS:
        counts = dim_counts[dim]
        print(f"  {dim}: available={counts['available']} degraded={counts['degraded']} missing={counts['missing']}")
    print("  reverse_tests=post_match_only, forbidden_terms, independent_edge")
    print("  no_network_import=true")
    print("  production_wired=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
