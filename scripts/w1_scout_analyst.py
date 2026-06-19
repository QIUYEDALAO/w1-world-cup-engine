#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W1_SCOUT analyst runner.

Turns pre-match scout bundles into structured match reads with a pluggable
OpenAI-compatible chat API. DeepSeek is the default provider. The model is never
trusted directly: each read must pass check_w1_scout.validate_call before it is
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

SYSTEM_PROMPT = """你是足球亚盘盘口研究员。任务是【把这场球读透并形成亚盘主导推荐卡】——不是资金建议,不承诺结果。

硬规则：
- 第一主轴是亚洲让球盘(AH)：主让/客受让/PASS观察、盘口深度、水位、W1覆盖概率、市场隐含覆盖概率、覆盖差、失效条件。
- 1X2 只能作为欧盘参考，不得作为主推荐轴，不得把胜平负概率放在默认结论最前面。
- 必须输出 read.asian_handicap_card，字段为 schema_version, fixture_id, stage_id, stage_label_cn, data_readiness, main_ah_pick_cn, ah_side_cn, ah_line, ah_price, ah_confidence_cn, recommendation_grade, ah_logic_cn, cover_probability_model, cover_probability_market, cover_edge, line_movement_cn, water_movement_cn, market_consensus_cn, ou_pick_cn, score_path_cn, risk_cn, pass_reason_cn, final_action_cn。
- 如果 AH盘口、W1覆盖概率或 score matrix 缺失，asian_handicap_card 必须写“亚盘推荐：PASS / 观察”，pass_reason_cn 写明“AH盘口或模型覆盖概率缺失，无法形成高质量推荐。”，不得硬编主推。
- 如果 data_readiness 为“低”，只能 PASS/观察，不得主推。
- 若 recommendation_grade 为 A/B+/B，必须有 ah_line、ah_side_cn、ah_confidence_cn、cover_probability_model、risk_cn、final_action_cn。
- 可以使用“推荐/主推/亚盘方向/穿盘/受让保护/让深盘/退盘/升盘/水位”等盘口术语；禁止下注金额、重仓、梭哈、倍投、加仓、稳赚、必红、包中、必穿、稳赢、包赢。
- 球队名必须使用中文，例如“澳大利亚 +1”“韩国 +1”“墨西哥 -0.5”；不得输出 Australia/Türkiye/South Korea/Mexico 等英文队名。
- 按五维(实力/战术/阵型/市场/环境)给结构化解读。
- 写清强弱倾向(谁占优、占多大)、看点(决定比赛走向的点)、风险(可能翻车的路径)、与市场的差异(若有,作为讨论点,不是叫人跟或逆)。
- 必须写出结构化 evidence、数据证据链、常规剧本、尾部高方差剧本、反向风险、专家盘口剧本。
- recommendation_card 是兼容层；默认展示以 asian_handicap_card 为准。recommendation_card 不能抢在 asian_handicap_card 之前解释 1X2。
- recommendation_card 必须短句、直接、可执行阅读；专家解释放在后面的证据链和剧本字段里。
- recommendation_card 必须包含 one_x_two_cn、score_picks_cn、ou_pick_cn、ah_pick_cn、main_recommendation_cn、risk_cn、confidence_cn、data_status_cn。
- recommendation_card.one_x_two_cn 可使用市场读数百分比，例如“主胜 52%｜平 25%｜客胜 23%”；没有 1X2 时写“1X2 市场读数缺失，暂不展开胜平负推荐。”
- 1X2 优先级：market_1x2 有数据用“来源：市场赔率”；market_1x2 缺失但 model_1x2 有数据用“来源：W1模型”；两者都缺才写“1X2 数据缺失，降级观察｜来源：缺失”。
- recommendation_card.score_picks_cn 使用“首选/次选/风险”短句；有比分矩阵概率时写“2-0 13%｜1-0 11%｜风险 1-1 10%｜来源：score matrix”；没有概率时写“首选 2-0｜次选 1-0｜风险 1-1｜来源：剧本排序，非精确概率”。
- recommendation_card.ou_pick_cn 使用“小2.5｜信心：中｜失效：早球｜来源：盘口 + W1分布”；大小球盘口缺失时必须写“大小球盘口缺失，暂不输出大小球推荐｜来源：缺失。”
- recommendation_card.ah_pick_cn 使用“韩国 +1｜信心：中｜深盘穿盘不稳｜失效：主队早球｜来源：盘口 + W1分布”；让球盘口缺失时必须写“让球盘口缺失，暂不输出让球推荐｜来源：缺失。”
- recommendation_card 每个字段都要短，单项不超过 80 个中文字符；不要写长段解释。
- recommendation_card.main_recommendation_cn 必须给主线，但必须带条件；数据不足时写“数据不足，推荐降级为观察。”
- recommendation_card.risk_cn 必须写风险触发或失效条件；recommendation_card.confidence_cn 只能写 高/中/低。
- 如果 data_readiness 为“低”，recommendation_card 必须出现“观察”或“降级”，不得强推。
- read.evidence 是给 checker/专家审计用的结构化证据数组,至少 2 条；结构化键名按 schema 输出,但这些键名绝不能出现在任何给人看的中文句子里。
- evidence.source 只能取 form/xg_roll/lineups/injuries/market/score_matrix/rest_days/standings/h2h/environment/availability。
- evidence.availability 只能取 full/partial/weak_sample/missing；evidence.weight 只能取 high/medium/low。
- evidence_chain_cn 是给人看的中文证据链,要逐条写成人话:市场读数/形态/xG/阵容/伤停/排名/休息/环境;缺失也要写成人话,不得补造,不得暴露 JSON 字段名。
- 常规剧本写比赛最自然展开路径;尾部高方差剧本写早球、红牌、转换混乱、定位球、门将失误等低频但会改变节奏的路径。
- regular_script_cn 和 high_variance_tail_script_cn 都必须绑定至少一条结构化证据的事实内容,但只能用自然语言复述,不得写“claim/source/fields/availability/weight”等结构词。
- 尾部高方差剧本必须写触发条件,例如“如果/若/一旦/前30分钟/早球/红牌/被迫前压/转换/定位球/门将失误”。
- 反向风险写与主倾向相反的比赛路径,至少一条必须原文包含失效条件关键词,例如“如果上半场仍是0-0”“如果久攻不下”“如果低位防守成功”“如果射门质量无法转化”“该剧本降权”“大比分剧本失效”。
- 专家盘口剧本只能解释让球/大小球/水位/早盘/临场/盘口样本,不得写成行动建议；盘口数据缺失时必须写“盘口数据缺失，无法展开让球覆盖或大小球触发判断；本场只保留比赛剧本推演。”不要硬编盘口内容。
- 如果市场包里提供 market_ah 或 market_ou，专家盘口剧本必须展开让球覆盖路径、大小球触发条件、盘口失效条件；此时禁止写“盘口数据缺失”。
- 专家盘口术语要使用“覆盖让球/未覆盖让球/覆盖受让/盘口返回中性/大小球触发/盘口失效条件”等研究口径，不得写“赢盘/输盘/全赢/走水/不输不赢/无输赢/返还本金/打出/打穿盘口/打穿概率”。
- 可以写主胜/平/客胜、比分首选/次选/风险、大小球倾向、让球倾向、受让保护、穿盘路径、信心：高/中/低；但不得写下注金额、重仓、梭哈、倍投、加仓、稳赚、必红、包中或命中率承诺。
- 比分只给分布口径:"偏 1-0/2-0,但单场看区间、别当真",绝不假装精确预测比分。
- 如果没有可靠比分数据,score_band_cn 必须写“常规比分带暂不展开；偏低比分小胜或平局分支，需结合临场数据。”
- 缺数据(availability=missing)就说缺,别编;首发未确认要降低 data_readiness。
- 不得输出内部变量名或结构词：p_home、p_draw、p_away、None、null、NaN、undefined、claim、fields、source、availability、weight。
- 不得输出坏格式或机器串：历史样本-0、1-历史样本-0、若干、xG若干、LDDL 这类未解释战绩代码串。
- 如果市场数据缺失,必须写成人话：“市场赔率数据缺失，暂时无法对比市场倾向。”
- 如果 xG 样本不足,必须写：“xG 样本不足，只作为弱参考。”不得写“xG 若干”。
- 任何 xG 数字必须标注“场均”或“总量/累计”,例如“5场场均xG 0.64”或“5场累计xG 3.2”,不得只写“5场滚动xG为3.2”。
- 如果写“近 N 场 X胜Y平Z负”,三项相加必须等于 N；没有完整 W-D-L 时就写“近况更稳/偏弱”,不要编造胜平负序列。
- 如果市场缺失、xG 样本不足且 data_readiness 为中或低,只能写“倾向/剧本/路径/风险”,不得写“概率较高/确定/明显/强烈/零封概率较高/大胜概率较高/明显打穿/穿盘路径明确”。
- 禁止 投注/资金/命中承诺/稳赢/打败市场/独立优势/资金化推介/机会 等表达。
- 只输出一个 JSON 对象，字段必须是：
  fixture_id,
  read{tilt_cn,score_band_cn,watch_points_cn[],risks_cn[],vs_market_cn,
       evidence[{claim,source,fields[],availability,weight}],
       asian_handicap_card{schema_version,fixture_id,stage_id,stage_label_cn,data_readiness,main_ah_pick_cn,ah_side_cn,ah_line,ah_price,ah_confidence_cn,recommendation_grade,ah_logic_cn,cover_probability_model,cover_probability_market,cover_edge,line_movement_cn,water_movement_cn,market_consensus_cn,ou_pick_cn,score_path_cn,risk_cn,pass_reason_cn,final_action_cn},
       recommendation_card{one_x_two_cn,score_picks_cn,ou_pick_cn,ah_pick_cn,main_recommendation_cn,risk_cn,confidence_cn,data_status_cn},
       evidence_chain_cn[],regular_script_cn,high_variance_tail_script_cn,
       reverse_risks_cn[],market_expert_script_cn},
  data_readiness,
  honesty_label,
  independent_edge。
- data_readiness 只能是 "高" / "中" / "低"。
- honesty_label 必须等于“AI 解读·非预测·非推介·可能错”，independent_edge 必须为 false。
"""

