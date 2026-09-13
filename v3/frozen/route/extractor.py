"""Route DAG extraction and compass from per-step telemetry snapshots."""

from collections import defaultdict
from pathlib import Path

from frozen.ram_map import SNAPSHOT_BASE, W_CUR_MAP
from frozen.route.data import ROUTE_VERSION, load_route
from frozen.splits.extractor import (
    extract_episode_splits,
    read_bit,
    read_play_clock,
)
from frozen.telemetry import iter_episode_records

# wNumBagItems / wBagItems — v3-obs-ram-map.json; snapshot window 0xD163–0xDA45
W_NUM_BAG_ITEMS = 0xD31D
W_BAG_ITEMS = 0xD31E
BAG_ITEM_CAPACITY = 20
BAG_TERMINATOR = 0xFF

_CUR_MAP_OFF = W_CUR_MAP - SNAPSHOT_BASE
_NUM_BAG_OFF = W_NUM_BAG_ITEMS - SNAPSHOT_BASE
_BAG_ITEMS_OFF = W_BAG_ITEMS - SNAPSHOT_BASE


def bag_contains(snapshot, item_id):
    count = min(snapshot[_NUM_BAG_OFF], BAG_ITEM_CAPACITY)
    for i in range(count):
        slot_id = snapshot[_BAG_ITEMS_OFF + i * 2]
        if slot_id == BAG_TERMINATOR:
            break
        if slot_id == item_id:
            return True
    return False


def _make_hit_record(node_id, step, clock, initial):
    return {
        "id": node_id,
        "first_hit_step": step,
        "game_time": clock["game_time"],
        "game_time_frames": clock["game_time_frames"],
        "clock_maxed": clock["clock_maxed"],
        "initial": initial,
    }


def _hit_from_split(node_id, split_entry):
    return {
        "id": node_id,
        "first_hit_step": split_entry["first_hit_step"],
        "game_time": split_entry["game_time"],
        "game_time_frames": split_entry["game_time_frames"],
        "clock_maxed": split_entry["clock_maxed"],
        "initial": split_entry["initial"],
    }


def _non_split_hit(hit, snapshot):
    htype = hit["type"]
    if htype == "event_bit":
        return read_bit(snapshot, hit["addr_int"], hit["bit"])
    if htype == "map_entry":
        return snapshot[_CUR_MAP_OFF] == hit["map_id"]
    if htype == "bag_item":
        return bag_contains(snapshot, hit["item_id"])
    raise ValueError(f"unknown hit type: {htype}")


def parents_by_node(route):
    parents = defaultdict(list)
    for edge in route["edges"]:
        parents[edge["to"]].append(edge["from"])
    return parents


def compute_compass(route, achieved_by_id, entered_maps=None):
    parents = parents_by_node(route)
    achieved_ids = set(achieved_by_id)
    spine = list(route["spine"])
    node_order = [node["id"] for node in route["nodes"]]
    node_by_id = {node["id"]: node for node in route["nodes"]}

    frontier = []
    for node_id in node_order:
        if node_id in achieved_ids:
            continue
        if all(parent in achieved_ids for parent in parents[node_id]):
            frontier.append(node_id)

    furthest_spine = None
    for node_id in spine:
        if node_id in achieved_ids:
            furthest_spine = node_id
        else:
            break

    off_spine = [
        node_id
        for node_id in node_order
        if node_id in achieved_ids and not node_by_id[node_id]["spine"]
    ]
    achieved = [
        achieved_by_id[node_id] for node_id in node_order if node_id in achieved_by_id
    ]

    result = {
        "route_version": ROUTE_VERSION,
        "spine": spine,
        "achieved": achieved,
        "frontier": frontier,
        "furthest_spine": furthest_spine,
        "off_spine": off_spine,
    }

    if entered_maps is not None:
        missing = []
        seen = set()
        for node in route["nodes"]:
            if not (node["spine"] or node["id"] in frontier):
                continue
            for const, map_id in zip(node["maps"], node["map_ids"]):
                if map_id not in entered_maps and const not in seen:
                    seen.add(const)
                    missing.append(const)
        result["missing_essential_maps"] = missing

    return result


def extract_episode_route(records, route=None):
    if route is None:
        route = load_route()

    split_nodes = [node for node in route["nodes"] if node["hit"]["type"] == "split"]
    other_nodes = [node for node in route["nodes"] if node["hit"]["type"] != "split"]

    split_by_name = {entry["name"]: entry for entry in extract_episode_splits(records)}
    achieved_by_id = {}
    for node in split_nodes:
        split_entry = split_by_name.get(node["hit"]["split_name"])
        if split_entry is not None:
            achieved_by_id[node["id"]] = _hit_from_split(node["id"], split_entry)

    steps = [rec for rec in records if "snapshot" in rec]
    entered_maps = set()
    for rec in steps:
        snapshot = rec["snapshot"]
        entered_maps.add(snapshot[_CUR_MAP_OFF])
        initial = rec is steps[0]
        for node in other_nodes:
            node_id = node["id"]
            if node_id in achieved_by_id:
                continue
            if _non_split_hit(node["hit"], snapshot):
                clock = read_play_clock(snapshot)
                achieved_by_id[node_id] = _make_hit_record(
                    node_id, rec["step"], clock, initial
                )

    return compute_compass(route, achieved_by_id, entered_maps)


def episode_id_from_telemetry(path):
    name = Path(path).name
    if name.endswith(".telemetry.gz"):
        return name[: -len(".telemetry.gz")]
    return Path(path).stem


def extract_route_from_telemetry(path):
    records = []
    for item in iter_episode_records(path):
        if "_metadata" not in item:
            records.append(item)
    return extract_episode_route(records)


def _best_hit(prev, candidate):
    if candidate["game_time_frames"] < prev["game_time_frames"]:
        return candidate
    if (
        candidate["game_time_frames"] == prev["game_time_frames"]
        and candidate["first_hit_step"] < prev["first_hit_step"]
    ):
        return candidate
    return prev


def aggregate_route_section(per_episode, route=None):
    if route is None:
        route = load_route()
    best = {}
    for episode_id, achieved in per_episode:
        for entry in achieved:
            candidate = dict(entry)
            candidate["episode"] = episode_id
            node_id = candidate["id"]
            if node_id not in best:
                best[node_id] = candidate
            else:
                best[node_id] = _best_hit(best[node_id], candidate)
    return compute_compass(route, best)


def format_route_table(route, compass):
    achieved_by_id = {entry["id"]: entry for entry in compass["achieved"]}
    lines = [
        f"{'Node':<28} {'Step':>6}  {'Game Time':>10}  {'Role':>8}",
        "-" * 60,
    ]
    for node in route["nodes"]:
        role = "spine" if node["spine"] else "off"
        if node["id"] in achieved_by_id:
            entry = achieved_by_id[node["id"]]
            lines.append(
                f"{node['id']:<28} {entry['first_hit_step']:>6}  "
                f"{entry['game_time']:>10}  {role:>8}"
            )
        else:
            mark = "*" if node["id"] in compass["frontier"] else "-"
            lines.append(f"{node['id']:<28} {mark:>6}  {'-':>10}  {role:>8}")
    lines.append("")
    lines.append(f"furthest_spine: {compass['furthest_spine']}")
    lines.append(f"frontier: {', '.join(compass['frontier']) or '-'}")
    lines.append(f"off_spine: {', '.join(compass['off_spine']) or '-'}")
    missing = compass.get("missing_essential_maps")
    if missing is not None:
        lines.append(f"missing_essential_maps: {', '.join(missing) or '-'}")
    return "\n".join(lines)
