import json
import sys
import tempfile
from pathlib import Path

V3_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V3_DIR))

from frozen.eval.scorecard import SCORECARD_VERSION, build_scorecard
from frozen.eval.maps import maps_seen_names
from frozen.ram_map import (
    SNAPSHOT_BASE,
    W_CUR_MAP,
    W_OBTAINED_BADGES,
    W_PLAY_TIME_FRAMES,
    W_PLAY_TIME_HOURS,
    W_PLAY_TIME_MAXED,
    W_PLAY_TIME_MINUTES,
    W_PLAY_TIME_SECONDS,
)
from frozen.splits import (
    SPLITS_VERSION,
    aggregate_splits_section,
    extract_splits_from_telemetry,
    format_game_time,
    load_splits,
    read_play_clock,
)
from frozen.telemetry import TelemetryRecorder

from conftest import FIXTURES_DIR

BADGES_OFF = W_OBTAINED_BADGES - SNAPSHOT_BASE
CUR_MAP_OFF = W_CUR_MAP - SNAPSHOT_BASE
CLOCK_HOURS_OFF = W_PLAY_TIME_HOURS - SNAPSHOT_BASE
CLOCK_MAXED_OFF = W_PLAY_TIME_MAXED - SNAPSHOT_BASE
CLOCK_MINUTES_OFF = W_PLAY_TIME_MINUTES - SNAPSHOT_BASE
CLOCK_SECONDS_OFF = W_PLAY_TIME_SECONDS - SNAPSHOT_BASE
CLOCK_FRAMES_OFF = W_PLAY_TIME_FRAMES - SNAPSHOT_BASE
MT_MOON_EVENT_ADDR = 0xD7F6
HM02_FLY_ADDR = 0xD7E0


def _base_snapshot():
    meta = json.loads((FIXTURES_DIR / "telemetry_has_pokedex" / "meta.json").read_text())
    hex_snap = meta["probed_snapshots"][0]["snapshot_b64"]
    return bytearray(bytes.fromhex(hex_snap))


def _set_bit(snapshot, wram_addr, bit):
    off = wram_addr - SNAPSHOT_BASE
    snapshot[off] |= 1 << bit


def _set_map(snapshot, map_id):
    snapshot[CUR_MAP_OFF] = map_id


def _set_clock(snapshot, hours, minutes, seconds, frames, maxed=0):
    snapshot[CLOCK_HOURS_OFF] = hours
    snapshot[CLOCK_MAXED_OFF] = maxed
    snapshot[CLOCK_MINUTES_OFF] = minutes
    snapshot[CLOCK_SECONDS_OFF] = seconds
    snapshot[CLOCK_FRAMES_OFF] = frames


def _write_episode(session_path, instance_id, steps):
    """steps: list of (action, snapshot_bytes)."""
    recorder = TelemetryRecorder(session_path, instance_id)
    recorder.on_reset(1)
    for step, (action, snapshot) in enumerate(steps):
        recorder.record_step(step, action, snapshot)
    recorder.on_episode_done()
    recorder.close()
    from frozen.telemetry import episode_path

    return episode_path(session_path, instance_id, reset_count=1)


def test_load_splits_validates_manifest():
    data = load_splits()
    assert len(data["splits"]) == 16
    assert data["splits"][0]["split_name"] == "Brock"
    assert data["splits"][1]["split_name"] == "Mt. Moon"


def test_brock_first_hit():
    with tempfile.TemporaryDirectory() as tmp:
        snap0 = bytes(_base_snapshot())
        snap5 = bytearray(_base_snapshot())
        _set_bit(snap5, W_OBTAINED_BADGES, 0)
        _set_clock(snap5, 0, 5, 30, 12)

        tel_path = _write_episode(
            tmp,
            "test_brock",
            [(0, snap0), (0, snap0), (0, snap0), (0, snap0), (0, snap0), (0, bytes(snap5))],
        )
        achieved = extract_splits_from_telemetry(tel_path)
        assert len(achieved) == 1
        assert achieved[0]["name"] == "Brock"
        assert achieved[0]["first_hit_step"] == 5
        assert achieved[0]["game_time"] == "0:05:30"
        assert achieved[0]["initial"] is False


