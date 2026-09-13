#!/usr/bin/env python3
"""Parse pret map headers/objects into Frozen map metadata.

Geography only: overworld connections plus warp_event destinations.
Does not import pyboy. Fly / Teleport / Dig / dungeon-hole tables are out.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
V3_DIR = REPO_ROOT / "v3"
DEFAULT_POKERED = Path.home() / "dev" / "pokered"
DEFAULT_SCRATCH = REPO_ROOT / ".scratch" / "references" / "v3-map-metadata.json"
DEFAULT_FROZEN_JSON = V3_DIR / "frozen" / "maps" / "maps.json"
DEFAULT_FROZEN_MANIFEST = V3_DIR / "frozen" / "maps" / "manifest.json"

W_CUR_MAP = "0xD35E"
W_CUR_MAP_TILESET = "0xD367"

_MAP_CONST_RE = re.compile(
    r"^\s*map_const\s+([A-Z0-9_]+)\s*,\s*(\d+)\s*,\s*(\d+)",
)
_DEF_EQU_RE = re.compile(
    r"^\s*DEF\s+(NUM_CITY_MAPS|FIRST_ROUTE_MAP|FIRST_INDOOR_MAP|NUM_MAPS)\s+EQU\s+const_value",
)
_MAP_HEADER_RE = re.compile(
    r"^\s*map_header\s+(\w+)\s*,\s*([A-Z0-9_]+)\s*,\s*(\w+)",
)
_CONNECTION_RE = re.compile(
    r"^\s*connection\s+(\w+)\s*,\s*\w+\s*,\s*([A-Z0-9_]+)\s*,",
)
_WARP_EVENT_RE = re.compile(
    r"^\s*warp_event\s+(-?\d+)\s*,\s*(-?\d+)\s*,\s*([A-Z0-9_]+)\s*,\s*(-?\d+)",
)
_OBJECT_EVENT_RE = re.compile(r"^\s*object_event\s+(.+)$")
_DEF_WARPS_TO_RE = re.compile(r"^\s*def_warps_to\s+([A-Z0-9_]+)", re.MULTILINE)

_META_NOTES = (
    "kind/size/tileset/warps/trainers are ROM-parsed. tags overlay is Frozen "
    "story metadata for reward gating (puffer MAP_ID_COMPLETION_EVENTS style). "
    "wCurMap 0xFF is a transition sentinel, not a real map."
)

OPPOSITE_DIR = {
    "north": "south",
    "south": "north",
    "west": "east",
    "east": "west",
}


def parse_warp_events(text: str) -> list[dict]:
    """Parse pret warp_event lines. dest may be a map const or LAST_MAP."""
    warps = []
    for line in text.splitlines():
        match = _WARP_EVENT_RE.match(line)
        if not match:
            continue
        x, y, dest, dest_warp = match.groups()
        warps.append(
            {
                "x": int(x),
                "y": int(y),
                "dest": dest,
                "dest_warp": int(dest_warp),
            }
        )
    return warps


def parse_object_events(text: str) -> tuple[int, bool]:
    count = 0
    has_trainer = False
    for line in text.splitlines():
        match = _OBJECT_EVENT_RE.match(line)
        if not match:
            continue
        count += 1
        args = [part.strip() for part in match.group(1).split(",")]
        if any(arg.startswith("OPP_") for arg in args):
            has_trainer = True
    return count, has_trainer


def parse_objects_asm(text: str) -> dict:
    warps = parse_warp_events(text)
    object_count, has_trainer = parse_object_events(text)
    warps_to = None
    match = _DEF_WARPS_TO_RE.search(text)
    if match:
        warps_to = match.group(1)
    return {
        "warps_to": warps_to,
        "warps": warps,
        "object_count": object_count,
        "has_trainer": has_trainer,
    }


def parse_header_asm(text: str) -> dict | None:
    header_match = None
    for line in text.splitlines():
        header_match = _MAP_HEADER_RE.match(line)
        if header_match:
            break
    if header_match is None:
        return None
    label, const, tileset = header_match.groups()
    connections = []
    for line in text.splitlines():
        conn = _CONNECTION_RE.match(line)
        if conn:
            connections.append({"dir": conn.group(1), "map": conn.group(2)})
    return {
        "label": label,
        "const": const,
        "tileset": tileset,
        "connections": connections,
    }


def parse_map_constants(text: str) -> dict:
    maps = []
    markers = {}
    next_id = 0
    for line in text.splitlines():
        const_match = _MAP_CONST_RE.match(line)
        if const_match:
            name, width, height = const_match.groups()
            maps.append(
                {
                    "id": next_id,
                    "const": name,
                    "width": int(width),
                    "height": int(height),
                }
            )
            next_id += 1
            continue
        def_match = _DEF_EQU_RE.match(line)
        if def_match:
            markers[def_match.group(1)] = next_id
    if "NUM_MAPS" not in markers:
        markers["NUM_MAPS"] = next_id
    return {"maps": maps, "markers": markers}


def map_kind(map_id: int, const: str, markers: dict) -> str:
    if const.startswith("UNUSED_MAP_"):
        return "unused"
    num_city = markers["NUM_CITY_MAPS"]
    first_route = markers["FIRST_ROUTE_MAP"]
    first_indoor = markers["FIRST_INDOOR_MAP"]
    if map_id < num_city:
        return "town"
    if first_route <= map_id < first_indoor:
        return "route"
    return "indoor"


def _pick_header_file(const: str, paths: list[Path]) -> Path:
    """If two headers share a const (Copy aliases), keep the non-Copy file."""
    if len(paths) == 1:
        return paths[0]
    if not const.endswith("_COPY"):
        non_copy = [path for path in paths if not path.name.endswith("Copy.asm")]
        if len(non_copy) == 1:
            return non_copy[0]
        if non_copy:
            return sorted(non_copy)[0]
    return sorted(paths)[0]


def load_tags_overlay(path: Path | None) -> dict[str, list[str]]:
    if path is None or not path.is_file():
        return {}
    data = json.loads(path.read_text())
    overlay = {}
    for entry in data.get("maps", []):
        const = entry.get("const")
        if const:
            overlay[const] = list(entry.get("tags", []))
    return overlay


def _scan_headers(headers_dir: Path) -> dict[str, dict]:
    by_const: dict[str, list[tuple[Path, dict]]] = defaultdict(list)
    for path in sorted(headers_dir.glob("*.asm")):
        parsed = parse_header_asm(path.read_text())
        if parsed is None:
            continue
        by_const[parsed["const"]].append((path, parsed))
    chosen = {}
    for const, entries in by_const.items():
        path = _pick_header_file(const, [item[0] for item in entries])
        parsed = next(item[1] for item in entries if item[0] == path)
        parsed = dict(parsed)
        parsed["file"] = path.name
        chosen[const] = parsed
    return chosen


def _scan_objects(objects_dir: Path) -> dict[str, dict]:
    by_const = {}
    for path in sorted(objects_dir.glob("*.asm")):
        parsed = parse_objects_asm(path.read_text())
        const = parsed["warps_to"]
        if const is None:
            continue
        parsed = dict(parsed)
        parsed["file"] = path.name
        by_const[const] = parsed
    return by_const


def build_map_entry(base: dict, markers: dict, header: dict | None, objects: dict | None, tags: list[str]) -> dict:
    warps = list(objects["warps"]) if objects else []
    entry = {
        "id": base["id"],
        "id_hex": f"0x{base['id']:02X}",
        "const": base["const"],
        "width": base["width"],
        "height": base["height"],
        "kind": map_kind(base["id"], base["const"], markers),
        "tileset": header["tileset"] if header else None,
        "connections": list(header["connections"]) if header else [],
        "warp_count": len(warps),
        "warps": warps,
        "object_count": objects["object_count"] if objects else 0,
        "has_trainer": objects["has_trainer"] if objects else False,
        "tags": sorted(tags),
    }
    if header:
        entry["header"] = header["file"]
    if objects:
        entry["objects_file"] = objects["file"]
    if entry["warp_count"] != len(entry["warps"]):
        raise ValueError(f"{base['const']}: warp_count {entry['warp_count']} != len(warps)")
    return entry


def build_map_catalog(pokered: Path, tags_overlay: dict[str, list[str]] | None = None) -> dict:
    pokered = Path(pokered)
    constants = parse_map_constants(
        (pokered / "constants" / "map_constants.asm").read_text()
    )
    headers = _scan_headers(pokered / "data" / "maps" / "headers")
    objects = _scan_objects(pokered / "data" / "maps" / "objects")
    overlay = tags_overlay or {}

    maps = []
    for base in constants["maps"]:
        const = base["const"]
        maps.append(
            build_map_entry(
                base,
                constants["markers"],
                headers.get(const),
                objects.get(const),
                overlay.get(const, []),
            )
        )

    return {
        "meta": {
            "source": (
                "~/dev/pokered constants/map_constants.asm + "
                "data/maps/headers + data/maps/objects"
            ),
            "date": "2026-09-13",
            "notes": _META_NOTES,
            "num_maps": len(maps),
            "wCurMap": W_CUR_MAP,
            "tileset_ram": f"wCurMapTileset {W_CUR_MAP_TILESET}",
        },
        "maps": maps,
    }


def dump_map_metadata(catalog: dict) -> bytes:
    return (json.dumps(catalog, indent=2) + "\n").encode("utf-8")


def maps_by_const(catalog: dict) -> dict[str, dict]:
    return {entry["const"]: entry for entry in catalog["maps"]}


def overworld_connection_edges(catalog: dict) -> list[tuple[str, str, str]]:
    edges = []
    for entry in catalog["maps"]:
        for conn in entry["connections"]:
            edges.append((entry["const"], conn["dir"], conn["map"]))
    return edges


def overworld_component_size(catalog: dict) -> int:
    adj: dict[str, set[str]] = defaultdict(set)
    nodes = []
    for entry in catalog["maps"]:
        if not entry["connections"]:
            continue
        nodes.append(entry["const"])
        for conn in entry["connections"]:
            adj[entry["const"]].add(conn["map"])
            adj[conn["map"]].add(entry["const"])
    if not nodes:
        return 0
    start = nodes[0]
    seen = {start}
    stack = [start]
    while stack:
        cur = stack.pop()
        for nxt in adj[cur]:
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return len(seen)


def connection_gaps(catalog: dict) -> list[str]:
    by_const = maps_by_const(catalog)
    missing = []
    for src, direction, dest in overworld_connection_edges(catalog):
        opposite = OPPOSITE_DIR[direction]
        dest_entry = by_const.get(dest)
        if dest_entry is None:
            missing.append(f"{src} {direction} -> {dest} (unknown dest)")
            continue
        if not any(c["dir"] == opposite and c["map"] == src for c in dest_entry["connections"]):
            missing.append(f"{src} {direction} -> {dest} missing {dest} {opposite} -> {src}")
    return missing


def write_catalog(catalog: dict, scratch_path: Path, frozen_json: Path, frozen_manifest: Path) -> bytes:
    blob = dump_map_metadata(catalog)
    scratch_path.parent.mkdir(parents=True, exist_ok=True)
    frozen_json.parent.mkdir(parents=True, exist_ok=True)
    scratch_path.write_bytes(blob)
    frozen_json.write_bytes(blob)
    digest = hashlib.sha256(blob).hexdigest()
    manifest = {
        "maps": {
            "file": frozen_json.name,
            "sha256": digest,
        }
    }
    frozen_manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    return blob


def _summarize(catalog: dict) -> None:
    last_map = 0
    with_warps = 0
    for entry in catalog["maps"]:
        if entry["warps"]:
            with_warps += 1
        last_map += sum(1 for warp in entry["warps"] if warp["dest"] == "LAST_MAP")
    gaps = connection_gaps(catalog)
    print(f"maps: {catalog['meta']['num_maps']}")
    print(f"maps with warps: {with_warps}")
    print(f"LAST_MAP warps: {last_map}")
    print(f"overworld maps: {sum(1 for m in catalog['maps'] if m['connections'])}")
    print(f"overworld component: {overworld_component_size(catalog)}")
    print(f"connection gaps: {len(gaps)}")
    for gap in gaps:
        print(f"  {gap}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Frozen map metadata from pret.")
    parser.add_argument("--pokered", type=Path, default=DEFAULT_POKERED)
    parser.add_argument("--tags-from", type=Path, default=None)
    parser.add_argument("--scratch", type=Path, default=DEFAULT_SCRATCH)
    parser.add_argument("--frozen-json", type=Path, default=DEFAULT_FROZEN_JSON)
    parser.add_argument("--frozen-manifest", type=Path, default=DEFAULT_FROZEN_MANIFEST)
    args = parser.parse_args(argv)

    if not args.pokered.is_dir():
        print(f"pokered source not found: {args.pokered}", file=sys.stderr)
        return 1

    tags_from = args.tags_from
    if tags_from is None:
        if args.scratch.is_file():
            tags_from = args.scratch
        elif args.frozen_json.is_file():
            tags_from = args.frozen_json

    overlay = load_tags_overlay(tags_from)
    catalog = build_map_catalog(args.pokered, overlay)
    write_catalog(catalog, args.scratch, args.frozen_json, args.frozen_manifest)
    _summarize(catalog)
    print(f"wrote {args.scratch}")
    print(f"wrote {args.frozen_json}")
    print(f"wrote {args.frozen_manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
