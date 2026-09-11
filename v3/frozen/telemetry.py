"""Per-step RAM telemetry for v3 training runs.

Records a canonical 2275-byte snapshot window plus decoded CSV fields per env step.
Files live under ``<session_path>/telemetry/`` as chunked gzip streams.

Set ``V3_TELEMETRY_OFF=1`` once at process start to disable recording entirely
(human benchmarking only — not an env config knob).
"""

import gzip
import json
import os
import struct
from pathlib import Path

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

TELEMETRY_MAGIC = b"V3TEL1"
SCHEMA_VERSION = "1.0.0"
FLUSH_INTERVAL = 512

TAG_HEADER = 0x00
TAG_DECODED = 0x01
TAG_SNAPSHOT = 0x02

DEX_BYTES = W_POKEDEX_SEEN_START - W_POKEDEX_OWNED_START
DEX_LAST_BYTE_MASK = 0x7F

PARTY_COUNT_OFFSET = W_PARTY_COUNT - SNAPSHOT_BASE
BADGES_OFFSET = W_OBTAINED_BADGES - SNAPSHOT_BASE
CUR_MAP_OFFSET = W_CUR_MAP - SNAPSHOT_BASE
Y_COORD_OFFSET = W_Y_COORD - SNAPSHOT_BASE
X_COORD_OFFSET = W_X_COORD - SNAPSHOT_BASE
EVENT_OFFSET = W_EVENT_FLAGS_START - SNAPSHOT_BASE
OWNED_OFFSET = W_POKEDEX_OWNED_START - SNAPSHOT_BASE
SEEN_OFFSET = W_POKEDEX_SEEN_START - SNAPSHOT_BASE
LEVEL_OFFSETS = tuple(addr - SNAPSHOT_BASE for addr in W_PARTY_MON_LEVEL)
SPECIES_OFFSETS = tuple(addr - SNAPSHOT_BASE for addr in W_PARTY_SPECIES)
HP_OFFSETS = tuple(addr - SNAPSHOT_BASE for addr in W_PARTY_MON_HP)
MAX_HP_OFFSETS = tuple(addr - SNAPSHOT_BASE for addr in W_PARTY_MON_MAX_HP)
CLOCK_HOURS_OFFSET = W_PLAY_TIME_HOURS - SNAPSHOT_BASE
CLOCK_MAXED_OFFSET = W_PLAY_TIME_MAXED - SNAPSHOT_BASE
CLOCK_MINUTES_OFFSET = W_PLAY_TIME_MINUTES - SNAPSHOT_BASE
CLOCK_SECONDS_OFFSET = W_PLAY_TIME_SECONDS - SNAPSHOT_BASE
CLOCK_FRAMES_OFFSET = W_PLAY_TIME_FRAMES - SNAPSHOT_BASE

CSV_COLUMNS = [
    "step",
    "x",
    "y",
    "map",
    "badges",
    "event_count",
    "dex_seen",
    "dex_caught",
    "level_sum",
    "clock_hours",
    "clock_maxed",
    "clock_minutes",
    "clock_seconds",
    "clock_frames",
    "last_action",
    "pcount",
    "hp_frac",
] + [f"level_{i}" for i in range(6)] + [f"ptype_{i}" for i in range(6)]


def _read_hp_pair(snapshot, offset):
    return 256 * snapshot[offset] + snapshot[offset + 1]


def _hp_fraction(snapshot):
    hp_sum = sum(_read_hp_pair(snapshot, off) for off in HP_OFFSETS)
    max_hp_sum = sum(_read_hp_pair(snapshot, off) for off in MAX_HP_OFFSETS)
    return hp_sum / max(max_hp_sum, 1)


def _dex_popcount(snapshot, offset):
    data = bytearray(snapshot[offset : offset + DEX_BYTES])
    data[-1] &= DEX_LAST_BYTE_MASK
    return int.from_bytes(data, "little").bit_count()


def decode_snapshot_to_csv_row(step, action, snapshot):
    snap = snapshot
    party_count = snap[PARTY_COUNT_OFFSET]
    badges = snap[BADGES_OFFSET].bit_count()
    event_count = int.from_bytes(
        snap[EVENT_OFFSET : EVENT_OFFSET + EVENT_FLAG_BYTES_OBS], "little"
    ).bit_count()
    dex_caught = _dex_popcount(snap, OWNED_OFFSET)
    dex_seen = _dex_popcount(snap, SEEN_OFFSET)
    levels = [snap[LEVEL_OFFSETS[i]] for i in range(6)]
    species = [snap[SPECIES_OFFSETS[i]] for i in range(6)]
    level_sum = sum(levels[i] for i in range(party_count))
    hp_frac = _hp_fraction(snap)

    values = [
        step,
        snap[X_COORD_OFFSET],
        snap[Y_COORD_OFFSET],
        snap[CUR_MAP_OFFSET],
        badges,
        event_count,
        dex_seen,
        dex_caught,
        level_sum,
        snap[CLOCK_HOURS_OFFSET],
        snap[CLOCK_MAXED_OFFSET],
        snap[CLOCK_MINUTES_OFFSET],
        snap[CLOCK_SECONDS_OFFSET],
        snap[CLOCK_FRAMES_OFFSET],
        action,
        party_count,
        f"{hp_frac:.6f}",
    ] + levels + species
    return ",".join(str(v) for v in values) + "\n"


