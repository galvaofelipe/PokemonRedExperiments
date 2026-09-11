#!/usr/bin/env python3
"""Hand-run smoke: submit a tiny job, drain queue, assert train→eval→Scorecard.

    cd v3 && ../.venv/bin/python verify/runner_smoke.py

Not part of pytest — run manually when the machine is idle.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
V3_DIR = REPO_ROOT / "v3"
BIN_DIR = V3_DIR / "bin"
JOBS_QUEUED = V3_DIR / "jobs" / "queued"
RUNS_DIR = V3_DIR / "runs"
ROM_PATH = REPO_ROOT / "PokemonRed.gb"
JOB_NAME = "smoke_runner"
JOB_FILE = JOBS_QUEUED / f"{JOB_NAME}.json"


def main() -> int:
    if not ROM_PATH.is_file():
        print(f"skip: ROM not found: {ROM_PATH}")
        return 0

    python = V3_DIR.parent / ".venv" / "bin" / "python"
    if not python.is_file():
        python = Path(sys.executable)

    JOBS_QUEUED.mkdir(parents=True, exist_ok=True)
    job = {
        "name": JOB_NAME,
        "run_type": "cadence",
        "budget": {"total_timesteps": 4096},
        "num_envs": 2,
        "seed": 0,
        "init_state": "../init.state",
        "warm_start_from": None,
        "max_steps": 2048,
        "eval": {
            "enabled": True,
            "max_steps": 512,
            "state_filter": "fresh_game",
            "seed_filter": 0,
        },
    }
    JOB_FILE.write_text(json.dumps(job, indent=2) + "\n")
    print(f"wrote job: {JOB_FILE}")

    rc = subprocess.run(
        [str(python), str(BIN_DIR / "runner.py")],
        cwd=V3_DIR,
    ).returncode
    if rc != 0:
        print(f"runner exited {rc}")
        return rc

    done = list((V3_DIR / "jobs" / "done").glob(f"*{JOB_NAME}*.json"))
    if not done:
        failed = list((V3_DIR / "jobs" / "failed").glob(f"*{JOB_NAME}*"))
        print(f"job did not complete; failed artifacts: {failed}")
        return 1

    run_dirs = sorted(RUNS_DIR.glob(f"{JOB_NAME}_*"))
    if not run_dirs:
        print("no run directory found")
        return 1
    run_dir = run_dirs[-1]

    meta_path = run_dir / "run_metadata.json"
    scorecard_path = run_dir / "scorecard.json"
    train_log = run_dir / "train.log"

    for path in (meta_path, scorecard_path, train_log):
        if not path.is_file():
            print(f"missing artifact: {path}")
            return 1

    meta = json.loads(meta_path.read_text())
    head = subprocess.check_output(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    if meta.get("commit") != head:
        print(f"commit mismatch: meta={meta.get('commit')} head={head}")
        return 1

    if not train_log.read_text().strip():
        print("train.log is empty")
        return 1

    print(f"smoke OK: run_dir={run_dir}")
    print(f"scorecard: {scorecard_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
