"""Split extraction from per-step telemetry snapshots."""

from pathlib import Path

from frozen.ram_map import (
    SNAPSHOT_BASE,
    W_CUR_MAP,
    W_PLAY_TIME_FRAMES,
    W_PLAY_TIME_HOURS,
    W_PLAY_TIME_MAXED,
    W_PLAY_TIME_MINUTES,
    W_PLAY_TIME_SECONDS,
)
from frozen.splits.data import SPLITS_VERSION, load_splits
from frozen.telemetry import iter_episode_records

MT_MOON_MAP_ID = 15

_CLOCK_HOURS_OFF = W_PLAY_TIME_HOURS - SNAPSHOT_BASE
_CLOCK_MAXED_OFF = W_PLAY_TIME_MAXED - SNAPSHOT_BASE
_CLOCK_MINUTES_OFF = W_PLAY_TIME_MINUTES - SNAPSHOT_BASE
_CLOCK_SECONDS_OFF = W_PLAY_TIME_SECONDS - SNAPSHOT_BASE
_CLOCK_FRAMES_OFF = W_PLAY_TIME_FRAMES - SNAPSHOT_BASE
_CUR_MAP_OFF = W_CUR_MAP - SNAPSHOT_BASE


def snapshot_offset(wram_addr):
    return wram_addr - SNAPSHOT_BASE


def _parse_addr(addr):
    if isinstance(addr, str):
        return int(addr, 16)
    return addr


def read_bit(snapshot, wram_addr, bit):
    off = snapshot_offset(wram_addr)
    return bool(snapshot[off] & (1 << bit))


def frames_to_game_time(total_frames):
    frames = total_frames % 60
    total_seconds = total_frames // 60
    seconds = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60
    return hours, minutes, seconds, frames


def format_game_time(hours, minutes, seconds):
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def read_play_clock(snapshot):
    hours = snapshot[_CLOCK_HOURS_OFF]
    clock_maxed = bool(snapshot[_CLOCK_MAXED_OFF])
    minutes = snapshot[_CLOCK_MINUTES_OFF]
    seconds = snapshot[_CLOCK_SECONDS_OFF]
    frames = snapshot[_CLOCK_FRAMES_OFF]
    game_time_frames = ((hours * 60 + minutes) * 60 + seconds) * 60 + frames
    return {
        "hours": hours,
        "minutes": minutes,
        "seconds": seconds,
        "frames": frames,
        "clock_maxed": clock_maxed,
        "game_time_frames": game_time_frames,
        "game_time": format_game_time(hours, minutes, seconds),
    }


def _split_order_and_defs(data=None):
    if data is None:
        data = load_splits()
    order = [s["split_name"] for s in data["splits"]]
    return order, data["splits"]


def _update_sticky(sticky, split_def, snapshot):
    if split_def["condition_type"] != "combo":
        return
    addr = _parse_addr(split_def["addresses"][0])
    bit = split_def["bits"][0]
    if read_bit(snapshot, addr, bit):
        sticky[split_def["split_name"]] = True


def _condition_met(split_def, snapshot, sticky):
    ctype = split_def["condition_type"]
    if ctype in ("badge_bit", "event_bit"):
        addr = _parse_addr(split_def["addresses"][0])
        bit = split_def["bits"][0]
        return read_bit(snapshot, addr, bit)
    if ctype == "combo":
        name = split_def["split_name"]
        if sticky.get(name):
            return snapshot[_CUR_MAP_OFF] == MT_MOON_MAP_ID
        return False
    raise ValueError(f"unknown condition_type: {ctype}")


def _make_hit_record(name, step, clock, initial):
    return {
        "name": name,
        "first_hit_step": step,
        "game_time": clock["game_time"],
        "game_time_frames": clock["game_time_frames"],
        "clock_maxed": clock["clock_maxed"],
        "segment_time": None,
        "segment_time_frames": None,
        "initial": initial,
    }


def _apply_segment_times(achieved_by_name, order, start_frames):
    achieved = [
        (route_idx, name, achieved_by_name[name])
        for route_idx, name in enumerate(order)
        if name in achieved_by_name
    ]
    completion_order = sorted(
        achieved,
        key=lambda item: (
            item[2]["game_time_frames"],
            item[2]["first_hit_step"],
            item[0],
        ),
    )
    prev_frames = start_frames
    for _route_idx, _name, entry in completion_order:
        seg_frames = entry["game_time_frames"] - prev_frames
        h, m, s, f = frames_to_game_time(seg_frames)
        entry["segment_time"] = format_game_time(h, m, s)
        entry["segment_time_frames"] = seg_frames
        prev_frames = entry["game_time_frames"]


def extract_episode_splits(records, order=None, definitions=None):
    if order is None or definitions is None:
        order, definitions = _split_order_and_defs()

    steps = [r for r in records if "snapshot" in r]
    if not steps:
        return []

    sticky = {}
    achieved_by_name = {}
    start_frames = read_play_clock(steps[0]["snapshot"])["game_time_frames"]

    for split_def in definitions:
        name = split_def["split_name"]
        _update_sticky(sticky, split_def, steps[0]["snapshot"])
        if _condition_met(split_def, steps[0]["snapshot"], sticky):
            clock = read_play_clock(steps[0]["snapshot"])
            achieved_by_name[name] = _make_hit_record(
                name, steps[0]["step"], clock, True
            )

    for rec in steps[1:]:
        snapshot = rec["snapshot"]
        for split_def in definitions:
            name = split_def["split_name"]
            if name in achieved_by_name:
                continue
            _update_sticky(sticky, split_def, snapshot)
            if _condition_met(split_def, snapshot, sticky):
                clock = read_play_clock(snapshot)
                achieved_by_name[name] = _make_hit_record(
                    name, rec["step"], clock, False
                )

    _apply_segment_times(achieved_by_name, order, start_frames)
    return [achieved_by_name[name] for name in order if name in achieved_by_name]


def episode_id_from_telemetry(path):
    name = Path(path).name
    if name.endswith(".telemetry.gz"):
        return name[: -len(".telemetry.gz")]
    return Path(path).stem


def extract_splits_from_telemetry(path):
    records = []
    for item in iter_episode_records(path):
        if "_metadata" not in item:
            records.append(item)
    return extract_episode_splits(records)


def aggregate_splits_section(per_episode):
    order, _ = _split_order_and_defs()
    best = {}
    for episode_id, achieved in per_episode:
        for entry in achieved:
            name = entry["name"]
            candidate = dict(entry)
            candidate["episode"] = episode_id
            if name not in best:
                best[name] = candidate
                continue
            prev = best[name]
            if candidate["game_time_frames"] < prev["game_time_frames"]:
                best[name] = candidate
            elif (
                candidate["game_time_frames"] == prev["game_time_frames"]
                and candidate["first_hit_step"] < prev["first_hit_step"]
            ):
                best[name] = candidate

    achieved_list = [best[name] for name in order if name in best]
    return {
        "splits_version": SPLITS_VERSION,
        "order": list(order),
        "achieved": achieved_list,
    }


def format_splits_table(order, achieved_by_name):
    lines = []
    lines.append(f"{'Split':<28} {'Step':>6}  {'Game Time':>10}  {'Segment':>10}")
    lines.append("-" * 60)
    for name in order:
        if name in achieved_by_name:
            e = achieved_by_name[name]
            lines.append(
                f"{name:<28} {e['first_hit_step']:>6}  "
                f"{e['game_time']:>10}  {e['segment_time']:>10}"
            )
        else:
            lines.append(f"{name:<28} {'-':>6}  {'-':>10}  {'-':>10}")
    return "\n".join(lines)
