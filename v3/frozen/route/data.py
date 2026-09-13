import hashlib
import json
from pathlib import Path

from frozen.maps import load_maps

ROUTE_VERSION = "1.0.0"

_ROUTE_DIR = Path(__file__).resolve().parent
_ROUTE_PATH = _ROUTE_DIR / "route.json"
_MANIFEST_PATH = _ROUTE_DIR / "manifest.json"


def _parse_hex(value):
    if isinstance(value, str):
        return int(value, 16)
    return value


def _maps_by_const(maps_data):
    return {entry["const"]: entry["id"] for entry in maps_data["maps"]}


def _resolve_const(by_const, const):
    if const not in by_const:
        raise ValueError(f"unknown map const: {const}")
    return by_const[const]


def _resolve_route(data, maps_data):
    by_const = _maps_by_const(maps_data)
    node_ids = {node["id"] for node in data["nodes"]}
    for node in data["nodes"]:
        node["map_ids"] = [_resolve_const(by_const, const) for const in node["maps"]]
        hit = node["hit"]
        htype = hit["type"]
        if htype == "map_entry":
            hit["map_id"] = _resolve_const(by_const, hit["map"])
        elif htype == "event_bit":
            hit["addr_int"] = _parse_hex(hit["addr"])
        elif htype == "bag_item":
            hit["item_id"] = _parse_hex(hit["id"])
        elif htype != "split":
            raise ValueError(f"unknown hit type: {htype}")
    for edge in data["edges"]:
        if edge["from"] not in node_ids or edge["to"] not in node_ids:
            raise ValueError(
                f"edge {edge['from']!r} -> {edge['to']!r} references unknown node"
            )
    return data


def load_route():
    with open(_MANIFEST_PATH) as f:
        manifest = json.load(f)
    entry = manifest["route"]
    path = _ROUTE_DIR / entry["file"]
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != entry["sha256"]:
        raise ValueError(
            f"route.json sha256 mismatch: expected {entry['sha256']}, got {digest}"
        )
    data = json.loads(raw.decode("utf-8"))
    return _resolve_route(data, load_maps())