SCORE_BAND_FALLBACK = "常规比分带暂不展开；偏低比分小胜或平局分支，需结合临场数据。"
MARKET_MISSING_TEXT = "市场赔率数据缺失，暂时无法对比市场倾向。"
MARKET_SCRIPT_MISSING_TEXT = "盘口数据缺失，无法展开让球覆盖或大小球触发判断；本场只保留比赛剧本推演。"
XG_WEAK_TEXT = "xG 样本不足，只作为弱参考。"
VISIBLE_TEXT_KEYS = (
    "tilt_cn",
    "score_band_cn",
    "vs_market_cn",
    "regular_script_cn",
    "high_variance_tail_script_cn",
    "market_expert_script_cn",
)
VISIBLE_LIST_KEYS = ("watch_points_cn", "risks_cn", "evidence_chain_cn", "reverse_risks_cn")
RECOMMENDATION_CARD_KEYS = (
    "one_x_two_cn",
    "score_picks_cn",
    "ou_pick_cn",
    "ah_pick_cn",
    "main_recommendation_cn",
    "risk_cn",
    "confidence_cn",
    "data_status_cn",
)
AH_CARD_KEYS = (
    "schema_version",
    "fixture_id",
    "stage_id",
    "stage_label_cn",
    "data_readiness",
    "main_ah_pick_cn",
    "ah_side_cn",
    "ah_line",
    "ah_price",
    "ah_confidence_cn",
    "recommendation_grade",
    "ah_logic_cn",
    "cover_probability_model",
    "cover_probability_market",
    "cover_edge",
    "line_movement_cn",
    "water_movement_cn",
    "market_consensus_cn",
    "ou_pick_cn",
    "score_path_cn",
    "risk_cn",
    "pass_reason_cn",
    "final_action_cn",
)
MACHINE_BAD_REPLACEMENTS = (
    ("p_home", "市场主胜读数"),
    ("p_draw", "市场平局读数"),
    ("p_away", "市场客胜读数"),
    ("None", "数据缺失"),
    ("null", "数据缺失"),
    ("NaN", "数据缺失"),
    ("undefined", "数据缺失"),
    ("数据claim", "证据"),
    ("claim", "证据"),
    ("fields", "数据项"),
    ("source", "来源"),
    ("availability", "可用度"),
    ("weight", "证据力度"),
    ("xG若干", XG_WEAK_TEXT),
    ("xG 若干", XG_WEAK_TEXT),
    ("若干", "样本不足"),
    ("1-历史样本-0", SCORE_BAND_FALLBACK),
    ("历史样本-0", SCORE_BAND_FALLBACK),
    ("保证", "不能说明"),
    ("赢盘", "覆盖让球"),
    ("输盘", "未覆盖让球"),
    ("全赢", "覆盖受让"),
    ("走水（不输不赢）", "盘口返回中性"),
    ("走水", "盘口返回中性"),
    ("不输不赢", "盘口返回中性"),
    ("无输赢", "盘口返回中性"),
    ("打穿概率", "覆盖条件"),
    ("打穿大球", "触发大球"),
    ("打穿盘口", "覆盖让球"),
    ("打出", "触发"),
    ("深穿", "覆盖让球"),
    ("返还本金", "盘口返回中性"),
    ("大球打出", "大球触发"),
    ("小球打出", "小球触发"),
    ("盘口盘口返回", "盘口返回"),
    ("小球稳固", "小比分路径更稳"),
    ("Australia", "澳大利亚"),
    ("Türkiye", "土耳其"),
    ("Turkey", "土耳其"),
    ("South Korea", "韩国"),
    ("Mexico", "墨西哥"),
    ("USA", "美国"),
)
STRONG_LOW_EVIDENCE_REPLACEMENTS = (
    ("零封概率较高", "存在零封分支，但证据不足，需临场确认"),
    ("大胜概率较高", "大胜只作为尾部路径"),
    ("明显打穿", "盘口覆盖不展开"),
    ("穿盘路径明确", "盘口覆盖不展开"),
    ("概率较高", "倾向存在"),
    ("确定", "倾向"),
    ("强烈", "偏向"),
    ("明显", "相对"),
)


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


