#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_w1_fivedim_data_support_report.py
========================================
W1 FiveDim 数据支持验证报告 checker。
检查报告完整性、关键章节、红线词汇。

红线词汇检查逻辑：
- 在红线检查章节中列出禁止词做负面检查 -> 允许（用于说明）
- 在实际分析/结论/推荐类语言中使用 -> 禁止
- 在 disclaimer 否定句式中使用 -> 允许（"不构成投注建议"）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "reports/W1_FIVEDIM_DATA_SUPPORT_VALIDATION.md"


def check_report_exists() -> bool:
    return REPORT_PATH.is_file()


def read_report() -> str:
    return REPORT_PATH.read_text(encoding="utf-8") if REPORT_PATH.is_file() else ""


# ---------- 关键章节检查 ----------
REQUIRED_SECTIONS = [
    "FiveDim Lite",
    "基础比赛数据",
    "W1 市场与概率底座",
    "绝对实力面",
    "战术高阶指标",
    "阵型化学反应",
    "市场与热度智慧",
    "外部物理与环境",
    "赛前/赛后使用边界",
    "BLOCKER",
    "红线",
    "不构成投注建议",
    "非投注",
]

# ---------- 高风险词汇（禁止出现 非免责/非负面清单 上下文） ----------
# 我们使用严格匹配模式：若整个报告中出现非免责用法的这些词则报错
# "投注建议" 只出现在"不构成投注建议"时允许
# "下注"、"稳赚"等出现在红线检查章节时允许
FORBIDDEN_PATTERNS = {
    # 以下模式会被红线检查章节列出的禁用词模式匹配，所以我们需要跳过检查表部分
    "稳赚": "警告",
    "下注": "警告（仅在红线章节和免责条款中出现时允许）",
    "入场价值": "警告（仅在红线章节中出现时允许）",
    "梭哈": "WARN",
    "跟机构": "警告（仅在红线章节中出现时允许）",
    "聪明钱建议": "WARN（不同于【聪明钱】参数引用）",
    "诱盘结论": "WARN（不同于【诱盘】参数名被动引用）",
    "竞彩推荐": "WARN",
    "保赢": "WARN",
    "包赢": "WARN",
}


def is_in_blocklist_pattern(text: str, term: str, report_lines: list[str]) -> bool:
    """检查某个词是否在报告规则允许的范围（红线检查、负面清单）中使用。"""
    for line in report_lines:
        if term in line:
            # 如果在红线检查章节（第 11 章 红线风险之后的章节），或以检查表形式出现
            stripped = line.strip()
            if stripped.startswith(("- " + term, "| \"" + term)):
                return False  # 在检查/列举中，允许
            # 如果在否定句式中：不构成投注建议/不包含
            if "不" + term in line or "无" + term in line or "禁止" in line or "不存在" in line or "未" in line:
                return False  # 免责/否定句式，允许
    return True


def check_forbidden(text: str) -> list[str]:
    """检查红线词汇，排除红线条目表和免责上下文"""
    lines = text.split("\n")
    found = []
    for term in FORBIDDEN_PATTERNS:
        term_lower = term.lower()
        for i, line in enumerate(lines):
            if term_lower not in line.lower():
                continue
            stripped = line.strip()
            # 在红线检查章节（以|或-开头列举的禁止项）中允许
            if stripped.startswith("|") and f"\"{term}\"" in line:
                continue  # 表格章节中的禁止列表
            if stripped.startswith("-") and term in stripped:
                continue  # 列表章节
            # 在"不存在"/"未发现"/"禁止"上下文中允许
            if "不存在" in line or "未" in line or "禁止" in line or "不提供" in line:
                continue
            # 在"不构成"+ term 的否定句中允许
            if "不构成" in line and term in line:
                continue
            # 在附录/红线结果检查表中允许
            if "红线" in line and ("❌" in line or "✅" in line):
                continue
            if "本报告不" in line:
                continue
            found.append(f"第{i+1}行: {stripped[:80]}")
            # 每项只报第一个命中
            break
    return found


