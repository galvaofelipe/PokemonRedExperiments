#!/usr/bin/env python
"""Stitch TensorBoard event files from a resumed SB3 run onto the original leg.

SB3 resume with reset_num_timesteps=True logs the continued run from step 0
(often first scalar at n_steps) while tensorboard_log may still point at the
original run directory. This script builds a merged destination logdir:
  1) TFRecords from the first leg copied verbatim (preserves on-disk encoding)
  2) events from the resumed leg with step offset, scalar floats re-encoded as
     simple_value so TensorBoard keeps a single continuous scalar series

Sources are read-only; the destination is removed and rewritten each run.

Usage (from v2/):
  ../.venv/bin/python ../.scratch/explore-v2-training/scripts/tb_stitch.py \\
    runs_t15_acc64_s0/poke_ppo_1 \\
    runs_t15_acc64_s0/poke_ppo_2 \\
    1966080 \\
    runs_t16_acc64_s0/poke_ppo_1
"""
import argparse
import hashlib
import shutil
import struct
import sys
import time
import socket
import os
from pathlib import Path

from tensorboard.backend.event_processing import event_file_loader
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
from tensorboard.compat.proto import event_pb2, summary_pb2
from tensorboard.summary.writer.record_writer import RecordWriter

GUIDANCE = {"scalars": 0, "tensors": 0, "histograms": 0, "images": 0}


def _event_files(logdir: Path) -> list[Path]:
    files = sorted(logdir.glob("events.out.tfevents.*"))
    if not files:
        raise FileNotFoundError(f"no event files under {logdir}")
    return files


def _read_tfrecords(path: Path) -> list[bytes]:
    records: list[bytes] = []
    with path.open("rb") as fh:
        while True:
            header = fh.read(8)
            if len(header) < 8:
                break
            length = struct.unpack("<Q", header)[0]
            fh.read(4)
            records.append(fh.read(length))
            fh.read(4)
    return records


def _compact_scalar_value(val: summary_pb2.Summary.Value) -> summary_pb2.Summary.Value:
    kind = val.WhichOneof("value")
    if (
        kind == "tensor"
        and val.tensor.dtype == 1  # DT_FLOAT
        and len(val.tensor.float_val) == 1
        and not val.tensor.tensor_shape.dim
    ):
        out = summary_pb2.Summary.Value()
        out.tag = val.tag
        out.simple_value = val.tensor.float_val[0]
        return out
    out = summary_pb2.Summary.Value()
    out.CopyFrom(val)
    return out


def _offset_resumed_event(ev: event_pb2.Event, offset: int) -> event_pb2.Event:
    out = event_pb2.Event()
    out.CopyFrom(ev)
    out.step = ev.step + offset
    if out.summary:
        summary = summary_pb2.Summary()
        for val in ev.summary.value:
            summary.value.append(_compact_scalar_value(val))
        out.summary.CopyFrom(summary)
    return out


def _write_merged(dest: Path, first_leg: Path, resumed_leg: Path, offset: int) -> int:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    out_name = dest / (
        "events.out.tfevents.%010d.%s.%s.0"
        % (time.time(), socket.gethostname(), os.getpid())
    )
    writer = RecordWriter(out_name.open("wb"))
    writer.write(
        event_pb2.Event(
            wall_time=time.time(),
            file_version="brain.Event:2",
        ).SerializeToString()
    )

    copied = 0
    for path in _event_files(first_leg):
        for record in _read_tfrecords(path):
            ev = event_pb2.Event.FromString(record)
            if ev.WhichOneof("what") == "file_version":
                continue
            # The first leg may overshoot the resume checkpoint (e.g. SB3 stops
            # only at an update boundary). Those steps were discarded by the
            # resume; keeping them would duplicate steps against shifted leg2.
            if ev.step > offset:
                continue
            writer.write(record)
            copied += 1

    appended = 0
    for path in _event_files(resumed_leg):
        for ev in event_file_loader.EventFileLoader(str(path)).Load():
            if ev.WhichOneof("what") == "file_version":
                continue
            writer.write(_offset_resumed_event(ev, offset).SerializeToString())
            appended += 1

    writer.close()
    return copied + appended


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_checksums(*dirs: Path) -> dict[str, str]:
    sums: dict[str, str] = {}
    for d in dirs:
        for path in sorted(_event_files(d)):
            sums[str(path.resolve())] = _sha256(path)
    return sums


def _load_scalar_series(logdir: Path) -> dict[str, list[tuple[int, float]]]:
    acc = EventAccumulator(str(logdir), size_guidance=GUIDANCE)
    acc.Reload()
    series: dict[str, list[tuple[int, float]]] = {}
    for tag in acc.Tags().get("scalars", []):
        series[tag] = [(ev.step, ev.value) for ev in acc.Scalars(tag)]
    return series


