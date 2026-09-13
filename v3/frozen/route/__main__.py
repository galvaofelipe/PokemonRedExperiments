import sys
from pathlib import Path

from frozen.route import (
    episode_id_from_telemetry,
    extract_route_from_telemetry,
    format_route_table,
    load_route,
)
from frozen.telemetry import iter_episode_files


def _resolve_paths(arg):
    path = Path(arg)
    if path.is_dir():
        return iter_episode_files(path)
    return [path]


def main():
    if len(sys.argv) != 2:
        print(
            "usage: python -m frozen.route <telemetry.gz|telemetry-dir>",
            file=sys.stderr,
        )
        return 1

    route = load_route()
    paths = _resolve_paths(sys.argv[1])
    if not paths:
        print("no telemetry files found")
        return 0

    for tel_path in paths:
        episode_id = episode_id_from_telemetry(tel_path)
        compass = extract_route_from_telemetry(tel_path)
        print(f"=== {episode_id} ===")
        print(format_route_table(route, compass))
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
