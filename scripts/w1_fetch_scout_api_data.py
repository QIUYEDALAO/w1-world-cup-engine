#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compatibility wrapper for Scout api-football factor fetch.

The canonical fetcher is scripts/w1_scout_fetch_api_football.py. This wrapper
keeps the S10 operator command stable (`--fixture-id`) without adding a new API
path or changing persistence rules.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FETCHER = ROOT / "scripts/w1_scout_fetch_api_football.py"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Scout factors for one or more fixtures.")
    parser.add_argument("--fixture-id", action="append", dest="fixture_ids", help="Fixture id; may be repeated.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--include-started", action="store_true")
    args, rest = parser.parse_known_args()

    cmd = [sys.executable, str(FETCHER)]
    for fid in args.fixture_ids or []:
        cmd += ["--fixture", str(fid)]
    if args.limit is not None:
        cmd += ["--limit", str(args.limit)]
    if args.include_started:
        cmd.append("--include-started")
    cmd.extend(rest)
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
