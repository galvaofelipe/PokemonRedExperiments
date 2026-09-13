import hashlib
import json
import sys
import tempfile
from pathlib import Path

import pytest

V3_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V3_DIR))

from frozen.eval.maps import maps_seen_names
from frozen.eval.scorecard import SCORECARD_VERSION, build_scorecard
from frozen.ram_map import (
    SNAPSHOT_BASE,
    SNAPSHOT_SIZE,
    W_CUR_MAP,
    W_OBTAINED_BADGES,
    W_PLAY_TIME_FRAMES,
    W_PLAY_TIME_HOURS,
    W_PLAY_TIME_MAXED,
    W_PLAY_TIME_MINUTES,
    W_PLAY_TIME_SECONDS,
)
from frozen.route import (
    ROUTE_VERSION,
    aggregate_route_section,
    compute_compass,
    extract_route_from_telemetry,
    load_route,
)
from frozen.route.extractor import W_BAG_ITEMS, W_NUM_BAG_ITEMS
from frozen.telemetry import TelemetryRecorder

BADGES_OFF = W_OBTAINED_BADGES - SNAPSHOT_BASE
CUR_MAP_OFF = W_CUR_MAP - SNAPSHOT_BASE
CLOCK_HOURS_OFF = W_PLAY_TIME_HOURS - SNAPSHOT_BASE
CLOCK_MAXED_OFF = W_PLAY_TIME_MAXED - SNAPSHOT_BASE
CLOCK_MINUTES_OFF = W_PLAY_TIME_MINUTES - SNAPSHOT_BASE
CLOCK_SECONDS_OFF = W_PLAY_TIME_SECONDS - SNAPSHOT_BASE
CLOCK_FRAMES_OFF = W_PLAY_TIME_FRAMES - SNAPSHOT_BASE
NUM_BAG_OFF = W_NUM_BAG_ITEMS - SNAPSHOT_BASE
BAG_ITEMS_OFF = W_BAG_ITEMS - SNAPSHOT_BASE
PARCEL_ADDR = 0xD74E
POKEDEX_ADDR = 0xD74B
FROZEN_ROUTE = V3_DIR / "frozen" / "route" / "route.json"

ROUTE_SECTION_KEYS = {
    "route_version",
    "spine",
    "achieved",
    "frontier",
    "furthest_spine",
    "off_spine",
}


def _base_snapshot():
    return bytearray(SNAPSHOT_SIZE)


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


def _set_bag_item(snapshot, item_id, qty=1):
    snapshot[NUM_BAG_OFF] = 1
    snapshot[BAG_ITEMS_OFF] = item_id
    snapshot[BAG_ITEMS_OFF + 1] = qty
    snapshot[BAG_ITEMS_OFF + 2] = 0xFF


def _write_episode(session_path, instance_id, steps):
    recorder = TelemetryRecorder(session_path, instance_id)
    recorder.on_reset(1)
    for step, (action, snapshot) in enumerate(steps):
        recorder.record_step(step, action, snapshot)
    recorder.on_episode_done()
    recorder.close()
    from frozen.telemetry import episode_path

    return episode_path(session_path, instance_id, reset_count=1)


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


def _hit_record(node_id, step=1, frames=3600):
    hours = frames // (60 * 60 * 60)
    rem = frames % (60 * 60 * 60)
    minutes = rem // (60 * 60)
    seconds = (rem % (60 * 60)) // 60
    return {
        "id": node_id,
        "first_hit_step": step,
        "game_time": f"{hours}:{minutes:02d}:{seconds:02d}",
        "game_time_frames": frames,
        "clock_maxed": False,
        "initial": False,
    }


def test_load_route_validates_manifest():
    data = load_route()
    assert ROUTE_VERSION == "1.0.0"
    assert data["spine"][0] == "parcel"
    assert data["spine"][-1] == "hof"
    assert len(data["spine"]) == 23
    by_id = {node["id"]: node for node in data["nodes"]}
    assert set(data["spine"]) == {n["id"] for n in data["nodes"] if n["spine"]}
    assert {n["id"] for n in data["nodes"] if not n["spine"]} == {
        "nugget_bridge",
        "erika",
        "sabrina",
    }
    assert by_id["card_key"]["hit"]["type"] == "bag_item"
    assert by_id["card_key"]["hit"]["item_id"] == 0x30
    assert by_id["secret_key"]["hit"]["type"] == "bag_item"
    assert by_id["secret_key"]["hit"]["item_id"] == 0x2B
    assert by_id["parcel"]["map_ids"] == [42]
    assert "VIRIDIAN_MART" in by_id["parcel"]["maps"]
    assert by_id["nugget_bridge"]["maps"] == []
    assert by_id["cascade"]["parallel_group"] == "cerulean_fork"
    assert by_id["ss_ticket"]["parallel_group"] == "cerulean_fork"
    assert by_id["nugget_bridge"]["parallel_group"] == "cerulean_fork"
    assert by_id["thunder"]["parallel_group"] == "post_cut"
    assert by_id["erika"]["parallel_group"] == "post_cut"
    assert by_id["silph_scope"]["parallel_group"] == "post_cut"
    for node_id in ("soul", "sabrina", "hm03", "hm04", "volcano"):
        assert by_id[node_id]["parallel_group"] == "post_flute"


