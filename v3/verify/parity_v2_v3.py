#!/usr/bin/env python3
"""Step-by-step parity check: v2 RedGymEnv vs v3 frozen env core."""

import argparse
import os
import sys
from contextlib import contextmanager
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
V2_DIR = REPO_ROOT / "v2"
V3_DIR = REPO_ROOT / "v3"
WRAM_START = 0xC000
WRAM_END = 0xE000


@contextmanager
def cwd(path: Path):
    prev = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def ram_snapshot(pyboy) -> bytes:
    return bytes(pyboy.memory[i] for i in range(WRAM_START, WRAM_END))


def compare_obs(obs2, obs3, step: int):
    v2_event_len = len(obs2["events"])
    assert len(obs3["events"]) == 2560, f"step {step}: v3 events len {len(obs3['events'])}"
    if not np.array_equal(obs3["events"][:v2_event_len], obs2["events"]):
        raise AssertionError(f"step {step}: events prefix mismatch")

    for key in ("screens", "health", "level", "badges", "map", "recent_actions"):
        if not np.array_equal(obs2[key], obs3[key]):
            raise AssertionError(f"step {step}: obs[{key}] mismatch")


def compare_agent_stats(stats2, stats3, step: int):
    assert stats2.keys() == stats3.keys(), f"step {step}: agent_stats keys differ"
    for key in stats2:
        v2 = stats2[key]
        v3 = stats3[key]
        if isinstance(v2, list):
            assert v2 == v3, f"step {step}: agent_stats[{key}] list mismatch"
        else:
            assert v2 == v3, f"step {step}: agent_stats[{key}] {v2} != {v3}"


def make_v2_env(sess_path: Path):
    sys.path.insert(0, str(V2_DIR))
    from red_gym_env_v2 import RedGymEnv

    config = {
        "headless": True,
        "save_final_state": False,
        "print_rewards": False,
        "action_freq": 24,
        "init_state": str(REPO_ROOT / "init.state"),
        "max_steps": 2048 * 80,
        "save_video": False,
        "fast_video": True,
        "session_path": sess_path,
        "gb_path": str(REPO_ROOT / "PokemonRed.gb"),
        "reward_scale": 0.5,
        "explore_weight": 0.25,
    }
    with cwd(V2_DIR):
        return RedGymEnv(config)


def make_v3_env(sess_path: Path):
    sys.path.insert(0, str(V3_DIR))
    from frozen.env.red_gym_env import RedGymEnv
    from train import DefaultReward

    config = {
        "headless": True,
        "save_final_state": False,
        "print_rewards": False,
        "action_freq": 24,
        "init_state": str(REPO_ROOT / "init.state"),
        "max_steps": 2048 * 80,
        "save_video": False,
        "fast_video": True,
        "session_path": sess_path,
        "gb_path": str(REPO_ROOT / "PokemonRed.gb"),
        "reward": DefaultReward(reward_scale=0.5, explore_weight=0.25),
    }
    return RedGymEnv(config)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=512)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    actions = rng.integers(0, 7, size=args.steps)

    v2_sess = REPO_ROOT / "v3" / "runs" / "parity_v2"
    v3_sess = REPO_ROOT / "v3" / "runs" / "parity_v3"
    v2_sess.mkdir(parents=True, exist_ok=True)
    v3_sess.mkdir(parents=True, exist_ok=True)

    env2 = make_v2_env(v2_sess)
    env3 = make_v3_env(v3_sess)

    with cwd(V2_DIR):
        env2.reset(seed=args.seed)
    env3.reset(seed=args.seed)

    for step, action in enumerate(actions):
        with cwd(V2_DIR):
            obs2, r2, _, d2, _ = env2.step(int(action))
        obs3, r3, _, d3, _ = env3.step(int(action))

        if abs(r2 - r3) > 1e-9:
            raise AssertionError(f"step {step}: reward {r2} != {r3}")

        compare_obs(obs2, obs3, step)
        compare_agent_stats(env2.agent_stats[-1], env3.agent_stats[-1], step)

        ram2 = ram_snapshot(env2.pyboy)
        ram3 = ram_snapshot(env3.pyboy)
        if ram2 != ram3:
            for addr in range(WRAM_START, WRAM_END):
                if env2.pyboy.memory[addr] != env3.pyboy.memory[addr]:
                    raise AssertionError(
                        f"step {step}: WRAM mismatch at 0x{addr:X}"
                    )

        if d2 != d3:
            raise AssertionError(f"step {step}: done flags differ d2={d2} d3={d3}")
        if d2:
            break

    env2.close()
    env3.close()
    print(f"PASS: {step + 1} steps")


if __name__ == "__main__":
    main()
