import sys
from pathlib import Path

from frozen.splits import (
    episode_id_from_telemetry,
    extract_splits_from_telemetry,
    format_splits_table,
    load_splits,
)
from frozen.telemetry import iter_episode_files


def _resolve_paths(arg):
    path = Path(arg)
    if path.is_dir():
        return iter_episode_files(path)
    return [path]


def main():
    if len(sys.argv) != 2:
        print(f"usage: python -m frozen.splits <telemetry.gz|telemetry-dir>", file=sys.stderr)
        return 1

    data = load_splits()
    order = [s["split_name"] for s in data["splits"]]

    paths = _resolve_paths(sys.argv[1])
    if not paths:
        print("no telemetry files found")
        return 0

    for tel_path in paths:
        episode_id = episode_id_from_telemetry(tel_path)
        achieved = extract_splits_from_telemetry(tel_path)
        achieved_by_name = {e["name"]: e for e in achieved}
        print(f"=== {episode_id} ===")
        print(format_splits_table(order, achieved_by_name))
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