def _step_extrema(logdir: Path) -> tuple[int | None, int | None]:
    acc = EventAccumulator(str(logdir), size_guidance=GUIDANCE)
    acc.Reload()
    mins: list[int] = []
    maxs: list[int] = []
    for kind in ("scalars", "images", "histograms", "tensors"):
        for tag in acc.Tags().get(kind, []):
            if kind == "scalars":
                evs = acc.Scalars(tag)
            elif kind == "images":
                evs = acc.Images(tag)
            elif kind == "histograms":
                evs = acc.Histograms(tag)
            else:
                evs = acc.Tensors(tag)
            if evs:
                mins.append(evs[0].step)
                maxs.append(evs[-1].step)
    if not mins:
        return None, None
    return min(mins), max(maxs)


def _tag_buckets(logdir: Path) -> dict[str, set[str]]:
    acc = EventAccumulator(str(logdir), size_guidance=GUIDANCE)
    acc.Reload()
    buckets: dict[str, set[str]] = {}
    for kind in ("scalars", "tensors", "images", "histograms"):
        for tag in acc.Tags().get(kind, []):
            buckets.setdefault(tag, set()).add(kind)
    return buckets


def _validate_merged(
    dest: Path,
    first_leg: Path,
    resumed_leg: Path,
    offset: int,
) -> None:
    _, resumed_max = _step_extrema(resumed_leg)
    merged_min, merged_max = _step_extrema(dest)
    if merged_max is None or resumed_max is None:
        raise RuntimeError("merged or resumed leg has no stepped events")

    expected_max = resumed_max + offset
    if merged_max != expected_max:
        raise RuntimeError(
            f"merged max step {merged_max} != resumed_max+offset ({expected_max})"
        )

    first = _load_scalar_series(first_leg)
    resumed = _load_scalar_series(resumed_leg)
    merged = _load_scalar_series(dest)

    missing = (set(first) | set(resumed)) - set(merged)
    if missing:
        raise RuntimeError(f"merged log missing scalar tags: {sorted(missing)}")

    for tag in sorted(merged):
        steps = [s for s, _ in merged[tag]]
        if len(steps) != len(set(steps)):
            dupes = sorted({s for s in steps if steps.count(s) > 1})
            raise RuntimeError(f"duplicate steps for {tag}: {dupes[:5]}")

        want = [(s, v) for s, v in first.get(tag, []) if s <= offset]
        want.extend((s + offset, v) for s, v in resumed.get(tag, []))
        want.sort(key=lambda x: (x[0], x[1]))
        got = sorted(merged[tag], key=lambda x: (x[0], x[1]))
        if want != got:
            raise RuntimeError(
                f"scalar mismatch for {tag}: want {len(want)} pts, got {len(got)}"
            )

    if merged_min != 0 and merged_min != min(
        s for pts in first.values() for s, _ in pts
    ):
        print(f"note: merged min step is {merged_min}", file=sys.stderr)


def _report_tags(first_leg: Path, resumed_leg: Path, dest: Path) -> None:
    first_b = _tag_buckets(first_leg)
    resumed_b = _tag_buckets(resumed_leg)
    dest_b = _tag_buckets(dest)
    all_tags = sorted(set(first_b) | set(resumed_b))
    print("# tags (EventAccumulator buckets: leg1 / leg2 / dest):")
    for tag in all_tags:
        print(
            f"#   {tag}\t"
            f"leg1={','.join(sorted(first_b.get(tag, ('-',))))}\t"
            f"leg2={','.join(sorted(resumed_b.get(tag, ('-',))))}\t"
            f"dest={','.join(sorted(dest_b.get(tag, ('-',))))}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first_leg", type=Path, help="original run logdir (e.g. poke_ppo_1)")
    parser.add_argument("resumed_leg", type=Path, help="resumed run logdir (e.g. poke_ppo_2)")
    parser.add_argument("offset", type=int, help="steps already trained before resume")
    parser.add_argument("dest", type=Path, help="output logdir (rewritten each run)")
    args = parser.parse_args()

    for d in (args.first_leg, args.resumed_leg):
        if not d.is_dir():
            parser.error(f"not a directory: {d}")

    before = _source_checksums(args.first_leg, args.resumed_leg)
    total_events = _write_merged(args.dest, args.first_leg, args.resumed_leg, args.offset)
    after = _source_checksums(args.first_leg, args.resumed_leg)
    if before != after:
        raise RuntimeError("source event file checksums changed during stitch")

    _validate_merged(args.dest, args.first_leg, args.resumed_leg, args.offset)

    _, resumed_max = _step_extrema(args.resumed_leg)
    merged_min, merged_max = _step_extrema(args.dest)

    _report_tags(args.first_leg, args.resumed_leg, args.dest)
    print(f"# wrote {args.dest} ({total_events} content events)")
    print(f"# steps: min={merged_min} max={merged_max} (resumed_max+offset={resumed_max + args.offset})")
    print("# wall_time: preserved from source Event protos (not rescaled)")
    print("# histograms: none in these runs")
    print(
        "# images: leg1 bytes copied (images bucket); leg2 re-serialized "
        "(may land in tensors bucket but keep images plugin metadata)"
    )


if __name__ == "__main__":
    main()