def _parse_csv_row(line, columns):
    parts = line.rstrip("\n").split(",")
    if len(parts) != len(columns):
        raise ValueError(f"CSV row has {len(parts)} fields, expected {len(columns)}")
    out = {}
    for key, raw in zip(columns, parts):
        if key == "hp_frac":
            out[key] = float(raw)
        else:
            out[key] = int(raw)
    return out


def _write_chunk(stream, tag, payload):
    stream.write(bytes([tag]))
    stream.write(struct.pack("<I", len(payload)))
    stream.write(payload)


def _safe_read(stream, size):
    try:
        return stream.read(size)
    except EOFError:
        return b""


def _iter_chunks(stream):
    while True:
        tag_byte = _safe_read(stream, 1)
        if not tag_byte:
            return
        tag = tag_byte[0]
        length_bytes = _safe_read(stream, 4)
        if len(length_bytes) < 4:
            return
        length = struct.unpack("<I", length_bytes)[0]
        payload = _safe_read(stream, length)
        if len(payload) < length:
            return
        yield tag, payload


def episode_path(session_path, instance_id, reset_count):
    return (
        Path(session_path)
        / "telemetry"
        / f"{instance_id}_ep{reset_count:04d}.telemetry.gz"
    )


def read_episode_metadata(path):
    try:
        with gzip.open(path, "rb") as f:
            for tag, payload in _iter_chunks(f):
                if tag != TAG_HEADER:
                    raise ValueError(
                        f"expected header chunk in {path}, got tag 0x{tag:02x}"
                    )
                if not payload.startswith(TELEMETRY_MAGIC):
                    raise ValueError(f"bad telemetry magic in {path}")
                meta = json.loads(payload[len(TELEMETRY_MAGIC) :].decode("utf-8"))
                return meta
    except EOFError:
        pass
    raise ValueError(f"empty or truncated telemetry file: {path}")


def iter_episode_records(path):
    """Yield per-step dicts (CSV columns + ``snapshot`` bytes) from one episode file."""
    try:
        f = gzip.open(path, "rb")
    except EOFError:
        return
    try:
        columns = None
        pending_row = None
        for tag, payload in _iter_chunks(f):
            if tag == TAG_HEADER:
                if not payload.startswith(TELEMETRY_MAGIC):
                    raise ValueError(f"bad telemetry magic in {path}")
                meta = json.loads(payload[len(TELEMETRY_MAGIC) :].decode("utf-8"))
                columns = meta["columns"]
                yield {"_metadata": meta}
            elif tag == TAG_DECODED:
                if columns is None:
                    raise ValueError(f"decoded chunk before header in {path}")
                pending_row = _parse_csv_row(payload.decode("utf-8"), columns)
            elif tag == TAG_SNAPSHOT:
                if columns is None or pending_row is None:
                    raise ValueError(f"snapshot chunk without decoded row in {path}")
                if len(payload) != SNAPSHOT_SIZE:
                    raise ValueError(
                        f"snapshot size {len(payload)} != {SNAPSHOT_SIZE} in {path}"
                    )
                record = dict(pending_row)
                record["snapshot"] = payload
                yield record
                pending_row = None
    except EOFError:
        return
    finally:
        f.close()


def iter_episode_files(telemetry_dir):
    return sorted(Path(telemetry_dir).glob("*.telemetry.gz"))


class TelemetryRecorder:
    def __init__(self, session_path, instance_id):
        self._enabled = os.environ.get("V3_TELEMETRY_OFF", "") != "1"
        self._session_path = Path(session_path)
        self._instance_id = str(instance_id)
        self._reset_count = 0
        self._file = None
        self._steps_since_flush = 0

    @property
    def enabled(self):
        return self._enabled

    def on_reset(self, reset_count):
        self._close_episode()
        self._reset_count = reset_count

    def record_step(self, step, action, snapshot):
        if not self._enabled:
            return
        if len(snapshot) != SNAPSHOT_SIZE:
            raise ValueError(f"snapshot must be {SNAPSHOT_SIZE} bytes, got {len(snapshot)}")
        if self._file is None:
            self._open_episode()
        row = decode_snapshot_to_csv_row(step, action, snapshot)
        _write_chunk(self._file, TAG_DECODED, row.encode("utf-8"))
        _write_chunk(self._file, TAG_SNAPSHOT, snapshot)
        self._steps_since_flush += 1
        if self._steps_since_flush >= FLUSH_INTERVAL:
            self._file.flush()
            self._steps_since_flush = 0

    def on_episode_done(self):
        self._close_episode()

    def close(self):
        self._close_episode()

    def _open_episode(self):
        path = episode_path(self._session_path, self._instance_id, self._reset_count)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = gzip.GzipFile(path, "wb", mtime=0)
        header = {
            "schema_version": SCHEMA_VERSION,
            "instance_id": self._instance_id,
            "episode": self._reset_count,
            "snapshot_size": SNAPSHOT_SIZE,
            "columns": CSV_COLUMNS,
        }
        payload = TELEMETRY_MAGIC + json.dumps(header, separators=(",", ":")).encode(
            "utf-8"
        )
        _write_chunk(self._file, TAG_HEADER, payload)
        self._steps_since_flush = 0

    def _close_episode(self):
        if self._file is not None:
            self._file.flush()
            self._file.close()
            self._file = None
            self._steps_since_flush = 0
