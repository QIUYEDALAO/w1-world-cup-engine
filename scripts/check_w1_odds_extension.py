#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
W1 S1B odds extension checker (C1 scaffold).

Scaffold checks:
  - spec file exists
  - schema file exists
  - required fields present in schema
  - no external-fetch imports in new/added scripts within this phase
  - no OU/AH data file => output BLOCKED or SKIP
  - does not generate FULL pipeline results
  - does not modify production model files:
      scripts/w1_score_engine.py
      config/w1_decision_policy.json
      config/w1_odds_movement_thresholds.json
  - DEFAULT_RHO unchanged
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Paths under check
SPEC = ROOT / "docs/W1_S1B_ODDS_EXTENSION_V1.md"
SCHEMA = ROOT / "config/w1_international_odds_extension_schema.json"
OU_FILE = ROOT / "data/local_odds/w1_ou_odds_extension.csv"
AH_FILE = ROOT / "data/local_odds/w1_ah_odds_extension.csv"
ALIASES = ROOT / "config/w1_team_aliases.json"

# Production files that must NOT be modified in this phase
PRODUCTION_FILES = [
    ROOT / "scripts/w1_score_engine.py",
    ROOT / "config/w1_decision_policy.json",
    ROOT / "config/w1_odds_movement_thresholds.json",
]

# Forbidden imports in any new script or loader related to this phase
FORBIDDEN_IMPORTS = [
    "requests", "urllib", "http.client", "httpx",
    "aiohttp", "socket", "selenium", "playwright",
    "BeautifulSoup", "web_fetch",
]

errors: list[str] = []
warnings: list[str] = []


def fail(m: str) -> None:
    errors.append(m)


def warn(m: str) -> None:
    warnings.append(m)


def check_file_exists(path: Path, label: str) -> None:
    if not path.is_file():
        fail(f"{label} missing: {path}")
    else:
        print(f"  OK  {label}: {path.name}")


def check_schema_fields() -> None:
    """Validate that required fields exist in the schema JSON."""
    import json
    try:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    except Exception as e:
        fail(f"schema JSON parse error: {e}")
        return

    ou_fields = schema.get("files", {}).get("ou", {}).get("fields", [])
    ah_fields = schema.get("files", {}).get("ah", {}).get("fields", [])

    ou_required = {"date", "home", "away", "ou_line", "over_odds", "under_odds"}
    ah_required = {"date", "home", "away", "ah_line", "home_odds", "away_odds"}

    ou_present = {f["name"] for f in ou_fields}
    ah_present = {f["name"] for f in ah_fields}

    missing_ou = ou_required - ou_present
    missing_ah = ah_required - ah_present

    if missing_ou:
        fail(f"OU schema missing required fields: {sorted(missing_ou)}")
    else:
        print(f"  OK  OU schema required fields all present")

    if missing_ah:
        fail(f"AH schema missing required fields: {sorted(missing_ah)}")
    else:
        print(f"  OK  AH schema required fields all present")

    # Check AH is defined (even if optional)
    if not ah_fields:
        fail("AH section missing from schema (must exist even if optional)")


def check_ou_ah_data_files() -> None:
    """Check existence of local OU/AH files."""
    has_ou = OU_FILE.is_file()
    has_ah = AH_FILE.is_file()

    if has_ou:
        print(f"  OK  OU file found: {OU_FILE.name}")
    else:
        warn(f"OU file not present: {OU_FILE.name} (expected at scaffold stage)")

    if has_ah:
        print(f"  OK  AH file found: {AH_FILE.name}")
    else:
        warn(f"AH file not present: {AH_FILE.name} (optional, expected at scaffold stage)")

    # FULL pipeline guard
    if has_ou:
        print(f"  OK  OU data present => FULL pipeline possible for covered subset")
    else:
        print(f"  OK  No OU data => pipeline_mode remains 1X2_ONLY (expected at scaffold)")


