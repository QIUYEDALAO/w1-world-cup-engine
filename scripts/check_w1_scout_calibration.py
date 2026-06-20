#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Checker for W1 Scout calibration readiness stub (S24)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/w1_calibration_policy.json"
CALIBRATION = ROOT / "scripts/w1_scout_calibration.py"
RECOMMENDATION = ROOT / "scripts/w1_recommendation_policy.py"
TRAINED_ARTIFACT = ROOT / "data/calibration/w1_calibration_model.json"


def fail(message: str) -> None:
    raise SystemExit(f"W1 scout calibration check FAIL: {message}")


def assert_contains(path: Path, tokens: list[str]) -> None:
    if not path.is_file():
        fail(f"missing {path.relative_to(ROOT)}")
    text = path.read_text(encoding="utf-8")
    for token in tokens:
        if token not in text:
            fail(f"{path.relative_to(ROOT)} missing token {token}")


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if config.get("schema_version") != "w1_calibration_policy_v1":
        fail("config schema_version mismatch")
    if config.get("status") != "untrained":
        fail("S24 config status must be untrained")
    if config.get("method") != "raw_passthrough":
        fail("S24 config method must be raw_passthrough")
    thresholds = config.get("thresholds") or {}
    for key in ("global_sigmoid_min_samples", "line_family_min_samples", "isotonic_min_samples"):
        if int(thresholds.get(key) or 0) < 100:
            fail(f"{key} must require at least 100 samples")
    assert_contains(CALIBRATION, [
        "--diagnose",
        "--json",
        "--fixture-id",
        "--self-test",
        "fit_global_sigmoid_stub",
        "fit_isotonic_stub",
        "fit_line_family_stub",
        "NotImplementedError",
        "trained_artifact_loaded",
        "raw_passthrough",
    ])
    assert_contains(RECOMMENDATION, [
        "build_calibration_metadata",
        "independent_settled_recommend_sample_count",
        "cover_prob_calibrated",
        "edge_calibrated",
        "trained_artifact_loaded",
    ])
    if TRAINED_ARTIFACT.is_file():
        try:
            payload = json.loads(TRAINED_ARTIFACT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        if str(payload.get("status") or "").lower() == "trained" or payload.get("trained_artifact_loaded") is True:
            fail("trained calibration artifact exists; S24 must not create/load trained artifacts")
    subprocess.check_call([sys.executable, str(CALIBRATION), "--self-test"], cwd=str(ROOT))
    raw = subprocess.check_output([sys.executable, str(CALIBRATION), "--json"], cwd=str(ROOT), text=True)
    diag = json.loads(raw)
    if diag.get("calibration_status") != "untrained":
        fail("diagnosis calibration_status must be untrained")
    if diag.get("calibration_method") != "raw_passthrough":
        fail("diagnosis calibration_method must be raw_passthrough")
    if diag.get("trained_artifact_loaded") is not False:
        fail("diagnosis must not load trained artifact")
    if diag.get("calibration_artifact"):
        fail("S24 diagnosis must not claim calibration artifact")
    if not diag.get("cover_prob_calibrated_equals_raw") or not diag.get("edge_calibrated_equals_raw"):
        fail("untrained diagnosis must assert raw passthrough")
    readiness = diag.get("readiness") or {}
    if set(readiness) != {"global_sigmoid", "line_family", "isotonic"}:
        fail("diagnosis readiness keys mismatch")
    if any(value != "insufficient_sample" for value in readiness.values()):
        fail("current S24 readiness must be insufficient_sample")
    print("W1 scout calibration check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