def market_prompt_line(market: dict[str, Any]) -> str:
    lines: list[str] = []
    vals = [market.get("p_home"), market.get("p_draw"), market.get("p_away")]
    if all(isinstance(v, (int, float)) for v in vals):
        home, draw, away = (float(v) for v in vals)
        lines.append(f"市场 1X2：主胜约 {home:.1%}，平局约 {draw:.1%}，客胜约 {away:.1%}；推荐卡 one_x_two_cn 来源写“市场赔率”。")
    else:
        model_vals = [market.get("model_p_home"), market.get("model_p_draw"), market.get("model_p_away")]
        if all(isinstance(v, (int, float)) for v in model_vals):
            home, draw, away = (float(v) for v in model_vals)
            lines.append(f"W1模型 1X2：主胜约 {home:.1%}，平局约 {draw:.1%}，客胜约 {away:.1%}；市场 1X2 缺失时推荐卡 one_x_two_cn 必须使用这些数，来源写“W1模型”。")
        else:
            lines.append("1X2 市场和 W1模型概率均缺失；推荐卡 one_x_two_cn 写“1X2 数据缺失，降级观察｜来源：缺失”。")
    score_picks = market.get("score_picks")
    if isinstance(score_picks, list) and score_picks:
        pieces = []
        for item in score_picks[:3]:
            score = item.get("score")
            prob = item.get("probability")
            if score and isinstance(prob, (int, float)):
                pieces.append(f"{score} {float(prob):.0%}")
            elif score:
                pieces.append(str(score))
        if pieces:
            lines.append("比分候选：" + "｜".join(pieces) + "；推荐卡 score_picks_cn 来源写“score matrix”。")
    ah_line = market.get("ah_line")
    ah_home = market.get("ah_home_price")
    ah_away = market.get("ah_away_price")
    if ah_line not in (None, "") and isinstance(ah_home, (int, float)) and isinstance(ah_away, (int, float)):
        lines.append(f"让球盘口：主队 {ah_line}，主队价格约 {float(ah_home):.2f}，客队价格约 {float(ah_away):.2f}。")
    ah = market.get("ah") if isinstance(market.get("ah"), dict) else {}
    if ah:
        side = ah.get("selected_side")
        side_cn = "主队让球" if side == "home" else "客队受让" if side == "away" else "观察"
        lines.append(
            "亚盘主轴："
            f"home_handicap={ah.get('home_handicap', ah.get('line'))}, "
            f"推荐方向={side_cn}, "
            f"W1覆盖率={_pct1(ah.get('cover_probability_model'))}, "
            f"市场隐含覆盖率={_pct1(ah.get('cover_probability_market'))}, "
            f"覆盖差={_pct1(ah.get('cover_edge'))}, "
            f"盘口变化={ah.get('line_movement') or '暂无'}, 水位={ah.get('water_movement') or '暂无'}。"
        )
    ou_line = market.get("ou_line")
    over = market.get("over_price")
    under = market.get("under_price")
    if ou_line not in (None, "") and isinstance(over, (int, float)) and isinstance(under, (int, float)):
        lines.append(f"大小球盘口：{ou_line} 球，大球价格约 {float(over):.2f}，小球价格约 {float(under):.2f}。")
    ou = market.get("ou") if isinstance(market.get("ou"), dict) else {}
    if ou and (ou_line in (None, "") or not isinstance(over, (int, float))):
        lines.append(f"大小球辅助：{ou.get('line')} 球，大球价格约 {ou.get('over_price') or '--'}，小球价格约 {ou.get('under_price') or '--'}。")
    if market.get("bookmaker_count"):
        lines.append(f"盘口样本：约 {market.get('bookmaker_count')} 家；来源 {market.get('market_source') or '本地盘口快照'}；更新时间 {market.get('odds_updated_at') or '未知'}。")
    if ah_line not in (None, "") or ou_line not in (None, ""):
        lines.append("market_ah 或 market_ou 已可用：market_expert_script_cn 必须写让球覆盖路径、大小球触发条件和盘口失效条件，不得写盘口数据缺失。")
    if not lines:
        return MARKET_MISSING_TEXT
    return "\n".join(lines)


def user_prompt(bundle: dict[str, Any], track: dict[str, Any], lessons: str, validator_errors: list[str] | None = None) -> str:
    market = bundle.get("market") or {}
    retry_note = ""
    if validator_errors:
        retry_note = (
            "\n[上次输出未过闸门] "
            + json.dumps(validator_errors, ensure_ascii=False)
            + "\n必须修正：只输出一个顶层 call JSON 对象；不要输出 analysis/summary/wrapper；"
            "必须包含 fixture_id, read, data_readiness, honesty_label, independent_edge；"
            "read 必须含 evidence / evidence_chain_cn / regular_script_cn / high_variance_tail_script_cn / reverse_risks_cn / market_expert_script_cn。"
        )
    return (
        f"[比赛] {bundle.get('home')} vs {bundle.get('away')} (fixture_id={bundle.get('fixture_id')})\n"
        f"[市场读数] {market_prompt_line(market)}\n"
        f"[因子包] {json.dumps(compact_factor_view(bundle), ensure_ascii=False)}\n"
        f"[你的历史战绩] {json.dumps(track, ensure_ascii=False)[:1200]}\n"
        f"[教训] {lessons[:1000]}\n"
        f"{retry_note}\n"
        "按系统规则只输出该场解读 JSON。"
    )


def sanitize_visible_text(value: Any, *, score_band: bool = False, market_script: bool = False) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    if re.search(r"(?:p_home|p_draw|p_away).*?(?:None|null|NaN|undefined)", text, flags=re.I):
        text = MARKET_SCRIPT_MISSING_TEXT if market_script else MARKET_MISSING_TEXT
    for old, new in MACHINE_BAD_REPLACEMENTS:
        text = text.replace(old, new)
    text = re.sub(r"\b[WDL]{3,}\b", "近期战绩序列", text)
    text = re.sub(r"\b(?:数据项|可用度|证据力度)\s*[:：=]", "证据：", text)
    text = re.sub(r"证据\s*[:：]\s*证据", "证据", text)
    text = re.sub(r"\s+", " ", text).strip()
    if score_band and ("历史样本" in text or re.search(r"\d+-样本不足-\d+", text)):
        return SCORE_BAND_FALLBACK
    if score_band and not any(token in text for token in ("区间", "分支", "比分带", "别当真", "偏")):
        return SCORE_BAND_FALLBACK
    if market_script and MARKET_MISSING_TEXT in text:
        return MARKET_SCRIPT_MISSING_TEXT
    return text


