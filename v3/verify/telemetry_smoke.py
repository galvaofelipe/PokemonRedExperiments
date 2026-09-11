#!/usr/bin/env python3
"""Functional smoke: 2 envs, ~300 steps each, print telemetry reader output."""

import sys
import tempfile
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
V3_DIR = REPO_ROOT / "v3"
sys.path.insert(0, str(V3_DIR))

from frozen.env.red_gym_env import RedGymEnv
from frozen.telemetry import iter_episode_files, iter_episode_records
from train import DefaultReward

STEPS = 300
SEED = 99


def make_env(sess_path, rank):
    return RedGymEnv(
        {
            "headless": True,
            "save_final_state": False,
            "print_rewards": False,
            "action_freq": 24,
            "init_state": str(REPO_ROOT / "init.state"),
            "max_steps": STEPS + 10,
            "save_video": False,
            "fast_video": True,
            "session_path": sess_path,
            "gb_path": str(REPO_ROOT / "pokered.gb"),
            "instance_id": str(rank),
            "reward": DefaultReward(reward_scale=0.5, explore_weight=0.25),
        }
    )


def run_env(env, rng):
    env.reset(seed=SEED)
    for _ in range(STEPS):
        env.step(int(rng.integers(0, 7)))
    env.close()


def main():
    rng = np.random.default_rng(SEED)
    with tempfile.TemporaryDirectory() as tmp:
        sess_path = Path(tmp) / "smoke"
        sess_path.mkdir()
        envs = [make_env(sess_path, rank) for rank in range(2)]
        for env in envs:
            run_env(env, rng)

        telemetry_dir = sess_path / "telemetry"
        files = iter_episode_files(telemetry_dir)
        print(f"telemetry files ({len(files)}):")
        for path in files:
            print(f"  {path.name}")
            records = [r for r in iter_episode_records(path) if "snapshot" in r]
            if not records:
                print("    (no records)")
                continue
            first, last = records[0], records[-1]
            print(
                f"    steps={len(records)} "
                f"first=({first['step']},{first['x']},{first['y']},map={first['map']}) "
                f"last=({last['step']},{last['x']},{last['y']},map={last['map']})"
            )


if __name__ == "__main__":
    main()
