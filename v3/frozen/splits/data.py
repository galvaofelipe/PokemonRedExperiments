import hashlib
import json
from pathlib import Path

SPLITS_VERSION = "1.0.0"

_SPLITS_DIR = Path(__file__).resolve().parent
_SPLITS_PATH = _SPLITS_DIR / "splits.json"
_MANIFEST_PATH = _SPLITS_DIR / "manifest.json"


def load_splits():
    with open(_MANIFEST_PATH) as f:
        manifest = json.load(f)
    entry = manifest["splits"]
    path = _SPLITS_DIR / entry["file"]
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != entry["sha256"]:
        raise ValueError(
            f"splits.json sha256 mismatch: expected {entry['sha256']}, got {digest}"
        )
    return json.loads(data.decode("utf-8"))