def test_load_route_rejects_tampered_file(tmp_path, monkeypatch):
    route_dir = tmp_path / "frozen" / "route"
    route_dir.mkdir(parents=True)
    original = FROZEN_ROUTE.read_bytes()
    tampered = bytearray(original)
    tampered[0] ^= 0xFF
    (route_dir / "route.json").write_bytes(tampered)
    digest = hashlib.sha256(original).hexdigest()
    (route_dir / "manifest.json").write_text(
        json.dumps({"route": {"file": "route.json", "sha256": digest}})
    )

    import frozen.route.data as route_data

    monkeypatch.setattr(route_data, "_ROUTE_DIR", route_dir)
    monkeypatch.setattr(route_data, "_MANIFEST_PATH", route_dir / "manifest.json")
    with pytest.raises(ValueError, match="sha256 mismatch"):
        route_data.load_route()


def test_in_order_spine_advances_furthest_prefix():
    route = load_route()
    empty = compute_compass(route, {})
    assert empty["furthest_spine"] is None
    assert empty["frontier"] == ["parcel"]

    with tempfile.TemporaryDirectory() as tmp:
        snap0 = bytes(_base_snapshot())
        snap1 = bytearray(_base_snapshot())
        _set_bit(snap1, PARCEL_ADDR, 1)
        _set_clock(snap1, 0, 1, 0, 0)
        tel_path = _write_episode(tmp, "spine_parcel", [(0, snap0), (0, bytes(snap1))])
        compass = extract_route_from_telemetry(tel_path)

    assert [a["id"] for a in compass["achieved"]] == ["parcel"]
    assert compass["achieved"][0]["first_hit_step"] == 1
    assert compass["achieved"][0]["game_time"] == "0:01:00"
    assert compass["furthest_spine"] == "parcel"
    assert compass["frontier"] == ["pokedex"]
    assert "boulder" not in compass["frontier"]

    with tempfile.TemporaryDirectory() as tmp:
        snap0 = bytes(_base_snapshot())
        snap1 = bytearray(_base_snapshot())
        _set_bit(snap1, PARCEL_ADDR, 1)
        _set_bit(snap1, POKEDEX_ADDR, 5)
        _set_clock(snap1, 0, 2, 0, 0)
        tel_path = _write_episode(
            tmp, "spine_dex", [(0, snap0), (0, bytes(snap1))]
        )
        compass = extract_route_from_telemetry(tel_path)

    assert compass["furthest_spine"] == "pokedex"
    assert compass["frontier"] == ["boulder"]
    assert [a["id"] for a in compass["achieved"]] == ["parcel", "pokedex"]


def test_parallel_only_erika_is_off_spine_not_frontier_leak():
    with tempfile.TemporaryDirectory() as tmp:
        snap0 = bytes(_base_snapshot())
        snap1 = bytearray(_base_snapshot())
        _set_bit(snap1, W_OBTAINED_BADGES, 3)
        _set_clock(snap1, 0, 8, 0, 0)
        tel_path = _write_episode(tmp, "erika_only", [(0, snap0), (0, bytes(snap1))])
        compass = extract_route_from_telemetry(tel_path)

    assert [a["id"] for a in compass["achieved"]] == ["erika"]
    assert compass["off_spine"] == ["erika"]
    assert compass["furthest_spine"] is None
    assert "thunder" not in compass["frontier"]
    assert "earth" not in compass["frontier"]
    assert "silph_scope" not in compass["frontier"]
    assert compass["frontier"] == ["parcel"]


def test_parent_blocked_thunder_not_on_frontier():
    route = load_route()
    compass = compute_compass(route, {})
    assert "thunder" not in compass["frontier"]
    assert compass["frontier"] == ["parcel"]

    with tempfile.TemporaryDirectory() as tmp:
        snap0 = bytes(_base_snapshot())
        snap1 = bytearray(_base_snapshot())
        _set_bit(snap1, W_OBTAINED_BADGES, 2)
        _set_clock(snap1, 0, 6, 0, 0)
        tel_path = _write_episode(
            tmp, "thunder_before_hm01", [(0, snap0), (0, bytes(snap1))]
        )
        compass = extract_route_from_telemetry(tel_path)

    assert [a["id"] for a in compass["achieved"]] == ["thunder"]
    assert "thunder" not in compass["frontier"]
    assert "earth" not in compass["frontier"]
    assert "hm01_before_anne_leaves" not in compass["frontier"]
    assert compass["frontier"] == ["parcel"]


