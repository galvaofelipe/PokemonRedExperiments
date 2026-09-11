from dataclasses import dataclass

from frozen.ram_map import (
    EVENT_BOUGHT_MUSEUM_TICKET,
    EVENT_FLAG_BYTES_OBS,
    NUM_MAPS,
    SNAPSHOT_BASE,
    SNAPSHOT_SIZE,
    W_CUR_MAP,
    W_EVENT_FLAGS_START,
    W_OBTAINED_BADGES,
    W_PARTY_COUNT,
    W_PARTY_MON_LEVEL,
    W_POKEDEX_OWNED_START,
    W_POKEDEX_SEEN_START,
)

SCORE_VERSION = "1.0.0"

WEIGHT_BADGES = 100
WEIGHT_EVENTS = 1
WEIGHT_DEX_CAUGHT = 2
WEIGHT_DEX_SEEN = 0.5
WEIGHT_UNIQUE_MAPS = 1
WEIGHT_LEVEL_SUM_CAPPED = 0.1

DEX_BYTES = W_POKEDEX_SEEN_START - W_POKEDEX_OWNED_START  # 19
DEX_LAST_BYTE_MASK = 0x7F  # bit 151 unused

EVENT_OFFSET = W_EVENT_FLAGS_START - SNAPSHOT_BASE
MUSEUM_BYTE_OFFSET = EVENT_BOUGHT_MUSEUM_TICKET[0] - W_EVENT_FLAGS_START
MUSEUM_BIT_MASK = ~(1 << EVENT_BOUGHT_MUSEUM_TICKET[1]) & 0xFF

BADGES_OFFSET = W_OBTAINED_BADGES - SNAPSHOT_BASE
CUR_MAP_OFFSET = W_CUR_MAP - SNAPSHOT_BASE
PARTY_COUNT_OFFSET = W_PARTY_COUNT - SNAPSHOT_BASE
LEVEL_OFFSETS = tuple(addr - SNAPSHOT_BASE for addr in W_PARTY_MON_LEVEL)
OWNED_OFFSET = W_POKEDEX_OWNED_START - SNAPSHOT_BASE
SEEN_OFFSET = W_POKEDEX_SEEN_START - SNAPSHOT_BASE


def _popcount_byte(b):
    return (b & 0xFF).bit_count()


def _popcount_bytes(data):
    return sum(_popcount_byte(b) for b in data)


def _mask_museum_byte(b):
    return b & MUSEUM_BIT_MASK


def _dex_popcount(snapshot, offset):
    data = snapshot[offset : offset + DEX_BYTES]
    masked = bytearray(data)
    masked[-1] &= DEX_LAST_BYTE_MASK
    return _popcount_bytes(masked)


def _event_popcount(snapshot, baseline_event_bits):
    count = 0
    for i in range(EVENT_FLAG_BYTES_OBS):
        cur = snapshot[EVENT_OFFSET + i]
        base = baseline_event_bits[i]
        if i == MUSEUM_BYTE_OFFSET:
            cur = _mask_museum_byte(cur)
            base = _mask_museum_byte(base)
        diff = cur & (~base & 0xFF)
        count += _popcount_byte(diff)
    return count


def _badge_popcount(snapshot):
    return _popcount_byte(snapshot[BADGES_OFFSET])


def _unique_maps_update(seen, snapshot):
    map_id = snapshot[CUR_MAP_OFFSET]
    if map_id < NUM_MAPS:
        seen.add(map_id)
    return len(seen)


def _level_sum_capped(snapshot):
    party_count = min(snapshot[PARTY_COUNT_OFFSET], 6)
    total = sum(snapshot[LEVEL_OFFSETS[i]] for i in range(party_count))
    return min(total, 100)


def _validate_snapshot(snapshot):
    if len(snapshot) != SNAPSHOT_SIZE:
        raise ValueError(
            f"snapshot must be {SNAPSHOT_SIZE} bytes, got {len(snapshot)}"
        )


def _validate_baseline(baseline_event_bits):
    if len(baseline_event_bits) != EVENT_FLAG_BYTES_OBS:
        raise ValueError(
            f"baseline_event_bits must be {EVENT_FLAG_BYTES_OBS} bytes, "
            f"got {len(baseline_event_bits)}"
        )


@dataclass(frozen=True)
class ScoreResult:
    score: float
    score_version: str
    components: dict

    def to_dict(self):
        return {
            "score": self.score,
            "score_version": self.score_version,
            "components": dict(self.components),
        }


def _compute_weighted_score(components):
    return (
        WEIGHT_BADGES * components["badges"]
        + WEIGHT_EVENTS * components["events"]
        + WEIGHT_DEX_CAUGHT * components["dex_caught"]
        + WEIGHT_DEX_SEEN * components["dex_seen"]
        + WEIGHT_UNIQUE_MAPS * components["unique_maps"]
        + WEIGHT_LEVEL_SUM_CAPPED * components["level_sum_capped"]
    )


def score_snapshots(snapshots, baseline_event_bits):
    _validate_baseline(baseline_event_bits)

    max_badges = 0
    max_events = 0
    max_dex_caught = 0
    max_dex_seen = 0
    max_unique_maps = 0
    max_level_sum = 0
    maps_seen = set()

    for snapshot in snapshots:
        snap = bytes(snapshot)
        _validate_snapshot(snap)

        max_badges = max(max_badges, _badge_popcount(snap))
        max_events = max(max_events, _event_popcount(snap, baseline_event_bits))
        max_dex_caught = max(max_dex_caught, _dex_popcount(snap, OWNED_OFFSET))
        max_dex_seen = max(max_dex_seen, _dex_popcount(snap, SEEN_OFFSET))
        max_unique_maps = max(
            max_unique_maps, _unique_maps_update(maps_seen, snap)
        )
        max_level_sum = max(max_level_sum, _level_sum_capped(snap))

    components = {
        "badges": max_badges,
        "events": max_events,
        "dex_caught": max_dex_caught,
        "dex_seen": max_dex_seen,
        "unique_maps": max_unique_maps,
        "level_sum_capped": max_level_sum,
    }
    score = _compute_weighted_score(components)
    return ScoreResult(score=score, score_version=SCORE_VERSION, components=components)
