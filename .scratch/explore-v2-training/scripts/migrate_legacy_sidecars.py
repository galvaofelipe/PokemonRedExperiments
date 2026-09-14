#!/usr/bin/env python3
"""One-time migration (ticket 19, item 7): backfill lineage sidecars for the
legacy t05/t15/t16 run dirs on the tower share.

Idempotent: existing sidecars are skipped unless --force. Safe to re-run when
the s1/s2 legs land on the share — their manifest entries are already here.

Facts come from each dir's own run.json (cli_args) plus the resume offsets
recorded in ticket 17 / the handoffs:

- leg1 dirs (t05_*, t15_*): fresh runs — global_step = zip step, parent null.
- t16 s0 legs: resumed from the 1,966,080 checkpoint with
  reset_num_timesteps=True, so zip steps are LEG-LOCAL: global = zip + 1966080.
- t16 s1/s2 legs (once published): trained with the global clock, so zip steps
  are already global; parent is still the t05/t15 checkpoint at 1,966,080.

NOTE: the largest t16 s0 zip is 8,978,432 leg-local (= 10,944,512 global) —
the runs ended at 9,011,200 leg steps with no final save. The t16 lineages
resume from 10,944,512, not 10,977,280.

Usage:
  python3 migrate_legacy_sidecars.py <runs_v2_dir> [--force]   # dry-run by default; --apply to write
"""
import argparse
import json
import sys
from pathlib import Path

OFFSET = 1966080

MANIFEST = {
    # leg1: fresh runs, global = zip step, no parent
    "t05_g2560_s0": {"offset": 0, "parent": None},
    "t05_g20480_s0": {"offset": 0, "parent": None},
    "t15_acc64_s0": {"offset": 0, "parent": None},
    # t16 s0: leg-local zip steps; parent = leg1 @ 1,966,080
    "t16_acc64_s0": {"offset": OFFSET, "parent": {"lineage": "t15_acc64_s0", "step": OFFSET}},
    "t16_g20480_s0": {"offset": OFFSET, "parent": {"lineage": "t05_g20480_s0", "step": OFFSET}},
    "t16_g2560_s0": {"offset": OFFSET, "parent": {"lineage": "t05_g2560_s0", "step": OFFSET}},
    # t16 s1/s2 (pending publish): global zip steps; same parents, own seeds
    "t16_acc64_s1": {"offset": 0, "parent": {"lineage": "t15_acc64_s1", "step": OFFSET}},
    "t16_g20480_s1": {"offset": 0, "parent": {"lineage": "t05_g20480_s1", "step": OFFSET}},
    "t16_g2560_s1": {"offset": 0, "parent": {"lineage": "t05_g2560_s1", "step": OFFSET}},
    "t16_acc64_s2": {"offset": 0, "parent": {"lineage": "t15_acc64_s2", "step": OFFSET}},
    "t16_g20480_s2": {"offset": 0, "parent": {"lineage": "t05_g20480_s2", "step": OFFSET}},
    "t16_g2560_s2": {"offset": 0, "parent": {"lineage": "t05_g2560_s2", "step": OFFSET}},
}

ENV_KEYS = [
    "headless", "save_final_state", "early_stop", "early_stop_survival",
    "action_freq", "init_state", "max_steps", "print_rewards", "save_video",
    "fast_video", "gb_path", "debug", "reward_scale", "explore_weight",
]


def build_sidecar(lineage, zip_step, entry, run_json):
    ca = run_json["cli_args"]
    num_envs = int(ca["num_envs"])
    physical = ca.get("physical_envs") or num_envs
    env_config = {k: ca.get(k) for k in ENV_KEYS}
    env_config["session_path"] = f"runs_{lineage}"
    return {
        "lineage": lineage,
        "global_step": zip_step + entry["offset"],
        "num_envs": num_envs,
        "n_steps": int(ca.get("n_steps") or ca["max_steps"] // 64),
        "accumulation_rounds": num_envs // physical,
        "seed": int(ca.get("seed", 0)),
        "env_config": env_config,
        "parent": entry["parent"],
        "hostname": run_json.get("hostname"),
        "saved_at": run_json.get("end"),
        "backfilled": "2026-09-14 migrate_legacy_sidecars.py (ticket 19 item 7)",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs_v2", type=Path, help="$POKERED_DATA/pokered/runs/v2 (or a copy)")
    ap.add_argument("--force", action="store_true", help="overwrite existing sidecars")
    ap.add_argument("--apply", action="store_true", help="write (default: dry-run)")
    args = ap.parse_args()

    rc = 0
    for lineage, entry in MANIFEST.items():
        d = args.runs_v2 / lineage
        if not d.is_dir():
            print(f"skip {lineage}: {d} not found (not published yet?)")
            continue
        run_json_path = d / "run.json"
        if not run_json_path.is_file():
            print(f"WARN {lineage}: no run.json — cannot derive env_config; skipped")
            rc = 1
            continue
        run_json = json.loads(run_json_path.read_text())
        zips = sorted(d.glob("poke_*_steps.zip"), key=lambda p: int(p.stem.split("_")[1]))
        wrote = skipped = 0
        for z in zips:
            sidecar_path = z.with_suffix(".json")
            if sidecar_path.exists() and not args.force:
                skipped += 1
                continue
            sidecar = build_sidecar(lineage, int(z.stem.split("_")[1]), entry, run_json)
            if args.apply:
                sidecar_path.write_text(json.dumps(sidecar, indent=2) + "\n")
            wrote += 1
        biggest = zips[-1].stem if zips else "none"
        gstep = int(biggest.split("_")[1]) + entry["offset"] if zips else 0
        print(f"{'APPLY' if args.apply else 'DRY '} {lineage}: {wrote} sidecars, {skipped} kept; "
              f"newest {biggest} -> global {gstep}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
