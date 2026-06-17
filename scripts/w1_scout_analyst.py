#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1_SCOUT T5 analyst runner.

Turns pre-match scout bundles into research calls with a pluggable
OpenAI-compatible chat API. DeepSeek is the default provider. The model is never
trusted directly: each call must pass check_w1_scout.validate_call before it is
written to the gitignored state/w1_scout_calls.json store.

No provider key means no output is written. That keeps the cold-start path honest
and avoids fabricating analyst calls.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib import request

ROOT = Path(__file__).resolve().parents[1]
BUNDLES_P = ROOT / "state/w1_scout_bundles.json"
TRACK_P = ROOT / "state/scout_track_record.json"
LESSONS_P = ROOT / "state/scout_lessons.md"
CALLS_P = ROOT / "state/w1_scout_calls.json"
POLICY_P = ROOT / "config/w1_scout_policy.json"
CHECKER_P = ROOT / "scripts/check_w1_scout.py"

PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/chat/completions",
        "model": "deepseek-v4-pro",
        "key_env": "DEEPSEEK_API_KEY",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
        "key_env": "OPENAI_API_KEY",
    },
    "custom": {
        "base_url": None,
        "model": None,
        "key_env": "W1_SCOUT_API_KEY",
    },
}

SYSTEM_PROMPT = """你是足球研究分析师。读“赛前因子包 + 你自己的历史战绩 + 教训”，对这场给出有据判断。

硬规则：
- 默认 AGREE 跟市场；只有真因子(form/xG/伤停/首发/排名/休息天数)明显背离市场、且有把握，才 LEAN_DIFFERENT。
- 只有背离很强且 conviction=HIGH，才 FADE_MARKET。
- 必须 stance 表态，必须给 why_cn 和 key_factors_cn；禁止只复述赔率。
- 缺数据就写缺数据，首发未确认要降低信心。
- 禁止投注、资金、保证、稳赢、必胜等表达。
- 只输出一个 JSON 对象，字段必须是：
  fixture_id,
  call{outcome_lean,scoreline_lean,confidence},
  market_divergence{stance,where_cn,why_cn},
  key_factors_cn[],
  conviction,
  track_record_context_cn,
  honesty_label,
  independent_edge。
- honesty_label 必须包含“AI 观点”，independent_edge 必须为 false。
"""


