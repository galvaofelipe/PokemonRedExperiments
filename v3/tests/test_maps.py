import hashlib
import json
import sys
from pathlib import Path

import pytest

V3_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = V3_DIR.parent
sys.path.insert(0, str(V3_DIR))

from frozen.maps import MAPS_VERSION, load_maps
from verify.generate_map_metadata import (
    connection_gaps,
    maps_by_const,
    overworld_component_size,
    parse_objects_asm,
    parse_warp_events,
)

from conftest import FIXTURES_DIR

MAP_FIXTURES = FIXTURES_DIR / "maps"
SCRATCH_CATALOG = REPO_ROOT / ".scratch" / "references" / "v3-map-metadata.json"
FROZEN_CATALOG = V3_DIR / "frozen" / "maps" / "maps.json"


def _fixture_text(name):
    return (MAP_FIXTURES / name).read_text()


def test_parse_pallet_town_doors():
    warps = parse_warp_events(_fixture_text("PalletTown.asm"))
    assert [w["dest"] for w in warps] == ["REDS_HOUSE_1F", "BLUES_HOUSE", "OAKS_LAB"]
    assert warps[0] == {"x": 5, "y": 5, "dest": "REDS_HOUSE_1F", "dest_warp": 1}
    assert warps[1] == {"x": 13, "y": 5, "dest": "BLUES_HOUSE", "dest_warp": 1}
    assert warps[2] == {"x": 12, "y": 11, "dest": "OAKS_LAB", "dest_warp": 2}
    parsed = parse_objects_asm(_fixture_text("PalletTown.asm"))
    assert parsed["warps_to"] == "PALLET_TOWN"
    assert parsed["object_count"] == 3
    assert parsed["has_trainer"] is False


def test_parse_pewter_gym_last_map():
    warps = parse_warp_events(_fixture_text("PewterGym.asm"))
    assert warps == [
        {"x": 4, "y": 13, "dest": "LAST_MAP", "dest_warp": 3},
        {"x": 5, "y": 13, "dest": "LAST_MAP", "dest_warp": 3},
    ]
    parsed = parse_objects_asm(_fixture_text("PewterGym.asm"))
    assert parsed["warps_to"] == "PEWTER_GYM"
    assert parsed["has_trainer"] is True


def test_parse_mt_moon_1f_named_floors():
    warps = parse_warp_events(_fixture_text("MtMoon1F.asm"))
    dests = [w["dest"] for w in warps]
    assert dests.count("LAST_MAP") == 2
    assert dests.count("MT_MOON_B1F") == 3
    assert "LAST_MAP" in dests
    parsed = parse_objects_asm(_fixture_text("MtMoon1F.asm"))
    assert parsed["warps_to"] == "MT_MOON_1F"
    assert parsed["object_count"] == 13
    assert parsed["has_trainer"] is True


def test_load_maps_validates_manifest():
    data = load_maps()
    assert MAPS_VERSION == "1.0.0"
    assert data["meta"]["num_maps"] == 248
    assert len(data["maps"]) == 248
    by_const = maps_by_const(data)
    pallet = by_const["PALLET_TOWN"]
    assert pallet["tags"] == ["oak_town", "start"]
    assert [w["dest"] for w in pallet["warps"]] == [
        "REDS_HOUSE_1F",
        "BLUES_HOUSE",
        "OAKS_LAB",
    ]
    pewter = by_const["PEWTER_GYM"]
    assert pewter["warps"]
    assert all(w["dest"] == "LAST_MAP" for w in pewter["warps"])
    assert "LAST_MAP" in {w["dest"] for m in data["maps"] for w in m["warps"]}


def test_warp_count_matches_warps_list():
    data = load_maps()
    for entry in data["maps"]:
        assert entry["warp_count"] == len(entry["warps"])
        for warp in entry["warps"]:
            assert set(warp) == {"x", "y", "dest", "dest_warp"}


def test_mt_moon_floors_name_each_other():
    by_const = maps_by_const(load_maps())
    one_f = {w["dest"] for w in by_const["MT_MOON_1F"]["warps"]}
    b1f = {w["dest"] for w in by_const["MT_MOON_B1F"]["warps"]}
    b2f = {w["dest"] for w in by_const["MT_MOON_B2F"]["warps"]}
    assert "MT_MOON_B1F" in one_f
    assert "MT_MOON_1F" in b1f
    assert "MT_MOON_B2F" in b1f
    assert "MT_MOON_B1F" in b2f


def test_overworld_connections_one_reciprocal_component():
    data = load_maps()
    connected = [m for m in data["maps"] if m["connections"]]
    assert len(connected) == 36
    assert overworld_component_size(data) == 36
    assert connection_gaps(data) == []


def test_scratch_catalog_matches_frozen_bytes():
    if not SCRATCH_CATALOG.is_file():
        pytest.skip("scratch catalog not present")
    assert SCRATCH_CATALOG.read_bytes() == FROZEN_CATALOG.read_bytes()


def test_load_maps_rejects_tampered_file(tmp_path, monkeypatch):
    maps_dir = tmp_path / "frozen" / "maps"
    maps_dir.mkdir(parents=True)
    original = FROZEN_CATALOG.read_bytes()
    tampered = bytearray(original)
    tampered[0] ^= 0xFF
    (maps_dir / "maps.json").write_bytes(tampered)
    digest = hashlib.sha256(original).hexdigest()
    (maps_dir / "manifest.json").write_text(
        json.dumps({"maps": {"file": "maps.json", "sha256": digest}})
    )

    import frozen.maps.data as maps_data

    monkeypatch.setattr(maps_data, "_MAPS_DIR", maps_dir)
    monkeypatch.setattr(maps_data, "_MANIFEST_PATH", maps_dir / "manifest.json")
    with pytest.raises(ValueError, match="sha256 mismatch"):
        maps_data.load_maps()
