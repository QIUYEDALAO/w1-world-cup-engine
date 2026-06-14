#!/usr/bin/env python3
"""Convert football-data league CSV files into W1 rho calibration CSV schema."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import w1_rho_calibration as R  # noqa: E402


HEADER = list(R.REQUIRED_COLUMNS) + list(R.OPTIONAL_COLUMNS)


def clean_key(value: str) -> str:
    return value.strip().lower().replace("-", "").replace("_", "").replace(" ", "")


def find_col(row: dict[str, Any], *candidates: str) -> str | None:
    lookup = {clean_key(key): key for key in row}
    for candidate in candidates:
        key = lookup.get(clean_key(candidate))
        if key is not None:
            return key
    return None


def read_float(row: dict[str, Any], *candidates: str) -> float | None:
    key = find_col(row, *candidates)
    if key is None:
        return None
    raw = str(row.get(key, "")).strip()
    if raw == "":
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 1.0 else None


def read_int(row: dict[str, Any], *candidates: str) -> int | None:
    key = find_col(row, *candidates)
    if key is None:
        return None
    raw = str(row.get(key, "")).strip()
    if raw == "":
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def read_text(row: dict[str, Any], *candidates: str) -> str:
    key = find_col(row, *candidates)
    return str(row.get(key, "")).strip() if key is not None else ""


def normalize_date(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    # football-data usually uses dd/mm/yyyy. Keep ISO-like inputs unchanged.
    parts = value.replace("-", "/").split("/")
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        first, second, third = parts
        if len(third) == 4 and len(first) <= 2:
            return f"{third}-{int(second):02d}-{int(first):02d}"
        if len(first) == 4:
            return f"{first}-{int(second):02d}-{int(third):02d}"
    return value


def convert_row(row: dict[str, Any]) -> dict[str, Any] | None:
    home_goals = read_int(row, "FTHG")
    away_goals = read_int(row, "FTAG")
    home_odds = read_float(row, "AvgH", "B365H")
    draw_odds = read_float(row, "AvgD", "B365D")
    away_odds = read_float(row, "AvgA", "B365A")
    over_odds = read_float(row, "Avg>2.5", "BbAv>2.5", "B365>2.5")
    under_odds = read_float(row, "Avg<2.5", "BbAv<2.5", "B365<2.5")
    if None in (home_goals, away_goals, home_odds, draw_odds, away_odds, over_odds, under_odds):
        return None
    competition = read_text(row, "Div") or "football_data_league"
    if competition.upper() == "SYNTH":
        competition = "football_data_league"
    return {
        "match_date": normalize_date(read_text(row, "Date")),
        "home_team": read_text(row, "HomeTeam"),
        "away_team": read_text(row, "AwayTeam"),
        "closing_home_odds": home_odds,
        "closing_draw_odds": draw_odds,
        "closing_away_odds": away_odds,
        "closing_ou_main_line": 2.5,
        "closing_over_odds": over_odds,
        "closing_under_odds": under_odds,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "market_snapshot_lead_minutes": "",
        "competition": competition,
        "neutral_venue": 0,
        "lineup_completeness": "",
        "closing_ah_main_line": read_text(row, "AHh", "AHCh"),
        "closing_fair_total_override": "",
        "bookmaker_count": read_text(row, "BbMx>2.5", "Bb1X2", "BbOU") or "",
    }


def rows_from_file(input_path: Path) -> tuple[int, list[dict[str, Any]]]:
    read_count = 0
    valid_rows: list[dict[str, Any]] = []
    with input_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            read_count += 1
            converted = convert_row(row)
            if converted:
                valid_rows.append(converted)
    return read_count, valid_rows


def write_output(output_path: Path, rows: list[dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)


def input_files(input_path: Path | None, input_dir: Path | None) -> list[Path]:
    if input_dir:
        if not input_dir.is_dir():
            raise FileNotFoundError(f"input dir not found: {input_dir}")
        return sorted(path for path in input_dir.glob("*.csv") if path.is_file())
    if input_path:
        if not input_path.is_file():
            raise FileNotFoundError(f"input CSV not found: {input_path}")
        return [input_path]
    raise ValueError("Either --input or --input-dir is required")


def main() -> int:
    parser = argparse.ArgumentParser(description="football-data league CSV -> W1 rho calibration schema")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", type=Path)
    group.add_argument("--input-dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        files = input_files(args.input, args.input_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    total_read = 0
    all_rows: list[dict[str, Any]] = []
    for path in files:
        read_count, rows = rows_from_file(path)
        total_read += read_count
        all_rows.extend(rows)
        print(f"{path.name}: read={read_count} valid={len(rows)}")
    write_output(args.out, all_rows)
    valid_count = len(all_rows)
    print(f"converted football-data CSV: files={len(files)} read={total_read} valid={valid_count} out={args.out}")
    if valid_count < 500:
        print(f"WARN: valid sample {valid_count} < 500; rho report must remain production_ready=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
