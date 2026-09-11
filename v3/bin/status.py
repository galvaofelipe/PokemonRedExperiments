#!/usr/bin/env python3
"""CLI reader for v3 runner job status (Human-owned / host-side)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

V3_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = Path(__file__).resolve().parent / "runner_config.json"


def load_queue_dirs(config_path: Path) -> dict[str, Path]:
    data = json.loads(config_path.read_text())
    queue = data["queue"]
    return {
        "queued": V3_ROOT / queue["queued_dir"],
        "running": V3_ROOT / queue["running_dir"],
        "done": V3_ROOT / queue["done_dir"],
        "failed": V3_ROOT / queue["failed_dir"],
    }


def count_jobs(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return len(list(directory.glob("*.json")))


def load_running_statuses(running_dir: Path) -> list[dict]:
    rows = []
    for path in sorted(running_dir.glob("*.status.json")):
        try:
            rows.append(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError):
            rows.append({"job_name": path.stem.replace(".status", ""), "state": "unknown"})
    return rows


def format_row(row: dict) -> str:
    name = row.get("job_name", "?")
    state = row.get("state", "?")
    planned = row.get("planned_timesteps")
    actual = row.get("actual_timesteps")
    eta = row.get("eta_s")
    elapsed = row.get("elapsed_s")
    sps = row.get("observed_sps")
    steps = f"{actual}/{planned}" if planned is not None else str(actual)
    eta_s = f"{eta:.0f}s" if isinstance(eta, (int, float)) else "—"
    elapsed_s = f"{elapsed:.0f}s" if isinstance(elapsed, (int, float)) else "—"
    sps_s = f"{sps:.0f}" if isinstance(sps, (int, float)) else "—"
    return f"{name:20} {state:12} steps={steps:>12} elapsed={elapsed_s:>8} eta={eta_s:>8} sps={sps_s:>6}"


def render_table(dirs: dict[str, Path], show_all: bool) -> str:
    lines = []
    if show_all:
        lines.append(
            f"queued={count_jobs(dirs['queued'])}  "
            f"running={count_jobs(dirs['running'])}  "
            f"done={count_jobs(dirs['done'])}  "
            f"failed={count_jobs(dirs['failed'])}"
        )
    rows = load_running_statuses(dirs["running"])
    if not rows:
        lines.append("no running jobs")
    else:
        lines.append(f"{'job':20} {'state':12} {'progress':26} {'elapsed':14} {'eta':10} {'sps':8}")
        for row in rows:
            lines.append(format_row(row))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Read v3 runner status files.")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--json", action="store_true", help="Emit JSON")
    p.add_argument("--all", action="store_true", help="Include queue directory counts")
    p.add_argument("--watch", type=float, metavar="SECONDS", help="Refresh every N seconds")
    args = p.parse_args(argv)

    dirs = load_queue_dirs(args.config)

    def once() -> int:
        rows = load_running_statuses(dirs["running"])
        if args.json:
            payload = {
                "counts": {k: count_jobs(d) for k, d in dirs.items()},
                "running": rows,
            }
            print(json.dumps(payload, indent=2))
        else:
            print(render_table(dirs, show_all=args.all))
        return 0

    if args.watch:
        while True:
            if not args.json:
                print("\033[H\033[J", end="")
            once()
            time.sleep(args.watch)
    return once()


if __name__ == "__main__":
    raise SystemExit(main())