def load_checker():
    spec = importlib.util.spec_from_file_location("w1_scout_checker", CHECKER_P)
    if not spec or not spec.loader:
        raise RuntimeError("unable to load check_w1_scout.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def selected_bundles(fixtures: set[str] | None, limit: int | None) -> list[dict[str, Any]]:
    bundles = read_json(BUNDLES_P, {"bundles": []}).get("bundles", [])
    out = []
    for bundle in bundles:
        fid = str(bundle.get("fixture_id") or "")
        if fixtures and fid not in fixtures:
            continue
        out.append(bundle)
        if limit and len(out) >= limit:
            break
    return out


def compact_factor_view(bundle: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "form_home",
        "form_away",
        "xg_roll_home",
        "xg_roll_away",
        "lineup",
        "injuries_home",
        "injuries_away",
        "standings",
        "h2h",
        "rest_days",
        "availability",
    )
    return {key: bundle.get(key) for key in keys}


def user_prompt(bundle: dict[str, Any], track: dict[str, Any], lessons: str, validator_errors: list[str] | None = None) -> str:
    market = bundle.get("market") or {}
    retry_note = ""
    if validator_errors:
        retry_note = "\n[上次输出未过闸门] " + json.dumps(validator_errors, ensure_ascii=False)
    return (
        f"[比赛] {bundle.get('home')} vs {bundle.get('away')} (fixture_id={bundle.get('fixture_id')})\n"
        f"[市场读数] p_home={market.get('p_home')} p_draw={market.get('p_draw')} p_away={market.get('p_away')}\n"
        f"[因子包] {json.dumps(compact_factor_view(bundle), ensure_ascii=False)}\n"
        f"[你的历史战绩] {json.dumps(track, ensure_ascii=False)[:1200]}\n"
        f"[教训] {lessons[:1000]}\n"
        f"{retry_note}\n"
        "按系统规则只输出该场 call 的 JSON。"
    )


def extract_json_object(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("model response did not contain a JSON object")
    payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("model JSON is not an object")
    return payload


def provider_config(provider_name: str) -> dict[str, str]:
    if provider_name not in PROVIDERS:
        raise ValueError(f"unknown provider {provider_name}; use one of {sorted(PROVIDERS)}")
    cfg = dict(PROVIDERS[provider_name])
    base_url = os.environ.get("W1_SCOUT_BASE_URL") or cfg.get("base_url")
    model = cfg.get("model") if provider_name == "deepseek" else (os.environ.get("W1_SCOUT_MODEL") or cfg.get("model"))
    key_env = str(cfg["key_env"])
    api_key = os.environ.get(key_env)
    if provider_name == "custom":
        api_key = os.environ.get("W1_SCOUT_API_KEY")
    if not base_url:
        raise ValueError("custom provider requires W1_SCOUT_BASE_URL")
    if not model:
        raise ValueError("custom provider requires W1_SCOUT_MODEL")
    if not api_key:
        raise RuntimeError(f"{key_env} is not configured")
    return {"provider": provider_name, "base_url": str(base_url), "model": str(model), "api_key": api_key}


def chat_completion(cfg: dict[str, str], prompt: str, max_tokens: int) -> str:
    body = json.dumps(
        {
            "model": cfg["model"],
            "temperature": 0.3,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }
    ).encode("utf-8")
    req = request.Request(
        cfg["base_url"],
        data=body,
        headers={"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"},
    )
    with request.urlopen(req, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return str(payload["choices"][0]["message"]["content"]).strip()


def harden_call(call: dict[str, Any], fixture_id: str) -> dict[str, Any]:
    call["fixture_id"] = fixture_id
    call["honesty_label"] = "AI 观点·未验证·仅研究·可能错"
    call["independent_edge"] = False
    if isinstance(call.get("conviction"), str):
        call["conviction"] = call["conviction"].upper()
    divergence = call.get("market_divergence")
    if isinstance(divergence, dict) and isinstance(divergence.get("stance"), str):
        divergence["stance"] = divergence["stance"].upper()
    return call


def build_calls(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[tuple[str, str]], dict[str, str]]:
    try:
        cfg = provider_config(args.provider)
    except Exception as exc:
        print(f"FAIL: {exc}; no scout calls written.", file=sys.stderr)
        raise SystemExit(2)

    checker = load_checker()
    policy = read_json(POLICY_P, {})
    track = read_json(TRACK_P, {})
    lessons = LESSONS_P.read_text(encoding="utf-8") if LESSONS_P.is_file() else ""
    fixtures = set(args.fixture or []) or None
    calls: list[dict[str, Any]] = []
    failed: list[tuple[str, str]] = []

    for bundle in selected_bundles(fixtures, args.limit):
        fixture_id = str(bundle.get("fixture_id") or "")
        validator_errors: list[str] | None = None
        accepted: dict[str, Any] | None = None
        for _attempt in range(args.retries + 1):
            try:
                text = chat_completion(
                    cfg,
                    user_prompt(bundle, track, lessons, validator_errors),
                    args.max_tokens,
                )
                candidate = harden_call(extract_json_object(text), fixture_id)
            except Exception as exc:
                validator_errors = [f"model/parse error: {exc}"]
                continue
            validator_errors = checker.validate_call(candidate, policy)
            if not validator_errors:
                accepted = candidate
                break
        if accepted:
            calls.append(accepted)
        else:
            failed.append((fixture_id, "; ".join(validator_errors or ["unknown validation failure"])))
    return calls, failed, cfg


def write_calls(calls: list[dict[str, Any]], cfg: dict[str, str]) -> None:
    CALLS_P.parent.mkdir(parents=True, exist_ok=True)
    CALLS_P.write_text(
        json.dumps(
            {
                "stage": "W1_SCOUT",
                "schema_version": "W1_SCOUT_CALL_V1",
                "generated_by": f"{cfg['provider']}:{cfg['model']}",
                "calls": calls,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate W1_SCOUT analyst calls through an OpenAI-compatible API, gated by check_w1_scout.")
    parser.add_argument("--fixture", action="append", help="Fixture id to judge; may be repeated. Defaults to all bundles.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum bundles to judge.")
    parser.add_argument("--provider", default=os.environ.get("W1_SCOUT_LLM", "deepseek"), choices=sorted(PROVIDERS))
    parser.add_argument("--max-tokens", type=int, default=900)
    parser.add_argument("--retries", type=int, default=1, help="Validation retry count per fixture.")
    parser.add_argument("--dry-run", action="store_true", help="Validate setup and selected bundle count without calling the model.")
    args = parser.parse_args()

    selected = selected_bundles(set(args.fixture or []) or None, args.limit)
    if args.dry_run:
        model = PROVIDERS[args.provider].get("model") if args.provider == "deepseek" else (os.environ.get("W1_SCOUT_MODEL") or PROVIDERS[args.provider].get("model") or "<custom>")
        print(f"scout analyst dry-run: provider={args.provider}, selected={len(selected)}, model={model}, output={CALLS_P.relative_to(ROOT)}")
        return 0
    if not selected:
        print("No scout bundles selected; no scout calls written.")
        return 0

    calls, failed, cfg = build_calls(args)
    if failed:
        for fixture_id, reason in failed[:12]:
            print(f"FAIL: fixture {fixture_id}: {reason}", file=sys.stderr)
        print(f"scout analyst wrote nothing because {len(failed)} fixture(s) failed validation.", file=sys.stderr)
        return 1
    write_calls(calls, cfg)
    print(f"scout analyst PASS: provider={cfg['provider']} model={cfg['model']} wrote {len(calls)} calls -> {CALLS_P.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
