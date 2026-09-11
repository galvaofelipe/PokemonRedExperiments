#!/usr/bin/env python3
"""Functional smoke: run eval twice, assert paired-seed score determinism."""

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
V3_DIR = REPO_ROOT / "v3"
sys.path.insert(0, str(V3_DIR))

from frozen.eval.runner import run_eval

DEFAULT_CHECKPOINT = V3_DIR / "runs/smoke/poke_40960_steps"
MAX_STEPS = 512
STATE_FILTER = "fresh_game"
SEED_FILTER = 0
ROM_PATH = REPO_ROOT / "pokered.gb"


def main():
    if not DEFAULT_CHECKPOINT.with_suffix(".zip").is_file():
        print(f"skip: checkpoint not found: {DEFAULT_CHECKPOINT.with_suffix('.zip')}")
        return 0
    if not ROM_PATH.is_file():
        print(f"skip: ROM not found: {ROM_PATH}")
        return 0

    scorecards = []
    for run_idx in range(2):
        with tempfile.TemporaryDirectory() as tmp:
            sess = Path(tmp) / f"eval_run_{run_idx}"
            card = run_eval(
                DEFAULT_CHECKPOINT,
                sess,
                gb_path=ROM_PATH,
                max_steps=MAX_STEPS,
                state_filter=STATE_FILTER,
                seed_filter=SEED_FILTER,
            )
            scorecards.append(card)
            print(f"run {run_idx}: mean={card['score']['mean']:.6f} max={card['score']['max']:.6f}")

    a, b = scorecards[0], scorecards[1]
    assert a["score"]["mean"] == b["score"]["mean"], (a["score"], b["score"])
    assert a["score"]["max"] == b["score"]["max"]

    required = {
        "scorecard_version",
        "score_version",
        "eval_suite_version",
        "commit",
        "checkpoint",
        "init_states",
        "score",
        "components_mean",
        "maps_seen_names",
        "episodes",
    }
    assert required.issubset(a.keys())
    assert a["episodes"][0]["components"]

    print("paired-seed determinism: OK")
    print(json.dumps(a, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