def test_out_of_order_later_spine_does_not_advance_prefix():
    route = load_route()
    compass = compute_compass(route, {"hof": _hit_record("hof")})
    assert compass["furthest_spine"] is None
    assert compass["frontier"] == ["parcel"]
    assert [a["id"] for a in compass["achieved"]] == ["hof"]


def test_card_key_bag_first_presence():
    with tempfile.TemporaryDirectory() as tmp:
        snap0 = bytes(_base_snapshot())
        snap1 = bytearray(_base_snapshot())
        _set_bag_item(snap1, 0x30)
        _set_clock(snap1, 0, 4, 0, 0)
        snap2 = bytearray(snap1)
        snap2[NUM_BAG_OFF] = 0
        snap2[BAG_ITEMS_OFF] = 0xFF
        tel_path = _write_episode(
            tmp,
            "card_key_bag",
            [(0, snap0), (0, bytes(snap1)), (0, bytes(snap2))],
        )
        compass = extract_route_from_telemetry(tel_path)

    by_id = {a["id"]: a for a in compass["achieved"]}
    assert "card_key" in by_id
    assert by_id["card_key"]["first_hit_step"] == 1
    assert by_id["card_key"]["game_time"] == "0:04:00"


def test_scorecard_omits_route_without_episode_route():
    ep = _synthetic_episode(
        1.0,
        {
            "badges": 0,
            "events": 0,
            "dex_caught": 0,
            "dex_seen": 0,
            "unique_maps": 1,
            "level_sum_capped": 5,
        },
        {0},
        "fresh_game_s0_ep0001.telemetry.gz",
    )
    card = build_scorecard(
        eval_suite_version="1.0.0",
        checkpoint_path=Path("x.zip"),
        checkpoint_sha256="abc",
        init_states=[],
        episodes=[ep],
    )
    assert "route" not in card
    assert card["scorecard_version"] == SCORECARD_VERSION


def test_scorecard_route_section_keys():
    base_components = {
        "badges": 0,
        "events": 0,
        "dex_caught": 0,
        "dex_seen": 0,
        "unique_maps": 1,
        "level_sum_capped": 5,
    }
    ep1 = _synthetic_episode(
        1.0, dict(base_components), {0}, "fresh_game_s0_ep0001.telemetry.gz"
    )
    ep2 = _synthetic_episode(
        2.0, dict(base_components), {1}, "fresh_game_s1_ep0001.telemetry.gz"
    )
    achieved1 = [_hit_record("parcel", step=100, frames=36000)]
    achieved2 = [_hit_record("parcel", step=50, frames=28800)]
    episode_route = [
        ("fresh_game_s0_ep0001", achieved1),
        ("fresh_game_s1_ep0001", achieved2),
    ]
    card = build_scorecard(
        eval_suite_version="1.0.0",
        checkpoint_path=Path("runs/smoke/poke_40960_steps.zip"),
        checkpoint_sha256="abc",
        init_states=[{"name": "fresh_game", "file": "fast_text_start.state", "sha256": "x"}],
        episodes=[ep1, ep2],
        episode_route=episode_route,
    )

    assert card["scorecard_version"] == "1.2.0"
    assert set(card["route"]) >= ROUTE_SECTION_KEYS
    assert card["route"]["route_version"] == ROUTE_VERSION
    assert card["route"]["furthest_spine"] == "parcel"
    assert card["route"]["frontier"] == ["pokedex"]
    assert card["route"]["achieved"][0]["id"] == "parcel"
    assert card["route"]["achieved"][0]["episode"] == "fresh_game_s1_ep0001"
    assert card["episodes"][0]["route"]["achieved"] == achieved1
    assert "episode" not in card["episodes"][0]["route"]["achieved"][0]
    assert card["components_mean"]["unique_maps"] == 1


def test_route_section_json_round_trip():
    achieved = [_hit_record("parcel")]
    section = aggregate_route_section([("fresh_game_s0_ep0001", achieved)])
    loaded = json.loads(json.dumps(section))
    assert loaded["route_version"] == ROUTE_VERSION
    assert loaded["furthest_spine"] == "parcel"
    assert loaded["achieved"][0]["id"] == "parcel"
