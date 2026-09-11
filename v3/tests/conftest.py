import json
import sys
from pathlib import Path

import pytest

V3_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V3_DIR))

from frozen.ram_map import SNAPSHOT_SIZE

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def load_fixture_snapshots(fixture_dir):
    data = (fixture_dir / "snapshots.bin").read_bytes()
    n = len(data) // SNAPSHOT_SIZE
    return [data[i * SNAPSHOT_SIZE : (i + 1) * SNAPSHOT_SIZE] for i in range(n)]


def load_fixture_meta(fixture_dir):
    with open(fixture_dir / "meta.json") as f:
        return json.load(f)


@pytest.fixture
def fixture_loader():
    def _load(name):
        fixture_dir = FIXTURES_DIR / name
        return load_fixture_snapshots(fixture_dir), load_fixture_meta(fixture_dir)

    return _load