def test_mt_moon_positive():
    with tempfile.TemporaryDirectory() as tmp:
        snaps = [bytes(_base_snapshot()) for _ in range(8)]
        snap3 = bytearray(snaps[3])
        _set_bit(snap3, MT_MOON_EVENT_ADDR, 1)
        snaps[3] = bytes(snap3)

        snap7 = bytearray(snaps[7])
        _set_bit(snap7, MT_MOON_EVENT_ADDR, 1)
        _set_map(snap7, 15)
        snaps[7] = bytes(snap7)

        tel_path = _write_episode(
            tmp,
            "test_mtmoon_pos",
            [(0, s) for s in snaps],
        )
        achieved = extract_splits_from_telemetry(tel_path)
        names = [a["name"] for a in achieved]
        assert "Mt. Moon" in names
        mt = next(a for a in achieved if a["name"] == "Mt. Moon")
        assert mt["first_hit_step"] == 7
        assert mt["initial"] is False


def test_mt_moon_negative():
    with tempfile.TemporaryDirectory() as tmp:
        snaps = [bytes(_base_snapshot()) for _ in range(5)]
        for i in range(1, 5):
            snap = bytearray(snaps[i])
            _set_bit(snap, MT_MOON_EVENT_ADDR, 1)
            snaps[i] = bytes(snap)

        tel_path = _write_episode(
            tmp,
            "test_mtmoon_neg",
            [(0, s) for s in snaps],
        )
        achieved = extract_splits_from_telemetry(tel_path)
        assert "Mt. Moon" not in [a["name"] for a in achieved]


def test_clock_maxed_formatting():
    snap = _base_snapshot()
    _set_clock(snap, 255, 0, 0, 0, maxed=1)
    clock = read_play_clock(bytes(snap))
    assert clock["clock_maxed"] is True
    assert clock["game_time"] == "255:00:00"
    assert clock["game_time_frames"] == 255 * 60 * 60 * 60


def test_initial_at_step_0():
    with tempfile.TemporaryDirectory() as tmp:
        snap = _base_snapshot()
        _set_bit(snap, W_OBTAINED_BADGES, 0)
        tel_path = _write_episode(tmp, "test_initial", [(0, bytes(snap)), (0, bytes(snap))])
        achieved = extract_splits_from_telemetry(tel_path)
        assert len(achieved) == 1
        assert achieved[0]["name"] == "Brock"
        assert achieved[0]["first_hit_step"] == 0
        assert achieved[0]["initial"] is True


def test_segment_time_completion_order():
    """Lt. Surge before HM02 Fly in game time but after in route order."""
    start_frames = 10 * 60 * 60
    surge_frames = 20 * 60 * 60
    fly_frames = 30 * 60 * 60

    with tempfile.TemporaryDirectory() as tmp:
        snaps = []
        for step in range(12):
            snap = bytearray(_base_snapshot())
            if step == 0:
                _set_clock(snap, 0, 10, 0, 0)
            elif step == 5:
                _set_bit(snap, W_OBTAINED_BADGES, 2)
                _set_clock(snap, 0, 20, 0, 0)
            elif step == 11:
                _set_bit(snap, HM02_FLY_ADDR, 6)
                _set_clock(snap, 0, 30, 0, 0)
            else:
                _set_clock(snap, 0, 10, 0, 0)
            snaps.append(bytes(snap))

        tel_path = _write_episode(
            tmp,
            "test_segment_completion",
            [(0, s) for s in snaps],
        )
        achieved = extract_splits_from_telemetry(tel_path)
        by_name = {a["name"]: a for a in achieved}

        assert set(by_name) == {"Lt. Surge", "HM02 Fly"}
        for entry in achieved:
            assert entry["segment_time_frames"] >= 0

        assert by_name["Lt. Surge"]["segment_time_frames"] == surge_frames - start_frames
        assert by_name["HM02 Fly"]["segment_time_frames"] == fly_frames - surge_frames
        assert by_name["Lt. Surge"]["game_time_frames"] < by_name["HM02 Fly"]["game_time_frames"]