# ---------- 必须包含的关键词汇 ----------
REQUIRED_PHRASES = [
    "研究参考",
    "不构成投注建议",
    "market_implied",
    "数据支持验证",
]


def check_sections(text: str) -> dict[str, Any]:
    missing = []
    present = []
    for section in REQUIRED_SECTIONS:
        if section.lower() in text.lower():
            present.append(section)
        else:
            missing.append(section)
    return {"present": present, "missing": missing}


def check_required_phrases(text: str) -> list[str]:
    missing = []
    for phrase in REQUIRED_PHRASES:
        if phrase not in text:
            missing.append(phrase)
    return missing


def check_dimensions(text: str) -> dict[str, bool]:
    """检查五维各维度的分析深度。"""
    return {
        "维度一有可进入第一版判断": bool(re.search(r"可进入第一版字段", text)) or bool(re.search(r"必须保留字段", text)),
        "维度二有赛前/赛后边界": bool(re.search(r"赛前/赛后使用边界", text)),
        "维度三有降级方案": bool(re.search(r"降级", text)) and bool(re.search(r"阵型化学反应", text)),
        "维度四有红线检查": bool(re.search(r"红线", text)) and bool(re.search(r"市场与热度智慧", text)),
        "维度五有可行性评估": bool(re.search(r"可自动计算", text)) or bool(re.search(r"休息天数", text)),
    }


def check_league_coverage(text: str) -> list[str]:
    """检查联赛覆盖分析。"""
    required_leagues = ["世界杯", "欧冠", "英超", "西甲", "意甲", "德甲", "法甲"]
    missing = []
    for league in required_leagues:
        if league not in text:
            missing.append(league)
    return missing


def check_fivedim_lite_fields(text: str) -> dict[str, list[str]]:
    """检查 FiveDim Lite 字段分类。"""
    sections = {
        "A. 第一版必须保留字段": "必须保留",
        "B. 第一版建议保留字段": "建议保留",
        "C. 仅 Analyst View 字段": "仅 Analyst",
        "D. 暂不启用字段": "暂不启用",
        "E. 未来增强字段": "未来增强",
        "F. BLOCKER": "BLOCKER",
    }
    missing = []
    present = []
    for label, keyword in sections.items():
        if label in text or keyword in text:
            present.append(label)
        else:
            missing.append(label)
    return {"present": present, "missing": missing}


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    if not check_report_exists():
        print("FAIL: reports/W1_FIVEDIM_DATA_SUPPORT_VALIDATION.md does not exist")
        return 1

    text = read_report()

    # 1. 章节完整性
    sec = check_sections(text)
    for s in sec["missing"]:
        errors.append(f"缺失关键章节: {s}")

    # 2. 红线词汇（排除免责和列举上下文）
    forbidden = check_forbidden(text)
    for f in forbidden:
        errors.append(f"发现红线词: {f}")

    # 3. 必备短语
    missing_phrases = check_required_phrases(text)
    for phrase in missing_phrases:
        warnings.append(f"缺少必备短语: {phrase}")

    # 4. 维度分析深度
    dims = check_dimensions(text)
    for key, ok in dims.items():
        if not ok:
            warnings.append(f"维度分析可能不足: {key}")

    # 5. 联赛覆盖
    missing_leagues = check_league_coverage(text)
    for league in missing_leagues:
        warnings.append(f"联赛覆盖分析缺失: {league}")

    # 6. FiveDim Lite 字段分类
    fields = check_fivedim_lite_fields(text)
    for field in fields["missing"]:
        warnings.append(f"缺少字段分类: {field}")

    # ---------- 输出 ----------
    if errors:
        print("FAIL")
        for err in errors:
            print(f"  ❌ {err}")
        if warnings:
            for warn in warnings:
                print(f"  ⚠️  {warn}")
        return 1

    if warnings:
        print("PASS (with warnings)")
        for warn in warnings:
            print(f"  ⚠️  {warn}")
    else:
        print("PASS")
        print("  ✅ 所有检查项通过")

    print(f"\n报告路径: {REPORT_PATH}")
    print(f"文件大小: {len(text)} bytes")
    print(f"估计字数: {len(text.split())}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
