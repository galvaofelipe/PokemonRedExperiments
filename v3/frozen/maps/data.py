import hashlib
import json
from pathlib import Path

MAPS_VERSION = "1.0.0"

_MAPS_DIR = Path(__file__).resolve().parent
_MAPS_PATH = _MAPS_DIR / "maps.json"
_MANIFEST_PATH = _MAPS_DIR / "manifest.json"


def load_maps():
    with open(_MANIFEST_PATH) as f:
        manifest = json.load(f)
    entry = manifest["maps"]
    path = _MAPS_DIR / entry["file"]
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != entry["sha256"]:
        raise ValueError(
            f"maps.json sha256 mismatch: expected {entry['sha256']}, got {digest}"
        )
    return json.loads(data.decode("utf-8"))
