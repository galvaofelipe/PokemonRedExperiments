#!/usr/bin/env python3
"""Capture event-flag baselines from save states for the Frozen scorer."""

import hashlib
import json
import sys
from pathlib import Path

from pyboy import PyBoy

REPO_ROOT = Path(__file__).resolve().parents[2]
V3_DIR = REPO_ROOT / "v3"
sys.path.insert(0, str(V3_DIR))

from frozen.ram_map import (
    EVENT_FLAG_BYTES_OBS,
    W_EVENT_FLAGS_END_INCLUSIVE,
    W_EVENT_FLAGS_START,
)

STATES = [
    "init.state",
    "fast_text_start.state",
    "has_pokedex.state",
    "has_pokedex_nballs.state",
]

BASELINES_DIR = V3_DIR / "frozen" / "scorer" / "baselines"
ROM_PATH = REPO_ROOT / "pokered.gb"


def read_event_flags(pyboy):
    return bytes(
        pyboy.memory[i]
        for i in range(W_EVENT_FLAGS_START, W_EVENT_FLAGS_END_INCLUSIVE + 1)
    )


def popcount_event_flags(data):
    return sum(b.bit_count() for b in data)


def main():
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {}

    for state_name in STATES:
        state_path = REPO_ROOT / state_name
        stem = state_path.stem
        out_path = BASELINES_DIR / f"{stem}.bin"

        pyboy = PyBoy(str(ROM_PATH), window="null")
        with open(state_path, "rb") as f:
            pyboy.load_state(f)
        flags = read_event_flags(pyboy)
        pyboy.stop(False)

        assert len(flags) == EVENT_FLAG_BYTES_OBS
        out_path.write_bytes(flags)
        digest = hashlib.sha256(flags).hexdigest()
        manifest[stem] = {"file": f"{stem}.bin", "sha256": digest}
        print(f"{stem}: popcount={popcount_event_flags(flags)} sha256={digest[:16]}...")

    manifest_path = BASELINES_DIR / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"Wrote {manifest_path}")


if __name__ == "__main__":
    main()
