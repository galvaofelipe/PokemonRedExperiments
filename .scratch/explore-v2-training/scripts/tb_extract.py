#!/usr/bin/env python
"""Extract scalar series from TensorBoard event files under a session dir.

Usage:
  tb_extract.py SESSION_DIR [TAG ...]

Event files are found recursively; scalar series from all of them are
merged (SB3 logger writes poke_ppo_*/; the custom callback writes
histogram/). With no TAG, lists available tags. With TAGs, prints one
line per point: tag<TAB>step<TAB>value
Values in this repo's event files live in v.tensor.float_val, not
simple_value; EventAccumulator handles both.
"""
import sys
from pathlib import Path

from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

GUIDANCE = {"scalars": 0, "tensors": 0, "histograms": 0, "images": 0}


def load_series(sess_dir: str) -> dict:
    root = Path(sess_dir)
    series = {}
    for d in sorted({p.parent for p in root.rglob("*tfevents*")}):
        acc = EventAccumulator(str(d), size_guidance=GUIDANCE)
        acc.Reload()
        for tag in acc.Tags().get("scalars", []):
            series.setdefault(tag, [])
            series[tag].extend((ev.step, ev.value) for ev in acc.Scalars(tag))
    for tag in series:
        series[tag].sort()
    return series


def main() -> None:
    sess = sys.argv[1]
    tags = sys.argv[2:]
    series = load_series(sess)
    if not series:
        print(f"# no scalar tags found under {sess}", file=sys.stderr)
        sys.exit(1)
    if not tags:
        for t in sorted(series):
            print(t)
        return
    for tag in tags:
        if tag not in series:
            print(f"# MISSING {tag}", file=sys.stderr)
            continue
        for step, value in series[tag]:
            print(f"{tag}\t{step}\t{value}")


if __name__ == "__main__":
    main()
