#!/usr/bin/env python3
"""Capture telemetry fixtures for tests. Expected values from independent RAM reads."""

import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
V3_DIR = REPO_ROOT / "v3"
sys.path.insert(0, str(V3_DIR))

from frozen.env.red_gym_env import RedGymEnv
from frozen.ram_map import (
    EVENT_FLAG_BYTES_OBS,
    SNAPSHOT_BASE,
    SNAPSHOT_END_INCLUSIVE,
    SNAPSHOT_SIZE,
    W_CUR_MAP,
    W_EVENT_FLAGS_START,
    W_OBTAINED_BADGES,
    W_PARTY_COUNT,
    W_PARTY_MON_HP,
    W_PARTY_MON_LEVEL,
    W_PARTY_MON_MAX_HP,
    W_PARTY_SPECIES,
    W_PLAY_TIME_FRAMES,
    W_PLAY_TIME_HOURS,
    W_PLAY_TIME_MAXED,
    W_PLAY_TIME_MINUTES,
    W_PLAY_TIME_SECONDS,
    W_POKEDEX_OWNED_START,
    W_POKEDEX_SEEN_START,
    W_X_COORD,
    W_Y_COORD,
)
from train import DefaultReward

FIXTURES_DIR = V3_DIR / "tests" / "fixtures"

DEX_BYTES = 19
DEX_LAST_BYTE_MASK = 0x7F
PROBE_EVERY = 25
EP1_STEPS = 150
EP2_STEPS = 100
SEED = 42


def capture_snapshot(pyboy):
    return bytes(pyboy.memory[SNAPSHOT_BASE : SNAPSHOT_END_INCLUSIVE + 1])


def read_hp_pair(snapshot, hp_offset):
    return 256 * snapshot[hp_offset] + snapshot[hp_offset + 1]


def independent_decode(snapshot, step, action):
    party_count = snapshot[W_PARTY_COUNT - SNAPSHOT_BASE]
    badges = snapshot[W_OBTAINED_BADGES - SNAPSHOT_BASE].bit_count()

    event_off = W_EVENT_FLAGS_START - SNAPSHOT_BASE
    event_count = int.from_bytes(
        snapshot[event_off : event_off + EVENT_FLAG_BYTES_OBS], "little"
    ).bit_count()

    owned_off = W_POKEDEX_OWNED_START - SNAPSHOT_BASE
    owned = bytearray(snapshot[owned_off : owned_off + DEX_BYTES])
    owned[-1] &= DEX_LAST_BYTE_MASK
    dex_caught = int.from_bytes(owned, "little").bit_count()

    seen_off = W_POKEDEX_SEEN_START - SNAPSHOT_BASE
    seen = bytearray(snapshot[seen_off : seen_off + DEX_BYTES])
    seen[-1] &= DEX_LAST_BYTE_MASK
    dex_seen = int.from_bytes(seen, "little").bit_count()

    levels = [snapshot[a - SNAPSHOT_BASE] for a in W_PARTY_MON_LEVEL]
    species = [snapshot[a - SNAPSHOT_BASE] for a in W_PARTY_SPECIES]
    level_sum = sum(levels[i] for i in range(party_count))

    hp_sum = sum(read_hp_pair(snapshot, a - SNAPSHOT_BASE) for a in W_PARTY_MON_HP)
    max_hp_sum = sum(
        read_hp_pair(snapshot, a - SNAPSHOT_BASE) for a in W_PARTY_MON_MAX_HP
    )
    hp_frac = hp_sum / max(max_hp_sum, 1)

    return {
        "step": step,
        "x": snapshot[W_X_COORD - SNAPSHOT_BASE],
        "y": snapshot[W_Y_COORD - SNAPSHOT_BASE],
        "map": snapshot[W_CUR_MAP - SNAPSHOT_BASE],
        "badges": badges,
        "event_count": event_count,
        "dex_seen": dex_seen,
        "dex_caught": dex_caught,
        "level_sum": level_sum,
        "clock_hours": snapshot[W_PLAY_TIME_HOURS - SNAPSHOT_BASE],
        "clock_maxed": snapshot[W_PLAY_TIME_MAXED - SNAPSHOT_BASE],
        "clock_minutes": snapshot[W_PLAY_TIME_MINUTES - SNAPSHOT_BASE],
        "clock_seconds": snapshot[W_PLAY_TIME_SECONDS - SNAPSHOT_BASE],
        "clock_frames": snapshot[W_PLAY_TIME_FRAMES - SNAPSHOT_BASE],
        "last_action": action,
        "pcount": party_count,
        "hp_frac": hp_frac,
        **{f"level_{i}": levels[i] for i in range(6)},
        **{f"ptype_{i}": species[i] for i in range(6)},
    }


