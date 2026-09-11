#!/usr/bin/env python3
"""Capture RAM snapshot fixtures for scorer tests. Expected values from first principles."""

import json
import sys
from pathlib import Path

from pyboy import PyBoy

REPO_ROOT = Path(__file__).resolve().parents[2]
V3_DIR = REPO_ROOT / "v3"
sys.path.insert(0, str(V3_DIR))

from frozen.ram_map import (
    EVENT_BOUGHT_MUSEUM_TICKET,
    EVENT_FLAG_BYTES_OBS,
    NUM_MAPS,
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
    W_POKEDEX_OWNED_START,
    W_POKEDEX_SEEN_START,
)

FIXTURES_DIR = V3_DIR / "tests" / "fixtures"
ROM_PATH = REPO_ROOT / "pokered.gb"

DEX_BYTES = 19
DEX_LAST_BYTE_MASK = 0x7F
MUSEUM_BYTE_OFFSET = EVENT_BOUGHT_MUSEUM_TICKET[0] - W_EVENT_FLAGS_START
MUSEUM_BIT_MASK = ~(1 << EVENT_BOUGHT_MUSEUM_TICKET[1]) & 0xFF

WEIGHT_BADGES = 100
WEIGHT_EVENTS = 1
WEIGHT_DEX_CAUGHT = 2
WEIGHT_DEX_SEEN = 0.5
WEIGHT_UNIQUE_MAPS = 1
WEIGHT_LEVEL_SUM_CAPPED = 0.1


def capture_snapshot(pyboy):
    return bytes(
        pyboy.memory[i]
        for i in range(SNAPSHOT_BASE, SNAPSHOT_END_INCLUSIVE + 1)
    )


def make_pyboy(state_name):
    pyboy = PyBoy(str(ROM_PATH), window="null")
    with open(REPO_ROOT / state_name, "rb") as f:
        pyboy.load_state(f)
    return pyboy