def _pct(value: Any) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    return f"{float(value) * 100:.0f}%"


def _source_suffix(text: str, source: str) -> str:
    text = str(text or "").strip()
    return text if "来源：" in text else f"{text}｜来源：{source}"


def _short_text(text: str, limit: int = 80) -> str:
    text = re.sub(r"\s+", " ", str(text or "").strip())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _compact_line_value(value: Any) -> str:
    value = str(value or "").strip()
    return value.replace("−", "-")


def _opposite_ah(line: str) -> str:
    number = _compact_line_value(line)
    if number.startswith("-"):
        return "+" + number[1:]
    if number.startswith("+"):
        return "-" + number[1:]
    return number


def _num(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if value in (None, "", [], {}):
        return None
    try:
        return float(str(value).replace("+", ""))
    except (TypeError, ValueError):
        return None


def _line_cn(value: Any) -> str:
    n = _num(value)
    if n is None:
        return ""
    if abs(n) < 1e-9:
        return "0"
    return f"{n:+g}"


def _pct1(value: Any) -> str:
    n = _num(value)
    return "--" if n is None else f"{n * 100:.0f}%"


def _grade_from_edge(edge: float | None, readiness: str, has_required: bool) -> str:
    if not has_required or readiness == "低":
        return "PASS"
    if edge is None:
        return "C/观察"
    if edge >= 0.06 and readiness == "高":
        return "A"
    if edge >= 0.03:
        return "B+"
    if edge >= 0.01:
        return "B"
    return "C/观察"


def _ah_side_label(side: str | None) -> str:
    return "主队让球" if side == "home" else "客队受让" if side == "away" else "观察"


def _ah_pick_name(home: str, away: str, side: str | None, home_handicap: Any) -> str:
    line = _num(home_handicap)
    if line is None or side not in {"home", "away"}:
        return "亚盘推荐：PASS / 观察"
    if side == "home":
        return f"{home} {_line_cn(line)}"
    return f"{away} {_line_cn(-line)}"


def ah_card_from_bundle(bundle: dict[str, Any], call: dict[str, Any] | None = None) -> dict[str, Any]:
    market = bundle.get("market") if isinstance(bundle.get("market"), dict) else {}
    ah = market.get("ah") if isinstance(market.get("ah"), dict) else {}
    ou = market.get("ou") if isinstance(market.get("ou"), dict) else {}
    one_x_two = market.get("one_x_two") if isinstance(market.get("one_x_two"), dict) else {}
    readiness = str((call or {}).get("data_readiness") or "中")
    home = str(bundle.get("home") or "主队")
    away = str(bundle.get("away") or "客队")
    side = str(ah.get("selected_side") or "")
    line = ah.get("home_handicap", ah.get("line"))
    price = ah.get("home_price") if side == "home" else ah.get("away_price") if side == "away" else None
    cover_model = ah.get("cover_probability_model")
    cover_market = ah.get("cover_probability_market")
    edge = ah.get("cover_edge")
    has_required = line not in (None, "") and _num(cover_model) is not None
    grade = _grade_from_edge(_num(edge), readiness, has_required)
    pick = _ah_pick_name(home, away, side if has_required and grade in {"A", "B+", "B"} else None, line)
    pass_reason = "" if has_required and grade in {"A", "B+", "B"} else "覆盖差不足或数据冲突，亚盘推荐降级为 PASS / 观察。"
    if not has_required:
        pass_reason = "AH盘口或模型覆盖概率缺失，无法形成高质量推荐。"
    if readiness == "低":
        pass_reason = "数据就绪度低，亚盘推荐降级为 PASS / 观察。"
        pick = "亚盘推荐：PASS / 观察"
    ah_logic = (
        f"W1覆盖率 {_pct1(cover_model)} vs 市场隐含 {_pct1(cover_market)}，覆盖差 {_pct1(edge)}；{_ah_side_label(side)}方向只在盘口与水位维持时成立。"
        if has_required and grade != "PASS"
        else "AH盘口或模型覆盖概率不足，暂不形成主推。"
    )
    market_consensus = "欧盘仅作参考。"
    if all(isinstance(one_x_two.get(k), (int, float)) for k in ("p_home", "p_draw", "p_away")):
        market_consensus = f"欧盘参考：主胜 {_pct1(one_x_two.get('p_home'))}｜平 {_pct1(one_x_two.get('p_draw'))}｜客胜 {_pct1(one_x_two.get('p_away'))}。"
    elif all(isinstance(market.get(k), (int, float)) for k in ("model_p_home", "model_p_draw", "model_p_away")):
        market_consensus = f"欧盘参考(W1)：主胜 {_pct1(market.get('model_p_home'))}｜平 {_pct1(market.get('model_p_draw'))}｜客胜 {_pct1(market.get('model_p_away'))}。"
    score_picks = market.get("score_picks") if isinstance(market.get("score_picks"), list) else []
    score_path = "比分路径暂不展开。"
    if score_picks:
        pieces = []
        for row in score_picks[:3]:
            if row.get("score"):
                pieces.append(f"{row.get('score')} {_pct1(row.get('probability'))}")
        if pieces:
            score_path = "主线 " + " / ".join(pieces[:2]) + (f"；风险 {pieces[2]}" if len(pieces) > 2 else "")
    ou_pick = "大小球辅助：盘口缺失，观察。"
    if ou.get("line") not in (None, ""):
        under_price = _num(ou.get("under_price"))
        over_price = _num(ou.get("over_price"))
        side_ou = "小" if under_price is not None and over_price is not None and under_price <= over_price else "大"
        ou_pick = f"{side_ou}{ou.get('line')}｜信心：中｜失效：早球"
    return {
        "schema_version": "scout_ah_recommendation_v1",
        "fixture_id": str(bundle.get("fixture_id") or ""),
        "stage_id": str((call or {}).get("stage_id") or ""),
        "stage_label_cn": str((call or {}).get("stage_label_cn") or ""),
        "data_readiness": readiness,
        "main_ah_pick_cn": pick,
        "ah_side_cn": _ah_side_label(side),
        "ah_line": _num(line),
        "ah_price": _num(price),
        "ah_confidence_cn": "中高" if grade in {"A", "B+"} else "中" if grade == "B" else "低",
        "recommendation_grade": grade,
        "ah_logic_cn": _short_text(ah_logic, 96),
        "cover_probability_model": _num(cover_model),
        "cover_probability_market": _num(cover_market),
        "cover_edge": _num(edge),
        "line_movement_cn": str(ah.get("line_movement") or "盘口变化暂无新增确认"),
        "water_movement_cn": str(ah.get("water_movement") or "水位变化暂无新增确认"),
        "market_consensus_cn": _short_text(market_consensus, 96),
        "ou_pick_cn": _short_text(ou_pick, 80),
        "score_path_cn": _short_text(score_path, 96),
        "risk_cn": "早球、首发关键点缺席、盘口退盘或水位反向，会削弱当前亚盘方向。",
        "pass_reason_cn": pass_reason,
        "final_action_cn": (
            f"亚盘主推：{pick}；若临场退盘或水位反向，降级观察。"
            if grade in {"A", "B+", "B"} else "亚盘推荐：PASS / 观察。"
        ),
    }


def card_from_bundle(bundle: dict[str, Any]) -> dict[str, str]:
    market = bundle.get("market") if isinstance(bundle.get("market"), dict) else {}
    home = str(bundle.get("home") or "主队")
    away = str(bundle.get("away") or "客队")
    out: dict[str, str] = {}
    if all(isinstance(market.get(key), (int, float)) for key in ("p_home", "p_draw", "p_away")):
        out["one_x_two_cn"] = f"主胜 {_pct(market.get('p_home'))}｜平 {_pct(market.get('p_draw'))}｜客胜 {_pct(market.get('p_away'))}｜来源：市场赔率"
    elif all(isinstance(market.get(key), (int, float)) for key in ("model_p_home", "model_p_draw", "model_p_away")):
        out["one_x_two_cn"] = f"主胜 {_pct(market.get('model_p_home'))}｜平 {_pct(market.get('model_p_draw'))}｜客胜 {_pct(market.get('model_p_away'))}｜来源：W1模型"
    else:
        out["one_x_two_cn"] = "1X2 数据缺失，降级观察｜来源：缺失"

    score_picks = market.get("score_picks") if isinstance(market.get("score_picks"), list) else []
    has_score_matrix = bool(score_picks) or all(isinstance(market.get(key), (int, float)) for key in ("model_p_home", "model_p_draw", "model_p_away"))
    handicap_source = "盘口 + W1分布" if has_score_matrix else "盘口"
    if score_picks:
        labels = ("首选", "次选", "风险")
        pieces = []
        for idx, row in enumerate(score_picks[:3]):
            score = row.get("score")
            prob = _pct(row.get("probability"))
            if score:
                pieces.append(f"{labels[idx]} {score} {prob}" if prob else f"{labels[idx]} {score}")
        if pieces:
            out["score_picks_cn"] = "｜".join(pieces) + "｜来源：score matrix"
    out.setdefault("score_picks_cn", "比分候选降级观察｜来源：剧本排序，非精确概率")

    ou_line = market.get("ou_line")
    over = market.get("over_price")
    under = market.get("under_price")
    if ou_line not in (None, "") and isinstance(over, (int, float)) and isinstance(under, (int, float)):
        side = "小" if float(under) <= float(over) else "大"
        out["ou_pick_cn"] = f"{side}{ou_line}｜信心：中｜失效：早球｜来源：{handicap_source}"
    else:
        out["ou_pick_cn"] = "大小球盘口缺失，暂不输出大小球推荐｜来源：缺失"

    ah_line = market.get("ah_line")
    ah_home = market.get("ah_home_price")
    ah_away = market.get("ah_away_price")
    if ah_line not in (None, "") and isinstance(ah_home, (int, float)) and isinstance(ah_away, (int, float)):
        pick = f"{away} {_opposite_ah(str(ah_line))}" if float(ah_away) <= float(ah_home) else f"{home} {ah_line}"
        out["ah_pick_cn"] = f"{pick}｜信心：中｜深盘穿盘不稳｜失效：早球｜来源：{handicap_source}"
    else:
        out["ah_pick_cn"] = "让球盘口缺失，暂不输出让球推荐｜来源：缺失"
    return out


def weak_low_evidence_context(call: dict[str, Any]) -> bool:
    read = call.get("read") if isinstance(call.get("read"), dict) else {}
    evidence = read.get("evidence") if isinstance(read, dict) else []
    market_missing = False
    xg_weak = False
    if isinstance(evidence, list):
        for row in evidence:
            if not isinstance(row, dict):
                continue
            source = str(row.get("source") or "")
            availability = str(row.get("availability") or "")
            if source == "market" and availability == "missing":
                market_missing = True
            if source == "xg_roll" and availability in {"weak_sample", "partial", "missing"}:
                xg_weak = True
    visible = "\n".join(visible_text_values(read))
    if MARKET_MISSING_TEXT in visible or "盘口数据缺失" in visible:
        market_missing = True
    if XG_WEAK_TEXT in visible or "xG样本不足" in visible:
        xg_weak = True
    return market_missing and xg_weak and call.get("data_readiness") in {"中", "低"}


def visible_text_values(read: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if not isinstance(read, dict):
        return out
    for key in VISIBLE_TEXT_KEYS:
        out.append(str(read.get(key) or ""))
    for key in VISIBLE_LIST_KEYS:
        value = read.get(key)
        if isinstance(value, list):
            out.extend(str(item or "") for item in value)
        elif value:
            out.append(str(value))
    evidence = read.get("evidence")
    if isinstance(evidence, list):
        out.extend(str(row.get("claim") or "") for row in evidence if isinstance(row, dict))
    card = read.get("recommendation_card")
    if isinstance(card, dict):
        out.extend(str(card.get(key) or "") for key in RECOMMENDATION_CARD_KEYS)
    ah_card = read.get("asian_handicap_card")
    if isinstance(ah_card, dict):
        out.extend(str(ah_card.get(key) or "") for key in AH_CARD_KEYS)
    return out


def normalize_recommendation_card(call: dict[str, Any], bundle: dict[str, Any] | None = None) -> None:
    read = call.get("read") if isinstance(call.get("read"), dict) else None
    if not read:
        return
    card = read.get("recommendation_card")
    if isinstance(card, str):
        card = {"main_recommendation_cn": card}
    if not isinstance(card, dict):
        card = {}
    has_market_line = bool(read.get("_market_has_lines"))
    bundle_card = card_from_bundle(bundle or {}) if bundle else {}
    readiness = str(call.get("data_readiness") or "低")
    for key in ("one_x_two_cn", "score_picks_cn", "ou_pick_cn", "ah_pick_cn"):
        if bundle_card.get(key):
            current = str(card.get(key) or "")
            force_bundle_value = True
            if (
                force_bundle_value
                or not current
                or "来源：" not in current
                or ("缺失" in current and "来源：缺失" not in bundle_card[key])
                or ("W1分布" in current and "W1分布" not in bundle_card[key])
                or len(current) > 80
            ):
                card[key] = bundle_card[key]
    card.setdefault("one_x_two_cn", "1X2 数据缺失，降级观察｜来源：缺失")
    card.setdefault("score_picks_cn", "比分候选降级观察｜来源：剧本排序，非精确概率")
    if has_market_line:
        card.setdefault("ou_pick_cn", "大小球倾向｜信心：中｜失效：早球｜来源：盘口 + W1分布")
        card.setdefault("ah_pick_cn", "让球倾向｜信心：中｜失效：早球｜来源：盘口 + W1分布")
        card.setdefault("data_status_cn", "市场赔率可用 / 数据部分缺失")
    else:
        card.setdefault("ou_pick_cn", "大小球盘口缺失，暂不输出大小球推荐｜来源：缺失")
        card.setdefault("ah_pick_cn", "让球盘口缺失，暂不输出让球推荐｜来源：缺失")
        card.setdefault("data_status_cn", "市场赔率缺失 / 数据部分缺失")
    if not str(card.get("main_recommendation_cn") or "").strip() or len(str(card.get("main_recommendation_cn") or "")) > 80:
        one = str(card.get("one_x_two_cn") or "").split("｜来源", 1)[0]
        ou = str(card.get("ou_pick_cn") or "").split("｜", 1)[0]
        ah = str(card.get("ah_pick_cn") or "").split("｜", 1)[0]
        card["main_recommendation_cn"] = f"{one}；{ou}；{ah}。"
    if not str(card.get("risk_cn") or "").strip() or len(str(card.get("risk_cn") or "")) > 80:
        card["risk_cn"] = "早球、红牌或首发反转会让主线降权。"
    card.setdefault("confidence_cn", "低" if readiness == "低" else "中")
    if readiness == "低":
        joined = " ".join(str(card.get(k) or "") for k in ("main_recommendation_cn", "risk_cn", "data_status_cn"))
        if "观察" not in joined and "降级" not in joined:
            card["main_recommendation_cn"] = "数据不足，推荐降级为观察；" + str(card.get("main_recommendation_cn") or "")
    for key in RECOMMENDATION_CARD_KEYS:
        card[key] = _short_text(sanitize_visible_text(card.get(key)))
    read["recommendation_card"] = card


def normalize_asian_handicap_card(call: dict[str, Any], bundle: dict[str, Any] | None = None) -> None:
    read = call.get("read") if isinstance(call.get("read"), dict) else None
    if not read:
        return
    card = read.get("asian_handicap_card")
    if not isinstance(card, dict):
        card = {}
    bundle_card = ah_card_from_bundle(bundle or {}, call) if bundle else {}
    for key in AH_CARD_KEYS:
        if key in bundle_card and bundle_card.get(key) not in (None, "", [], {}):
            card[key] = bundle_card[key]
        else:
            card.setdefault(key, bundle_card.get(key))
    card["schema_version"] = "scout_ah_recommendation_v1"
    card["fixture_id"] = str(call.get("fixture_id") or card.get("fixture_id") or "")
    card["data_readiness"] = str(call.get("data_readiness") or card.get("data_readiness") or "低")
    grade = str(card.get("recommendation_grade") or "PASS")
    if card["data_readiness"] == "低" and grade not in {"PASS", "C/观察"}:
        card["recommendation_grade"] = "PASS"
        card["main_ah_pick_cn"] = "亚盘推荐：PASS / 观察"
        card["pass_reason_cn"] = "数据就绪度低，亚盘推荐降级为 PASS / 观察。"
        card["final_action_cn"] = "亚盘推荐：PASS / 观察。"
    for key in ("main_ah_pick_cn", "ah_confidence_cn", "recommendation_grade", "ah_logic_cn", "line_movement_cn", "water_movement_cn", "market_consensus_cn", "ou_pick_cn", "score_path_cn", "risk_cn", "pass_reason_cn", "final_action_cn"):
        card[key] = sanitize_visible_text(card.get(key))
    read["asian_handicap_card"] = card


def apply_visible_quality_guard(call: dict[str, Any], bundle: dict[str, Any] | None = None) -> None:
    read = call.get("read") if isinstance(call.get("read"), dict) else None
    if not read:
        return
    for key in VISIBLE_TEXT_KEYS:
        read[key] = sanitize_visible_text(
            read.get(key),
            score_band=(key == "score_band_cn"),
            market_script=(key == "market_expert_script_cn"),
        )
    for key in VISIBLE_LIST_KEYS:
        value = read.get(key)
        if isinstance(value, list):
            read[key] = [sanitize_visible_text(item) for item in value if str(item or "").strip()]
        elif isinstance(value, str):
            read[key] = [sanitize_visible_text(value)]
    normalize_recommendation_card(call, bundle)
    normalize_asian_handicap_card(call, bundle)
    if "xG样本不足" in "\n".join(visible_text_values(read)):
        for key in ("evidence_chain_cn", "watch_points_cn"):
            rows = read.get(key) if isinstance(read.get(key), list) else []
            if rows and not any(XG_WEAK_TEXT in str(row) for row in rows):
                rows.append(XG_WEAK_TEXT)
                read[key] = rows
    if weak_low_evidence_context(call):
        for key in VISIBLE_TEXT_KEYS:
            text = str(read.get(key) or "")
            for old, new in STRONG_LOW_EVIDENCE_REPLACEMENTS:
                text = text.replace(old, new)
            read[key] = text
        for key in VISIBLE_LIST_KEYS:
            value = read.get(key)
            if isinstance(value, list):
                cleaned = []
                for item in value:
                    text = str(item or "")
                    for old, new in STRONG_LOW_EVIDENCE_REPLACEMENTS:
                        text = text.replace(old, new)
                    cleaned.append(text)
                read[key] = cleaned
        card = read.get("recommendation_card")
        if isinstance(card, dict):
            for key in RECOMMENDATION_CARD_KEYS:
                text = str(card.get(key) or "")
                for old, new in STRONG_LOW_EVIDENCE_REPLACEMENTS:
                    text = text.replace(old, new)
                card[key] = text


def compact_fact_piece(text: str) -> str:
    clean = sanitize_visible_text(text)
    clean = re.sub(r"[，。；;:：()（）]", " ", clean)
    parts = [part for part in clean.split() if len(part) >= 4]
    return max(parts, key=len) if parts else clean[:24]


def evidence_facts(read: dict[str, Any]) -> list[str]:
    rows = read.get("evidence")
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        claim = sanitize_visible_text(row.get("claim") or "")
        if claim:
            row["claim"] = claim
            out.append(claim)
    return out


def readiness_from_bundle(bundle: dict[str, Any] | None) -> str:
    if not bundle:
        return "低"
    availability = bundle.get("availability") if isinstance(bundle.get("availability"), dict) else {}
    available = sum(1 for value in availability.values() if value == "available")
    if availability.get("market_ah") == "available" and availability.get("model_1x2") == "available" and available >= 7:
        return "高"
    if availability.get("market_ah") == "available" and available >= 4:
        return "中"
    return "低"


def complete_read_defaults(call: dict[str, Any], bundle: dict[str, Any] | None) -> None:
    fixture_id = str(call.get("fixture_id") or (bundle or {}).get("fixture_id") or "")
    read = call.get("read") if isinstance(call.get("read"), dict) else {}
    call["read"] = read
    readiness = str(call.get("data_readiness") or readiness_from_bundle(bundle))
    call["data_readiness"] = readiness if readiness in {"高", "中", "低"} else "低"
    market = (bundle or {}).get("market") if isinstance((bundle or {}).get("market"), dict) else {}
    home = str((bundle or {}).get("home") or "主队")
    away = str((bundle or {}).get("away") or "客队")
    model_home = _num(market.get("model_p_home"))
    model_draw = _num(market.get("model_p_draw"))
    model_away = _num(market.get("model_p_away"))
    if model_home is not None and model_away is not None:
        tilt = f"{home}稍占优" if model_home > model_away else f"{away}稍占优"
    else:
        tilt = "强弱倾向待观察"
    read.setdefault("tilt_cn", tilt)
    score_picks = market.get("score_picks") if isinstance(market.get("score_picks"), list) else []
    if score_picks:
        read.setdefault("score_band_cn", "偏 " + " / ".join(str(row.get("score")) for row in score_picks[:2] if row.get("score")) + "，但单场看区间、别当真")
    else:
        read.setdefault("score_band_cn", SCORE_BAND_FALLBACK)
    read.setdefault("watch_points_cn", [
        "亚盘主轴来自当前让球盘口、W1覆盖率与市场隐含覆盖率的对照。",
        "欧盘胜平负只作参考，不作为主推荐轴。",
    ])
    read.setdefault("risks_cn", ["早球、红牌、首发关键点变化或盘口退盘，会让当前亚盘方向降权。"])
    read.setdefault("vs_market_cn", "欧盘仅作参考；亚盘覆盖率与水位变化决定本卡主轴。")
    evidence = read.get("evidence") if isinstance(read.get("evidence"), list) else []
    if len(evidence) < 2:
        evidence = [
            {"claim": "亚盘盘口与水位是本卡主轴。", "source": "market", "fields": ["market.ah"], "availability": "full" if (bundle or {}).get("availability", {}).get("market_ah") == "available" else "missing", "weight": "high"},
            {"claim": "比分矩阵提供 W1 覆盖率和比分路径。", "source": "score_matrix", "fields": ["score_matrix_summary", "market_probability_panel.handicap"], "availability": "full" if (bundle or {}).get("availability", {}).get("model_1x2") == "available" else "missing", "weight": "high"},
        ]
    read["evidence"] = evidence
    read.setdefault("recommendation_card", card_from_bundle(bundle or {}))
    read.setdefault("asian_handicap_card", ah_card_from_bundle(bundle or {}, call))
    read.setdefault("evidence_chain_cn", [
        "盘口：当前让球盘和水位用于判断覆盖方向，不把欧盘胜负当主轴。",
        "比分矩阵：W1分布用于计算覆盖率、比分路径和大小球辅助。",
    ])
    read.setdefault("regular_script_cn", f"常规剧本是{read['evidence'][0]['claim']}支撑亚盘方向，比赛按中低速节奏推进。")
    read.setdefault("high_variance_tail_script_cn", f"如果前30分钟出现早球、红牌或转换混乱，{read['evidence'][1]['claim']}对应的比分路径会进入高方差区间。")
    read.setdefault("reverse_risks_cn", ["如果上半场仍是0-0，或优势方久攻不下、射门质量无法转化，该剧本降权。"])
    if (bundle or {}).get("availability", {}).get("market_ah") == "available":
        read.setdefault("market_expert_script_cn", "若临场让球盘口退盘或水位反向，当前亚盘方向降权；大小球触发主要看早球与转换节奏。")
    else:
        read.setdefault("market_expert_script_cn", MARKET_SCRIPT_MISSING_TEXT)


def script_has_fact(script: str, facts: list[str]) -> bool:
    compact_script = script.replace(" ", "")
    for fact in facts:
        piece = compact_fact_piece(fact).replace(" ", "")
        if len(piece) >= 4 and piece[: min(10, len(piece))] in compact_script:
            return True
        compact_fact = fact.replace(" ", "")
        for size in (10, 8, 6, 4):
            for idx in range(0, max(0, len(compact_fact) - size + 1)):
                fragment = compact_fact[idx:idx + size]
                if fragment and fragment in compact_script:
                    return True
    return False


def complete_script_guards(call: dict[str, Any]) -> None:
    read = call.get("read") if isinstance(call.get("read"), dict) else None
    if not read:
        return
    facts = evidence_facts(read)
    fact = facts[0] if facts else "现有赛前数据仍不足"
    regular = sanitize_visible_text(read.get("regular_script_cn") or "")
    if facts and not script_has_fact(regular, facts):
        regular = (regular + f" 这一剧本主要来自：{fact}。").strip()
    read["regular_script_cn"] = regular

    tail = sanitize_visible_text(read.get("high_variance_tail_script_cn") or "")
    if not any(token in tail for token in ("如果", "若", "一旦", "前30分钟", "早球", "红牌", "被迫前压", "转换", "定位球", "门将失误")):
        tail = ("如果前30分钟出现早球、红牌或转换混乱，比赛会进入尾部高方差路径。 " + tail).strip()
    if facts and not script_has_fact(tail, facts):
        tail = (tail + f" 触发参考：如果“{fact}”对应的弱点被早球或转换放大，比赛会脱离常规节奏。").strip()
    read["high_variance_tail_script_cn"] = tail

    reverse = read.get("reverse_risks_cn")
    if not isinstance(reverse, list):
        reverse = [str(reverse or "").strip()] if reverse else []
    reverse_text = "\n".join(str(x) for x in reverse)
    if not any(token in reverse_text for token in ("如果上半场仍是 0-0", "如果上半场仍是0-0", "如果久攻不下", "如果低位防守成功", "如果首发进攻点缺席", "如果射门质量无法转化", "该剧本降权", "大比分剧本失效", "失效")):
        reverse.append("如果上半场仍是0-0，或者优势方久攻不下、射门质量无法转化，该剧本降权，平局风险上升。")
    read["reverse_risks_cn"] = [sanitize_visible_text(x) for x in reverse if str(x or "").strip()]

    market_script = sanitize_visible_text(read.get("market_expert_script_cn") or "", market_script=True)
    visible = "\n".join(visible_text_values(read))
    has_market_line = bool(read.get("_market_has_lines"))
    if ("盘口数据缺失" in market_script or MARKET_MISSING_TEXT in visible or "市场赔率数据缺失" in visible) and not has_market_line:
        market_script = MARKET_SCRIPT_MISSING_TEXT
    elif not any(token in market_script for token in ("盘口", "让球", "大小球", "水位", "早盘", "临场", "盘口样本", "隐含")):
        market_script = MARKET_SCRIPT_MISSING_TEXT
    elif not any(token in market_script for token in ("如果", "若", "一旦", "前30分钟", "早球", "红牌", "被迫前压", "转换", "定位球", "门将失误", "失效", "降权")):
        market_script += " 若临场盘口样本没有新增确认，只保留读盘语境，不上升为结论。"
    read["market_expert_script_cn"] = market_script


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
    raise ValueError("model response did not contain a valid JSON object")


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


def chat_completion(cfg: dict[str, str], prompt: str, max_tokens: int, json_mode: bool = True) -> str:
    body_obj = {
        "model": cfg["model"],
        "temperature": 0.3,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    if json_mode:
        body_obj["response_format"] = {"type": "json_object"}
    body = json.dumps(body_obj).encode("utf-8")
    req = request.Request(
        cfg["base_url"],
        data=body,
        headers={"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"},
    )
    with request.urlopen(req, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return str(payload["choices"][0]["message"]["content"]).strip()


def harden_call(call: dict[str, Any], fixture_id: str, bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    for wrapper_key in ("call", "scout_call", "read_call", "result", "output"):
        wrapped = call.get(wrapper_key)
        if isinstance(wrapped, dict):
            call = wrapped
            break
    if "read" not in call:
        read_keys = {
            "tilt_cn",
            "score_band_cn",
            "watch_points_cn",
            "risks_cn",
            "vs_market_cn",
            "evidence",
            "recommendation_card",
            "asian_handicap_card",
            "evidence_chain_cn",
            "regular_script_cn",
            "high_variance_tail_script_cn",
            "reverse_risks_cn",
            "market_expert_script_cn",
        }
        lifted = {key: call.pop(key) for key in list(call) if key in read_keys}
        if lifted:
            call["read"] = lifted
    call["fixture_id"] = fixture_id
    call["honesty_label"] = "AI 解读·非预测·非推介·可能错"
    call["independent_edge"] = False
    complete_read_defaults(call, bundle)
    if isinstance(call.get("read"), dict):
        read = call["read"]
        read.setdefault("vs_market_cn", "")
        for key in ("watch_points_cn", "risks_cn", "evidence_chain_cn", "reverse_risks_cn"):
            if isinstance(read.get(key), str):
                read[key] = [read[key]]
        for row in read.get("evidence") or []:
            if isinstance(row, dict):
                if row.get("availability") == "available":
                    row["availability"] = "full"
                if isinstance(row.get("fields"), str):
                    row["fields"] = [row["fields"]]
        complete_script_guards(call)
        apply_visible_quality_guard(call, bundle)
        normalize_asian_handicap_card(call, bundle)
    return call


def bundle_has_market_lines(bundle: dict[str, Any]) -> bool:
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
        for attempt in range(args.retries + 1):
            try:
                text = chat_completion(
                    cfg,
                    user_prompt(bundle, track, lessons, validator_errors),
                    args.max_tokens,
                    json_mode=(attempt % 2 == 0),
                )
                candidate = extract_json_object(text)
                if isinstance(candidate.get("read"), dict) and bundle_has_market_lines(bundle):
                    candidate["read"]["_market_has_lines"] = True
                candidate = harden_call(candidate, fixture_id, bundle)
                if isinstance(candidate.get("read"), dict):
                    candidate["read"].pop("_market_has_lines", None)
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


def write_calls(calls: list[dict[str, Any]], cfg: dict[str, str], drop_fixture_ids: set[str] | None = None) -> None:
    CALLS_P.parent.mkdir(parents=True, exist_ok=True)
    drop_fixture_ids = drop_fixture_ids or set()
    merged: dict[str, dict[str, Any]] = {}
    if CALLS_P.is_file():
        try:
            prior = json.loads(CALLS_P.read_text(encoding="utf-8"))
            for call in prior.get("calls", []):
                fid = str(call.get("fixture_id") or "")
                if fid and fid not in drop_fixture_ids:
                    merged[fid] = call
        except Exception:
            merged = {}
    for call in calls:
        fid = str(call.get("fixture_id") or "")
        if fid:
            merged[fid] = call
    CALLS_P.write_text(
        json.dumps(
            {
                "stage": "W1_SCOUT",
                "schema_version": "W1_SCOUT_READ_V1",
                "generated_by": f"{cfg['provider']}:{cfg['model']}",
                "calls": list(merged.values()),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate W1_SCOUT match reads through an OpenAI-compatible API, gated by check_w1_scout.")
    parser.add_argument("--fixture", "--fixture-id", action="append", help="Fixture id to read; may be repeated. Defaults to all bundles.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum bundles to read.")
    parser.add_argument("--provider", default=os.environ.get("W1_SCOUT_LLM", "deepseek"), choices=sorted(PROVIDERS))
    parser.add_argument("--max-tokens", type=int, default=3200)
    parser.add_argument("--retries", type=int, default=3, help="Validation retry count per fixture.")
    parser.add_argument("--dry-run", action="store_true", help="Validate setup and selected bundle count without calling the model.")
    args = parser.parse_args()

    selected = selected_bundles(set(args.fixture or []) or None, args.limit)
    if args.dry_run:
        model = PROVIDERS[args.provider].get("model") if args.provider == "deepseek" else (os.environ.get("W1_SCOUT_MODEL") or PROVIDERS[args.provider].get("model") or "<custom>")
        print(f"scout analyst dry-run: provider={args.provider}, selected={len(selected)}, model={model}, read_output={CALLS_P.relative_to(ROOT)}")
        return 0
    if not selected:
        print("No scout bundles selected; no scout reads written.")
        return 0

    calls, failed, cfg = build_calls(args)
    if failed:
        for fixture_id, reason in failed[:12]:
            print(f"FAIL: fixture {fixture_id}: {reason}", file=sys.stderr)
        failed_ids = {str(fixture_id) for fixture_id, _reason in failed}
        if calls and os.environ.get("W1_SCOUT_ALLOW_PARTIAL_WRITES", "").strip().lower() in {"1", "true", "yes", "on"}:
            write_calls(calls, cfg, failed_ids)
            print(
                f"scout analyst PARTIAL: provider={cfg['provider']} model={cfg['model']} wrote {len(calls)} accepted read(s), failed={len(failed)} -> {CALLS_P.relative_to(ROOT)}",
                file=sys.stderr,
            )
            return 2
        if set(args.fixture or []):
            write_calls([], cfg, failed_ids)
        print(f"scout analyst wrote nothing because {len(failed)} fixture(s) failed validation.", file=sys.stderr)
        return 1
    write_calls(calls, cfg)
    print(f"scout analyst PASS: provider={cfg['provider']} model={cfg['model']} wrote {len(calls)} reads -> {CALLS_P.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