def _synthetic_episode(score, components, map_ids, telemetry_file):
    return {
        "state": "fresh_game",
        "seed": 1,
        "steps": 10,
        "score": score,
        "components": components,
        "maps_seen_names": maps_seen_names(map_ids),
        "telemetry_file": telemetry_file,
        "_map_ids": map_ids,
    }


def test_scorecard_splits_integration():
    base_components = {
        "badges": 0,
        "events": 0,
        "dex_caught": 0,
        "dex_seen": 0,
        "unique_maps": 1,
        "level_sum_capped": 5,
    }
    ep1 = _synthetic_episode(1.0, dict(base_components), {0}, "fresh_game_s0_ep0001.telemetry.gz")
    ep2 = _synthetic_episode(2.0, dict(base_components), {1}, "fresh_game_s1_ep0001.telemetry.gz")

    achieved1 = [
        {
            "name": "Brock",
            "first_hit_step": 100,
            "game_time": "0:10:00",
            "game_time_frames": 36000,
            "clock_maxed": False,
            "segment_time": "0:10:00",
            "segment_time_frames": 36000,
            "initial": False,
        }
    ]
    achieved2 = [
        {
            "name": "Brock",
            "first_hit_step": 50,
            "game_time": "0:08:00",
            "game_time_frames": 28800,
            "clock_maxed": False,
            "segment_time": "0:08:00",
            "segment_time_frames": 28800,
            "initial": False,
        }
    ]
    episode_splits = [
        ("fresh_game_s0_ep0001", achieved1),
        ("fresh_game_s1_ep0001", achieved2),
    ]

    card = build_scorecard(
        eval_suite_version="1.0.0",
        checkpoint_path=Path("runs/smoke/poke_40960_steps.zip"),
        checkpoint_sha256="abc",
        init_states=[{"name": "fresh_game", "file": "fast_text_start.state", "sha256": "x"}],
        episodes=[ep1, ep2],
        episode_splits=episode_splits,
    )

    assert card["scorecard_version"] == SCORECARD_VERSION
    assert card["scorecard_version"] == "1.2.0"
    assert card["splits"]["splits_version"] == SPLITS_VERSION
    assert len(card["splits"]["order"]) == 16
    assert card["splits"]["achieved"][0]["name"] == "Brock"
    assert card["splits"]["achieved"][0]["episode"] == "fresh_game_s1_ep0001"
    assert card["episodes"][0]["splits"]["achieved"] == achieved1
    assert "episode" not in card["episodes"][0]["splits"]["achieved"][0]


def test_build_scorecard_omits_splits_without_episode_splits():
    ep = _synthetic_episode(1.0, {
        "badges": 0, "events": 0, "dex_caught": 0, "dex_seen": 0,
        "unique_maps": 1, "level_sum_capped": 5,
    }, {0}, "fresh_game_s0_ep0001.telemetry.gz")
    card = build_scorecard(
        eval_suite_version="1.0.0",
        checkpoint_path=Path("x.zip"),
        checkpoint_sha256="abc",
        init_states=[],
        episodes=[ep],
    )
    assert "splits" not in card


def test_splits_section_json_round_trip():
    achieved = [
        {
            "name": "Brock",
            "first_hit_step": 10,
            "episode": "fresh_game_s0_ep0001",
            "game_time": "0:01:00",
            "game_time_frames": 3600,
            "clock_maxed": False,
            "segment_time": "0:01:00",
            "segment_time_frames": 3600,
            "initial": False,
        }
    ]
    section = aggregate_splits_section([("fresh_game_s0_ep0001", achieved)])
    loaded = json.loads(json.dumps(section))
    assert loaded["splits_version"] == SPLITS_VERSION
    assert loaded["order"][0] == "Brock"
    assert loaded["achieved"][0]["game_time_frames"] == 3600


def test_format_game_time():
    assert format_game_time(0, 5, 30) == "0:05:30"
    assert format_game_time(255, 0, 0) == "255:00:00"
