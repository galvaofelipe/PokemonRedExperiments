import json
import subprocess
import tempfile
from pathlib import Path

from frozen.eval.maps import maps_seen_names
from frozen.scorer import SCORE_VERSION

SCORECARD_VERSION = "1.0.0"

COMPONENT_KEYS = (
    "badges",
    "events",
    "dex_caught",
    "dex_seen",
    "unique_maps",
    "level_sum_capped",
)


def git_head_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.STDOUT
    ).strip()


def build_scorecard(
    *,
    eval_suite_version: str,
    checkpoint_path: Path,
    checkpoint_sha256: str,
    init_states: list[dict],
    episodes: list[dict],
) -> dict:
    if not episodes:
        raise ValueError("scorecard requires at least one episode")

    scores = [ep["score"] for ep in episodes]
    components_mean = {}
    for key in COMPONENT_KEYS:
        components_mean[key] = sum(ep["components"][key] for ep in episodes) / len(
            episodes
        )

    union_map_ids: set[int] = set()
    for ep in episodes:
        union_map_ids.update(ep["_map_ids"])

    public_episodes = []
    for ep in episodes:
        public_episodes.append(
            {
                "state": ep["state"],
                "seed": ep["seed"],
                "steps": ep["steps"],
                "score": ep["score"],
                "components": dict(ep["components"]),
                "maps_seen_names": ep["maps_seen_names"],
                "telemetry_file": ep["telemetry_file"],
            }
        )

    return {
        "scorecard_version": SCORECARD_VERSION,
        "score_version": SCORE_VERSION,
        "eval_suite_version": eval_suite_version,
        "commit": git_head_commit(),
        "checkpoint": {
            "path": str(checkpoint_path.resolve()),
            "sha256": checkpoint_sha256,
        },
        "init_states": init_states,
        "score": {
            "mean": sum(scores) / len(scores),
            "max": max(scores),
        },
        "components_mean": components_mean,
        "maps_seen_names": maps_seen_names(union_map_ids),
        "episodes": public_episodes,
    }


def write_scorecard(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=False)
    payload += "\n"
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, delete=False, suffix=".tmp"
    ) as tmp:
        tmp.write(payload)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)
