import gzip
import json
import sys
import tempfile
from pathlib import Path

import pytest

V3_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V3_DIR))

from frozen.scorer import load_baseline, score_snapshots
from frozen.telemetry import (
    SNAPSHOT_SIZE,
    iter_episode_files,
    iter_episode_records,
    read_episode_metadata,
)
from frozen.ram_map import SNAPSHOT_SIZE as RAM_SNAPSHOT_SIZE

from conftest import FIXTURES_DIR

assert SNAPSHOT_SIZE == RAM_SNAPSHOT_SIZE

TELEMETRY_SCENARIOS = ["telemetry_init", "telemetry_has_pokedex"]


def load_telemetry_meta(name):
    with open(FIXTURES_DIR / name / "meta.json") as f:
        return json.load(f)


def telemetry_dir(name):
    return FIXTURES_DIR / name / "telemetry"


def records_for_episode(path):
    rows = []
    for item in iter_episode_records(path):
        if "_metadata" in item:
            continue
        rows.append(item)
    return rows


@pytest.mark.parametrize("scenario", TELEMETRY_SCENARIOS)
def test_one_file_per_episode(scenario):
    meta = load_telemetry_meta(scenario)
    files = iter_episode_files(telemetry_dir(scenario))
    assert len(files) == 2
    names = [f.name for f in files]
    assert names == meta["telemetry_files"]
    instance = meta["instance_id"]
    assert names == [
        f"{instance}_ep0001.telemetry.gz",
        f"{instance}_ep0002.telemetry.gz",
    ]


@pytest.mark.parametrize("scenario", TELEMETRY_SCENARIOS)
def test_probed_decoded_fields(scenario):
    meta = load_telemetry_meta(scenario)
    files = iter_episode_files(telemetry_dir(scenario))
    ep_records = {i + 1: records_for_episode(p) for i, p in enumerate(files)}

    for probe in meta["probed_steps"]:
        ep = probe["episode"]
        expected = probe["expected"]
        row_idx = probe["step"]
        record = ep_records[ep][row_idx]
        for key, val in expected.items():
            if key == "hp_frac":
                assert abs(record[key] - val) < 1e-5, f"{scenario} ep{ep} step {row_idx} {key}"
            else:
                assert record[key] == val, f"{scenario} ep{ep} step {row_idx} {key}"


@pytest.mark.parametrize("scenario", TELEMETRY_SCENARIOS)
def test_snapshot_scorer_contract(scenario):
    meta = load_telemetry_meta(scenario)
    baseline = load_baseline(meta["baseline"])
    files = iter_episode_files(telemetry_dir(scenario))

    all_telemetry_snaps = []
    for path in files:
        snaps = [r["snapshot"] for r in records_for_episode(path)]
        assert all(len(s) == SNAPSHOT_SIZE for s in snaps)
        all_telemetry_snaps.extend(snaps)
    score_all = score_snapshots(all_telemetry_snaps, baseline)

    independent_snaps = [
        bytes.fromhex(p["snapshot_b64"]) for p in meta["probed_snapshots"]
    ]
    score_probed = score_snapshots(independent_snaps, baseline)
    assert score_all.score >= score_probed.score
    assert set(score_all.components.keys()) == set(score_probed.components.keys())


@pytest.mark.parametrize("scenario", TELEMETRY_SCENARIOS)
def test_scorer_parity_on_probed_snapshots(scenario):
    meta = load_telemetry_meta(scenario)
    baseline = load_baseline(meta["baseline"])
    files = iter_episode_files(telemetry_dir(scenario))
    ep_records = {i + 1: records_for_episode(p) for i, p in enumerate(files)}

    step_by_global = {p["global_step"]: p for p in meta["probed_steps"]}
    for probe in meta["probed_snapshots"]:
        ep = probe["episode"]
        step_idx = step_by_global[probe["global_step"]]["step"]
        snap_from_file = ep_records[ep][step_idx]["snapshot"]
        snap_independent = bytes.fromhex(probe["snapshot_b64"])
        assert snap_from_file == snap_independent
        score_file = score_snapshots([snap_from_file], baseline)
        score_ind = score_snapshots([snap_independent], baseline)
        assert score_file.score == score_ind.score
        assert score_file.components == score_ind.components


def test_reader_tolerates_truncated_final_chunk():
    scenario = FIXTURES_DIR / "telemetry_init"
    src = iter_episode_files(scenario / "telemetry")[0]
    with gzip.open(src, "rb") as f:
        payload = f.read()
    truncated = payload[: len(payload) - 8]

    with tempfile.NamedTemporaryFile(suffix=".telemetry.gz", delete=False) as tmp:
        trunc_path = Path(tmp.name)
    with gzip.open(trunc_path, "wb") as f:
        f.write(truncated)

    meta = read_episode_metadata(trunc_path)
    assert meta["schema_version"]
    records = records_for_episode(trunc_path)
    full_records = records_for_episode(src)
    assert len(records) == len(full_records) - 1
    if records:
        last = records[-1]
        assert "snapshot" in last
        assert len(last["snapshot"]) == SNAPSHOT_SIZE
    trunc_path.unlink()


def test_episode_metadata_header(scenario=TELEMETRY_SCENARIOS[0]):
    meta = load_telemetry_meta(scenario)
    path = iter_episode_files(telemetry_dir(scenario))[0]
    header = read_episode_metadata(path)
    assert header["instance_id"] == meta["instance_id"]
    assert header["episode"] == 1
    assert header["snapshot_size"] == SNAPSHOT_SIZE
    assert "step" in header["columns"]
    assert "ptype_5" in header["columns"]
