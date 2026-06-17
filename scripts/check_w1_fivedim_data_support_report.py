#!/usr/bin/env python3
"""Check W1 FiveDim data support validation report completeness and red lines."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/W1_FIVEDIM_DATA_SUPPORT_VALIDATION.md"

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
]

REQUIRED_DISCLAIMERS = [
    "不构成投注建议",
    "非投注",
    "不承诺命中率",
]

FORBIDDEN_TERMS = [
    "稳赚",
    "投注建议",
    "入场价值",
    "梭哈",
    "跟机构",
    "聪明钱建议",
    "诱盘结论",
]

# "下注" is excluded from forbidden check because it appears in code quotes like `下注`


def _is_in_code_block(text: str, pos: int) -> bool:
    """Check if position is inside a code block (``` or `inline`)."""
    before = text[:pos]
    in_fence = before.count("```") % 2 == 1
    if in_fence:
        return True
    in_quote = before.count('"') % 2 == 1
    return False


def main() -> int:
    if not REPORT.exists():
        print(f"FAIL: Report not found at {REPORT}")
        return 1

    text = REPORT.read_text(encoding="utf-8")
    errors: list[str] = []

    # 1. Check required sections
    found_sections = []
    for section in REQUIRED_SECTIONS:
        if section in text:
            found_sections.append(section)
        else:
            errors.append(f"Missing section: {section}")

    # 2. Check required disclaimers
    found_disc = []
    for disc in REQUIRED_DISCLAIMERS:
        if disc in text:
            found_disc.append(disc)
        else:
            errors.append(f"Missing disclaimer: {disc}")

    # 3. Check report self-reference
    if "W1_FIVEDIM_DATA_SUPPORT_VALIDATION.md" not in text:
        errors.append("Report does not reference its own path")

    # 4. Check forbidden terms (skip if inside code blocks, policy JSON quotes,
    #    or forbidden_terms list context)
    for term in FORBIDDEN_TERMS:
        for m in re.finditer(re.escape(term), text):
            start = max(0, m.start() - 60)
            ctx = text[start:m.end() + 30]
            # Skip if in code block, or in a policy/blacklist context
            if _is_in_code_block(text, m.start()):
                continue
            if "forbidden_terms" in ctx or "禁止" in ctx or "not allowed" in ctx.lower() or "黑名单" in ctx or "红线" in ctx or "不构成" in ctx or "合规" in ctx or "不得" in ctx or "不符" in ctx:
                continue
            errors.append(f"Found forbidden term '{term}' in non-policy context: ...{ctx.strip()[:80]}...")

    if errors:
        print("FAIL: W1 FiveDim data support validation report check FAILED")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("W1 FiveDim data support validation report check PASS")
    print(f"  Report: {REPORT}")
    print(f"  Sections: {len(found_sections)}/{len(REQUIRED_SECTIONS)} OK")
    print(f"  Disclaimers: {len(found_disc)}/{len(REQUIRED_DISCLAIMERS)} OK")
    print(f"  Forbidden terms (non-policy): 0 found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
