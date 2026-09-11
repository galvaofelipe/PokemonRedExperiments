import hashlib
import json
from pathlib import Path

from frozen.scorer.core import (
    SCORE_VERSION,
    ScoreResult,
    score_snapshots,
)

_BASELINES_DIR = Path(__file__).resolve().parent / "baselines"
_MANIFEST_PATH = _BASELINES_DIR / "manifest.json"


def load_baseline(name):
    with open(_MANIFEST_PATH) as f:
        manifest = json.load(f)
    if name not in manifest:
        raise KeyError(f"unknown baseline: {name}")
    entry = manifest[name]
    path = _BASELINES_DIR / entry["file"]
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != entry["sha256"]:
        raise ValueError(
            f"baseline {name} sha256 mismatch: expected {entry['sha256']}, got {digest}"
        )
    return data


__all__ = [
    "SCORE_VERSION",
    "ScoreResult",
    "load_baseline",
    "score_snapshots",
]
