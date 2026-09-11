#!/usr/bin/env python3
"""Verify split extraction on eval_full telemetry (weak checkpoint → zero splits)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
V3_DIR = REPO_ROOT / "v3"
sys.path.insert(0, str(V3_DIR))

from frozen.splits import extract_splits_from_telemetry
from frozen.telemetry import iter_episode_files

TELEMETRY_DIR = V3_DIR / "runs/eval_full/telemetry"


def main():
    if not TELEMETRY_DIR.is_dir():
        print(f"skip: telemetry directory not found: {TELEMETRY_DIR}")
        return 0

    files = iter_episode_files(TELEMETRY_DIR)
    if not files:
        print(f"skip: no telemetry files in {TELEMETRY_DIR}")
        return 0

    print(f"checking {len(files)} telemetry file(s) in {TELEMETRY_DIR}")
    for path in files:
        achieved = extract_splits_from_telemetry(path)
        assert len(achieved) == 0, (
            f"expected zero splits in {path.name}, got {[a['name'] for a in achieved]}"
        )
        print(f"  {path.name}: 0 splits (OK)")

    print("zero-splits assertion: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