def write_fixture(scenario_dir, snapshots, meta):
    scenario_dir.mkdir(parents=True, exist_ok=True)
    (scenario_dir / "snapshots.bin").write_bytes(b"".join(snapshots))
    with open(scenario_dir / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")
    print(f"  {scenario_dir.name}: score={meta['expected']['score']}")


def popcount_byte(b):
    return (b & 0xFF).bit_count()


def popcount_bytes(data):
    return sum(popcount_byte(b) for b in data)


def dex_popcount_from_snapshot(snapshot):
    owned_off = W_POKEDEX_OWNED_START - SNAPSHOT_BASE
    data = bytearray(snapshot[owned_off : owned_off + DEX_BYTES])
    data[-1] &= DEX_LAST_BYTE_MASK
    return popcount_bytes(data)


def dex_seen_popcount_from_snapshot(snapshot):
    seen_off = W_POKEDEX_SEEN_START - SNAPSHOT_BASE
    data = bytearray(snapshot[seen_off : seen_off + DEX_BYTES])
    data[-1] &= DEX_LAST_BYTE_MASK
    return popcount_bytes(data)


def event_popcount_from_snapshot(snapshot, baseline_event_bits):
    event_off = W_EVENT_FLAGS_START - SNAPSHOT_BASE
    count = 0
    for i in range(EVENT_FLAG_BYTES_OBS):
        cur = snapshot[event_off + i]
        base = baseline_event_bits[i]
        if i == MUSEUM_BYTE_OFFSET:
            cur &= MUSEUM_BIT_MASK
            base &= MUSEUM_BIT_MASK
        diff = cur & (~base & 0xFF)
        count += popcount_byte(diff)
    return count


def badge_popcount_from_snapshot(snapshot):
    off = W_OBTAINED_BADGES - SNAPSHOT_BASE
    return popcount_byte(snapshot[off])


def unique_maps_from_snapshots(snapshots):
    seen = set()
    map_off = W_CUR_MAP - SNAPSHOT_BASE
    for snap in snapshots:
        map_id = snap[map_off]
        if map_id < NUM_MAPS:
            seen.add(map_id)
    return len(seen)


def level_sum_capped_from_snapshot(snapshot):
    party_off = W_PARTY_COUNT - SNAPSHOT_BASE
    level_offs = [a - SNAPSHOT_BASE for a in W_PARTY_MON_LEVEL]
    party_count = min(snapshot[party_off], 6)
    total = sum(snapshot[level_offs[i]] for i in range(party_count))
    return min(total, 100)


def compute_expected(snapshots, baseline_event_bits):
    max_badges = 0
    max_events = 0
    max_dex_caught = 0
    max_dex_seen = 0
    max_level_sum = 0
    maps_seen = set()
    map_off = W_CUR_MAP - SNAPSHOT_BASE

    for snap in snapshots:
        max_badges = max(max_badges, badge_popcount_from_snapshot(snap))
        max_events = max(max_events, event_popcount_from_snapshot(snap, baseline_event_bits))
        max_dex_caught = max(max_dex_caught, dex_popcount_from_snapshot(snap))
        max_dex_seen = max(max_dex_seen, dex_seen_popcount_from_snapshot(snap))
        map_id = snap[map_off]
        if map_id < NUM_MAPS:
            maps_seen.add(map_id)
        max_level_sum = max(max_level_sum, level_sum_capped_from_snapshot(snap))

    components = {
        "badges": max_badges,
        "events": max_events,
        "dex_caught": max_dex_caught,
        "dex_seen": max_dex_seen,
        "unique_maps": len(maps_seen),
        "level_sum_capped": max_level_sum,
    }
    score = (
        WEIGHT_BADGES * components["badges"]
        + WEIGHT_EVENTS * components["events"]
        + WEIGHT_DEX_CAUGHT * components["dex_caught"]
        + WEIGHT_DEX_SEEN * components["dex_seen"]
        + WEIGHT_UNIQUE_MAPS * components["unique_maps"]
        + WEIGHT_LEVEL_SUM_CAPPED * components["level_sum_capped"]
    )
    return score, components


def read_event_flags(pyboy):
    return bytes(
        pyboy.memory[i]
        for i in range(W_EVENT_FLAGS_START, W_EVENT_FLAGS_START + EVENT_FLAG_BYTES_OBS)
    )


def set_event_bit(pyboy, global_bit_index):
    byte_idx = global_bit_index // 8
    bit_pos = global_bit_index % 8
    addr = W_EVENT_FLAGS_START + byte_idx
    if byte_idx == MUSEUM_BYTE_OFFSET and bit_pos == 0:
        raise ValueError("cannot use museum ticket bit")
    pyboy.memory[addr] = pyboy.memory[addr] | (1 << bit_pos)


def set_dex_owned_bit(pyboy, pokemon_id):
    bit_idx = pokemon_id - 1
    byte_idx = bit_idx // 8
    bit_pos = bit_idx % 8
    addr = W_POKEDEX_OWNED_START + byte_idx
    pyboy.memory[addr] = pyboy.memory[addr] | (1 << bit_pos)


def set_dex_seen_bit(pyboy, pokemon_id):
    bit_idx = pokemon_id - 1
    byte_idx = bit_idx // 8
    bit_pos = bit_idx % 8
    addr = W_POKEDEX_SEEN_START + byte_idx
    pyboy.memory[addr] = pyboy.memory[addr] | (1 << bit_pos)


def unused_event_bits(baseline):
    bits = []
    for byte_idx in range(EVENT_FLAG_BYTES_OBS - 1, -1, -1):
        for bit_pos in range(7, -1, -1):
            if byte_idx == MUSEUM_BYTE_OFFSET and bit_pos == 0:
                continue
            if not (baseline[byte_idx] >> bit_pos) & 1:
                bits.append(byte_idx * 8 + bit_pos)
    return bits


def scenario_pokedex_milestone():
    pyboy1 = make_pyboy("init.state")
    snap1 = capture_snapshot(pyboy1)
    baseline = read_event_flags(pyboy1)
    pyboy1.stop(False)

    pyboy2 = make_pyboy("has_pokedex.state")
    snap2 = capture_snapshot(pyboy2)
    pyboy2.stop(False)

    snapshots = [snap1, snap2]
    score, components = compute_expected(snapshots, baseline)
    score1, comp1 = compute_expected([snap1], baseline)

    write_fixture(
        FIXTURES_DIR / "pokedex_milestone",
        snapshots,
        {
            "init_state": "init.state",
            "baseline": "init",
            "n_snapshots": 2,
            "description": "init then has_pokedex milestone",
            "expected": {
                "score": score,
                "components": components,
                "delta_from_first": {
                    "score": score - score1,
                    "components": {k: components[k] - comp1[k] for k in components},
                },
            },
        },
    )


def scenario_badge_milestone():
    pyboy = make_pyboy("init.state")
    baseline = read_event_flags(pyboy)
    snapshots = [capture_snapshot(pyboy)]

    pyboy.memory[W_OBTAINED_BADGES] = 0x01
    snapshots.append(capture_snapshot(pyboy))

    pyboy.memory[W_OBTAINED_BADGES] = 0x03
    snapshots.append(capture_snapshot(pyboy))
    pyboy.stop(False)

    score, components = compute_expected(snapshots, baseline)
    score1, comp1 = compute_expected([snapshots[0]], baseline)

    write_fixture(
        FIXTURES_DIR / "badge_milestone",
        snapshots,
        {
            "init_state": "init.state",
            "baseline": "init",
            "n_snapshots": 3,
            "description": "badge 0x01 then 0x03",
            "expected": {
                "score": score,
                "components": components,
                "delta_from_first": {
                    "score": score - score1,
                    "components": {k: components[k] - comp1[k] for k in components},
                },
                "per_badge_score_delta": 100,
            },
        },
    )


def scenario_museum_ticket_excluded():
    pyboy = make_pyboy("init.state")
    baseline = read_event_flags(pyboy)
    snapshots = [capture_snapshot(pyboy)]

    pyboy.memory[EVENT_BOUGHT_MUSEUM_TICKET[0]] |= 0x01
    snapshots.append(capture_snapshot(pyboy))
    pyboy.stop(False)

    score, components = compute_expected(snapshots, baseline)
    score1, comp1 = compute_expected([snapshots[0]], baseline)

    write_fixture(
        FIXTURES_DIR / "museum_ticket_excluded",
        snapshots,
        {
            "init_state": "init.state",
            "baseline": "init",
            "n_snapshots": 2,
            "description": "museum ticket bit must not count as event",
            "expected": {
                "score": score,
                "components": components,
                "delta_from_first": {
                    "score": score - score1,
                    "components": {k: components[k] - comp1[k] for k in components},
                },
            },
        },
    )


def scenario_money_noop():
    pyboy1 = make_pyboy("has_pokedex.state")
    snap1 = capture_snapshot(pyboy1)
    baseline = read_event_flags(pyboy1)
    flags1 = bytes(baseline)
    pyboy1.stop(False)

    pyboy2 = make_pyboy("has_pokedex_nballs.state")
    snap2 = capture_snapshot(pyboy2)
    flags2 = read_event_flags(pyboy2)
    pyboy2.stop(False)

    warning = None
    for i in range(EVENT_FLAG_BYTES_OBS):
        cur1 = flags1[i]
        cur2 = flags2[i]
        if i == MUSEUM_BYTE_OFFSET:
            cur1 &= MUSEUM_BIT_MASK
            cur2 &= MUSEUM_BIT_MASK
        new_bits = cur2 & (~cur1 & 0xFF)
        if new_bits:
            warning = (
                f"WARNING: has_pokedex_nballs has new event bits in byte {i}: "
                f"0x{new_bits:02x} (expected money-only delta)"
            )
            print(warning)

    snapshots = [snap1, snap2]
    score, components = compute_expected(snapshots, baseline)
    score1, comp1 = compute_expected([snap1], baseline)

    meta = {
        "init_state": "has_pokedex.state",
        "baseline": "has_pokedex",
        "n_snapshots": 2,
        "description": "money change only; score must not move",
        "expected": {
            "score": score,
            "components": components,
            "delta_from_first": {
                "score": score - score1,
                "components": {k: components[k] - comp1[k] for k in components},
            },
        },
    }
    if warning:
        meta["warning"] = warning

    write_fixture(FIXTURES_DIR / "money_noop", snapshots, meta)


def scenario_heal_noop():
    pyboy = make_pyboy("init.state")
    baseline = read_event_flags(pyboy)

    pyboy.memory[W_PARTY_COUNT] = 1
    pyboy.memory[W_PARTY_SPECIES[0]] = 1
    pyboy.memory[W_PARTY_MON_LEVEL[0]] = 20
    pyboy.memory[W_PARTY_MON_MAX_HP[0]] = 50
    pyboy.memory[W_PARTY_MON_MAX_HP[0] + 1] = 0
    pyboy.memory[W_PARTY_MON_HP[0]] = 50
    pyboy.memory[W_PARTY_MON_HP[0] + 1] = 0

    snapshots = []
    for hp in (50, 10, 50):
        pyboy.memory[W_PARTY_MON_HP[0]] = hp
        pyboy.memory[W_PARTY_MON_HP[0] + 1] = 0
        snapshots.append(capture_snapshot(pyboy))
    pyboy.stop(False)

    score, components = compute_expected(snapshots, baseline)
    score1, comp1 = compute_expected([snapshots[0]], baseline)

    write_fixture(
        FIXTURES_DIR / "heal_noop",
        snapshots,
        {
            "init_state": "init.state",
            "baseline": "init",
            "n_snapshots": 3,
            "description": "HP heal/damage only; score must not move",
            "expected": {
                "score": score,
                "components": components,
                "delta_from_first": {
                    "score": score - score1,
                    "components": {k: components[k] - comp1[k] for k in components},
                },
            },
        },
    )


def scenario_map_revisit():
    pyboy = make_pyboy("init.state")
    baseline = read_event_flags(pyboy)
    map_sequence = [0, 12, 12, 12, 1, 1, 0, 0xFF, 12]
    snapshots = []
    for map_id in map_sequence:
        pyboy.memory[W_CUR_MAP] = map_id
        snapshots.append(capture_snapshot(pyboy))
    pyboy.stop(False)

    score, components = compute_expected(snapshots, baseline)

    write_fixture(
        FIXTURES_DIR / "map_revisit",
        snapshots,
        {
            "init_state": "init.state",
            "baseline": "init",
            "n_snapshots": len(snapshots),
            "description": "map revisits add nothing; 0xFF ignored",
            "expected": {
                "score": score,
                "components": components,
                "unique_maps": 3,
            },
        },
    )


def scenario_level_cap():
    pyboy = make_pyboy("init.state")
    baseline = read_event_flags(pyboy)

    pyboy.memory[W_PARTY_COUNT] = 6
    for i in range(6):
        pyboy.memory[W_PARTY_SPECIES[i]] = 1 + i
        pyboy.memory[W_PARTY_MON_LEVEL[i]] = 50

    snap_high = capture_snapshot(pyboy)

    for i in range(6):
        pyboy.memory[W_PARTY_MON_LEVEL[i]] = 5
    snap_low = capture_snapshot(pyboy)
    pyboy.stop(False)

    snapshots = [snap_high, snap_low]
    score, components = compute_expected(snapshots, baseline)

    write_fixture(
        FIXTURES_DIR / "level_cap",
        snapshots,
        {
            "init_state": "init.state",
            "baseline": "init",
            "n_snapshots": 2,
            "description": "level sum capped at 100; running max holds on drop",
            "expected": {
                "score": score,
                "components": components,
                "level_sum_capped": 100,
            },
        },
    )


def scenario_gym_skip_worse():
    pyboy_a = make_pyboy("init.state")
    baseline_a = read_event_flags(pyboy_a)
    pyboy_a.memory[W_OBTAINED_BADGES] = 0x01
    unused_a = unused_event_bits(baseline_a)[:10]
    for bit in unused_a:
        set_event_bit(pyboy_a, bit)
    snapshots_a = [capture_snapshot(pyboy_a)]
    pyboy_a.stop(False)
    score_a, comp_a = compute_expected(snapshots_a, baseline_a)

    pyboy_b = make_pyboy("init.state")
    baseline_b = read_event_flags(pyboy_b)
    unused_b = unused_event_bits(baseline_b)[:60]
    for bit in unused_b:
        set_event_bit(pyboy_b, bit)
    for pid in range(1, 9):
        set_dex_owned_bit(pyboy_b, pid)
    for pid in range(1, 5):
        set_dex_seen_bit(pyboy_b, pid)
    pyboy_b.memory[W_PARTY_COUNT] = 6
    for i in range(6):
        pyboy_b.memory[W_PARTY_MON_LEVEL[i]] = 50
    map_ids = [0, 12, 1, 13, 51]
    snapshots_b = []
    for map_id in map_ids:
        pyboy_b.memory[W_CUR_MAP] = map_id
        snapshots_b.append(capture_snapshot(pyboy_b))
    pyboy_b.stop(False)
    score_b, comp_b = compute_expected(snapshots_b, baseline_b)

    assert score_a > score_b, (
        f"takes_gym ({score_a}) must beat skips_gym ({score_b})"
    )

    write_fixture(
        FIXTURES_DIR / "gym_skip_worse" / "takes_gym",
        snapshots_a,
        {
            "init_state": "init.state",
            "baseline": "init",
            "n_snapshots": 1,
            "description": "badge + 10 events",
            "expected": {"score": score_a, "components": comp_a},
        },
    )
    write_fixture(
        FIXTURES_DIR / "gym_skip_worse" / "skips_gym",
        snapshots_b,
        {
            "init_state": "init.state",
            "baseline": "init",
            "n_snapshots": len(snapshots_b),
            "description": "60 events + dex + maps + level cap, no badge",
            "expected": {"score": score_b, "components": comp_b},
        },
    )
    print(f"  gym_skip_worse: takes_gym={score_a} > skips_gym={score_b}")


def main():
    print("Capturing scorer fixtures...")
    scenario_pokedex_milestone()
    scenario_badge_milestone()
    scenario_museum_ticket_excluded()
    scenario_money_noop()
    scenario_heal_noop()
    scenario_map_revisit()
    scenario_level_cap()
    scenario_gym_skip_worse()
    print("Done.")


if __name__ == "__main__":
    main()
