#!/usr/bin/env python3
"""Hand-run smoke: submit a tiny job, drain queue, assert train→eval→Scorecard.

    cd v3 && ../.venv/bin/python verify/runner_smoke.py

Uses a scratch runner config so ledger/milestones/champion are not written to
the real v3/ workspace paths. Not part of pytest — run manually when idle.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
V3_DIR = REPO_ROOT / "v3"
BIN_DIR = V3_DIR / "bin"
SCRATCH_DIR = V3_DIR / "verify" / "scratch"
JOBS_QUEUED = V3_DIR / "jobs" / "queued"
RUNS_DIR = V3_DIR / "runs"
ROM_PATH = REPO_ROOT / "PokemonRed.gb"
JOB_NAME = "smoke_runner"
JOB_FILE = JOBS_QUEUED / f"{JOB_NAME}.json"
SMOKE_CONFIG = SCRATCH_DIR / "runner_config.json"


def _count_ledger_rows(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    return len(rows)


def _write_smoke_config() -> Path:
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    base = json.loads((BIN_DIR / "runner_config.json").read_text())
    base["ledger_path"] = str(SCRATCH_DIR / "ledger.tsv")
    base["milestones_path"] = str(SCRATCH_DIR / "milestones.jsonl")
    base["champion_json"] = str(SCRATCH_DIR / "champion.json")
    base["champion_dir"] = str(SCRATCH_DIR / "champion")
    SMOKE_CONFIG.write_text(json.dumps(base, indent=2) + "\n")
    return SMOKE_CONFIG


def main() -> int:
    if not ROM_PATH.is_file():
        print(f"skip: ROM not found: {ROM_PATH}")
        return 0

    python = V3_DIR.parent / ".venv" / "bin" / "python"
    if not python.is_file():
        python = Path(sys.executable)

    smoke_config = _write_smoke_config()
    ledger_path = Path(json.loads(smoke_config.read_text())["ledger_path"])
    champion_path = Path(json.loads(smoke_config.read_text())["champion_json"])
    ledger_before = _count_ledger_rows(ledger_path)
    had_champion = champion_path.is_file()

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
    print(f"scratch config: {smoke_config}")

    rc = subprocess.run(
        [str(python), str(BIN_DIR / "runner.py"), "--config", str(smoke_config)],
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
    scorecard = json.loads(scorecard_path.read_text())
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

    ledger_after = _count_ledger_rows(ledger_path)
    if ledger_after != ledger_before + 1:
        print(f"ledger row count expected {ledger_before + 1}, got {ledger_after}")
        return 1

    with ledger_path.open(newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    last = rows[-1]
    if last["status"] not in {"keep", "discard", "no-eval"}:
        print(f"unexpected ledger status: {last['status']}")
        return 1

    champion_score = "none"
    if not had_champion:
        if not champion_path.is_file():
            print(f"missing inaugural champion: {champion_path}")
            return 1
        champion = json.loads(champion_path.read_text())
        if champion.get("score_mean") != scorecard["score"]["mean"]:
            print("champion score_mean mismatch with scorecard")
            return 1
        champion_score = str(champion.get("score_mean"))
    elif champion_path.is_file():
        champion_score = str(json.loads(champion_path.read_text()).get("score_mean"))

    real_ledger = V3_DIR / "ledger.tsv"
    if real_ledger.is_file() and _count_ledger_rows(real_ledger) > 0:
        print(f"warning: real ledger exists at {real_ledger} (smoke used scratch only)")

    print(f"smoke OK: run_dir={run_dir}")
    print(f"scorecard: {scorecard_path}")
    print(f"ledger status={last['status']} champion={champion_score}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