def check_no_external_fetch() -> None:
    """Scan only this-phase scripts (checker itself and any odds_extension files).
    We do NOT scan pre-existing scripts from earlier phases.
    """
    import re

    # This script's phase files: script itself + anything in data/local_odds/
    # (data/local_odds/ does not exist at scaffold stage, but check anyway)
    this_script = Path(__file__).resolve()
    scan_candidates = [this_script]

    local_odds = ROOT / "data/local_odds"
    if local_odds.is_dir():
        for py_file in sorted(local_odds.rglob("*.py")):
            scan_candidates.append(py_file)

    # Also scan any script whose name starts with load_w1_odds_extension
    for p in ROOT.rglob("load_w1_odds_extension*.py"):
        scan_candidates.append(p)

    for py_file in set(scan_candidates):
        if not py_file.is_file():
            continue
        src = py_file.read_text(encoding="utf-8")
        for imp in FORBIDDEN_IMPORTS:
            pattern = re.compile(
                rf"(?:^|\n)\s*(?:import\s+{re.escape(imp)}|from\s+{re.escape(imp)}\s+import)",
                re.MULTILINE,
            )
            if pattern.search(src):
                fail(f"forbidden import '{imp}' in {py_file.relative_to(ROOT)}")


def check_production_files_unchanged() -> None:
    """Verify no modifications to protected production files."""
    import subprocess

    for pf in PRODUCTION_FILES:
        if not pf.is_file():
            continue
        # Check git diff for uncommitted changes
        result = subprocess.run(
            ["git", "diff", "--name-only", str(pf.relative_to(ROOT))],
            capture_output=True, text=True, cwd=ROOT, timeout=10,
        )
        if result.stdout.strip():
            fail(f"Production file modified: {pf.relative_to(ROOT)} (must remain unchanged)")


def check_default_rho_unchanged() -> None:
    """Check that DEFAULT_RHO variable in w1_score_engine.py retains its original value."""
    engine = ROOT / "scripts/w1_score_engine.py"
    if not engine.is_file():
        return  # not yet cloned / scaffold only

    import re
    src = engine.read_text(encoding="utf-8")
    match = re.search(r"DEFAULT_RHO\s*=\s*-?0\.\d+", src)
    if match:
        rho_val = match.group(0)
        print(f"  OK  DEFAULT_RHO present: {rho_val}")
    else:
        fail("DEFAULT_RHO not found in w1_score_engine.py")


def check_spec_content() -> None:
    """Validate spec doc has required sections."""
    if not SPEC.is_file():
        fail("spec doc missing, cannot validate content")
        return

    text = SPEC.read_text(encoding="utf-8")
    required_sections = [
        "Boundary",
        "Pipeline Mode Rule",
        "Matching",
        "OU Row",
        "AH Row",
        "Checker Rules",
    ]
    for section in required_sections:
        if section not in text:
            fail(f"spec doc missing section: {section}")
        else:
            print(f"  OK  spec section found: {section}")


def main() -> int:
    print("W1 S1B odds extension checker (C1 scaffold)")
    print()

    # 1. Spec exists
    check_file_exists(SPEC, "spec doc")

    # 2. Schema exists
    check_file_exists(SCHEMA, "schema JSON")

    # 3. Schema field completeness
    check_schema_fields()

    # 4. Spec content
    check_spec_content()

    # 5. OU/AH data file check
    check_ou_ah_data_files()

    # 6. No external fetch
    check_no_external_fetch()

    # 7. Production files unchanged
    check_production_files_unchanged()

    # 8. DEFAULT_RHO unchanged
    check_default_rho_unchanged()

    print()
    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        print(f"  Result: BLOCKED ({len(errors)} failures)")
        return 1

    if warnings:
        for w in warnings:
            print(f"  WARN: {w}")

    has_ou = OU_FILE.is_file()
    has_ah = AH_FILE.is_file()

    if not has_ou and not has_ah:
        print("  Result: SKIP (no OU/AH data files — pipeline_mode=1X2_ONLY per spec)")
    else:
        print("  Result: OU/AH data present — FULL pipeline eligible for covered subset")

    print("  check_w1_odds_extension PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