def run_scenario(name, init_state, instance_id="test0"):
    rng = np.random.default_rng(SEED)
    expected_probes = []
    probed_snapshots = []

    with tempfile.TemporaryDirectory() as tmp:
        sess_path = Path(tmp) / "session"
        sess_path.mkdir()

        config = {
            "headless": True,
            "save_final_state": False,
            "print_rewards": False,
            "action_freq": 24,
            "init_state": str(REPO_ROOT / init_state),
            "max_steps": EP1_STEPS + EP2_STEPS + 10,
            "save_video": False,
            "fast_video": True,
            "session_path": sess_path,
            "gb_path": str(REPO_ROOT / "pokered.gb"),
            "instance_id": instance_id,
            "reward": DefaultReward(reward_scale=0.5, explore_weight=0.25),
        }
        env = RedGymEnv(config)
        env.reset(seed=SEED)

        global_step = 0
        for ep in range(2):
            if ep == 1:
                env.reset(seed=SEED + 1)
            ep_steps = EP1_STEPS if ep == 0 else EP2_STEPS
            for _ in range(ep_steps):
                action = int(rng.integers(0, 7))
                env.step(action)
                if global_step % PROBE_EVERY == 0:
                    snap = capture_snapshot(env.pyboy)
                    assert len(snap) == SNAPSHOT_SIZE
                    step_idx = env.step_count - 1
                    expected_probes.append(
                        {
                            "episode": ep + 1,
                            "global_step": global_step,
                            "step": step_idx,
                            "expected": independent_decode(snap, step_idx, action),
                        }
                    )
                    probed_snapshots.append(
                        {
                            "episode": ep + 1,
                            "global_step": global_step,
                            "snapshot": snap,
                        }
                    )
                global_step += 1

        env.close()

        telemetry_dir = sess_path / "telemetry"
        files = sorted(telemetry_dir.glob("*.telemetry.gz"))
        assert len(files) == 2, f"expected 2 episode files, got {len(files)}"

        out_dir = FIXTURES_DIR / f"telemetry_{name}"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True)
        telemetry_out = out_dir / "telemetry"
        telemetry_out.mkdir()
        copied = []
        for src in files:
            dst = telemetry_out / src.name
            shutil.copy2(src, dst)
            copied.append(src.name)

        baseline_name = "init" if init_state == "init.state" else "has_pokedex"
        meta = {
            "init_state": init_state,
            "baseline": baseline_name,
            "instance_id": instance_id,
            "seed": SEED,
            "probe_every": PROBE_EVERY,
            "ep1_steps": EP1_STEPS,
            "ep2_steps": EP2_STEPS,
            "telemetry_files": copied,
            "probed_steps": expected_probes,
            "probed_snapshots": [
                {
                    "episode": p["episode"],
                    "global_step": p["global_step"],
                    "snapshot_b64": p["snapshot"].hex(),
                }
                for p in probed_snapshots
            ],
        }
        with open(out_dir / "meta.json", "w") as f:
            json.dump(meta, f, indent=2)
            f.write("\n")

        print(f"  {name}: {len(copied)} files, {len(expected_probes)} probes")
        return out_dir


def main():
    print("Capturing telemetry fixtures...")
    run_scenario("init", "init.state", instance_id="tel_init")
    run_scenario("has_pokedex", "has_pokedex.state", instance_id="tel_dex")
    print("Done.")


if __name__ == "__main__":
    main()
