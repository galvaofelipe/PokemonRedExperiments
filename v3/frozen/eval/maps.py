import json
from functools import lru_cache
from pathlib import Path

_MAP_DATA_PATH = Path(__file__).resolve().parents[1] / "env" / "map_data.json"


@lru_cache(maxsize=1)
def load_map_names() -> dict[int, str]:
    with open(_MAP_DATA_PATH) as f:
        data = json.load(f)
    names = {}
    for region in data["regions"]:
        raw_id = region["id"]
        if not raw_id.lstrip("-").isdigit():
            continue
        names[int(raw_id)] = region["name"]
    return names


def map_id_to_name(map_id: int, names: dict[int, str] | None = None) -> str:
    table = load_map_names() if names is None else names
    return table.get(map_id, f"0x{map_id:02X}")


def filter_scoring_map_ids(map_ids: set[int]) -> set[int]:
    from frozen.ram_map import NUM_MAPS

    return {mid for mid in map_ids if mid < NUM_MAPS}


def maps_seen_names(map_ids: set[int], names: dict[int, str] | None = None) -> list[str]:
    table = load_map_names() if names is None else names
    scoring_ids = filter_scoring_map_ids(map_ids)
    return [map_id_to_name(mid, table) for mid in sorted(scoring_ids)]
