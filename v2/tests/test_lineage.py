"""Ticket 19: pure-logic tests for the lineage machinery (sidecars, checkpoint
selection, share-fallback resolution, contradiction detection, ledger) plus
validation of the 030-038 campaign specs through the real CLI parser."""

import json
import os
from pathlib import Path

import pytest

from lineage import (
    append_ledger,
    check_contradictions,
    explicit_flag_dests,
    local_lineage_dir,
    normalize_lineage,
    read_sidecars,
    resolve_extend,
    resolve_physical_cap,
    select_sidecar,
    write_sidecar,
)

INFO = {
    "lineage": "x_test",
    "num_envs": 64,
    "n_steps": 2560,
    "accumulation_rounds": 8,
    "seed": 0,
    "env_config": {"max_steps": 16384, "action_freq": 24, "seed_note": "paths are strings", "init_state": "../init.state"},
    "parent": None,
}


def make_checkpoint(dirpath: Path, step: int, **info_overrides):
    """Write a fake zip + sidecar pair; returns the sidecar dict."""
    info = {**INFO, **info_overrides}
    (dirpath / f"poke_{step}_steps.zip").write_bytes(b"fake-zip")
    return write_sidecar(dirpath / f"poke_{step}_steps.json", step, info)


def test_sidecar_round_trip(tmp_path):
    written = make_checkpoint(tmp_path, 1_966_080)
    (read,) = read_sidecars(tmp_path)
    assert read["lineage"] == "x_test"
    assert read["global_step"] == 1_966_080
    assert read["num_envs"] == 64 and read["n_steps"] == 2560
    assert read["accumulation_rounds"] == 8
    assert read["seed"] == 0
    assert read["parent"] is None
    assert read["hostname"] and read["saved_at"]
    assert read["env_config"] == INFO["env_config"]
    assert written["global_step"] == read["global_step"]


def test_sidecar_skips_garbage(tmp_path):
    (tmp_path / "poke_5_steps.json").write_text("{not json")
    make_checkpoint(tmp_path, 10)
    (read,) = read_sidecars(tmp_path)
    assert read["global_step"] == 10


def test_select_newest_and_from_step(tmp_path):
    for step in (100, 200, 300):
        make_checkpoint(tmp_path, step)
    cands = read_sidecars(tmp_path)
    assert select_sidecar(cands)["global_step"] == 300
    assert select_sidecar(cands, from_step=250)["global_step"] == 200
    assert select_sidecar(cands, from_step=300)["global_step"] == 300
    assert select_sidecar(cands, from_step=50) is None
    assert select_sidecar([]) is None


def test_select_overshoot_zip(tmp_path):
    # runs_t05_g20480_s0 case: correct resume point 1,966,080 plus an
    # overshoot zip at 2,097,152 from the same leg.
    make_checkpoint(tmp_path, 1_966_080)
    make_checkpoint(tmp_path, 2_097_152)
    cands = read_sidecars(tmp_path)
    assert select_sidecar(cands, from_step=1_966_080)["global_step"] == 1_966_080
    assert select_sidecar(cands)["global_step"] == 2_097_152


def test_normalize_and_dirs():
    assert normalize_lineage("t16_acc64_s0") == "t16_acc64_s0"
    assert normalize_lineage("runs_t16_acc64_s0") == "t16_acc64_s0"
    assert normalize_lineage("runs_t16_acc64_s0/") == "t16_acc64_s0"
    assert local_lineage_dir("t16_acc64_s0") == Path("runs_t16_acc64_s0")


def test_resolve_extend_local(tmp_path):
    sess = tmp_path / "runs_x_test"
    sess.mkdir()
    make_checkpoint(sess, 100)
    make_checkpoint(sess, 200)
    got_sess, stem, sidecar = resolve_extend("x_test", cwd=tmp_path, pokered_data=None)
    assert got_sess == sess
    assert stem == str(sess / "poke_200_steps")
    assert sidecar["global_step"] == 200


def test_resolve_extend_requires_zip(tmp_path):
    sess = tmp_path / "runs_x_test"
    sess.mkdir()
    sc = make_checkpoint(sess, 100)
    (sess / "poke_100_steps.zip").unlink()  # sidecar without zip is unusable
    with pytest.raises(SystemExit):
        resolve_extend("x_test", cwd=tmp_path, pokered_data=None)
    del sc


def test_resolve_extend_share_fallback(tmp_path, monkeypatch):
    share_root = tmp_path / "share"
    share_sess = share_root / "pokered" / "runs" / "v2" / "x_test"
    (share_sess / "poke_ppo_1").mkdir(parents=True)
    make_checkpoint(share_sess, 1_966_080)
    make_checkpoint(share_sess, 2_097_152)
    (share_sess / "poke_ppo_1" / "events.out.tfevents.1.host").write_bytes(b"tb")

    got_sess, stem, sidecar = resolve_extend(
        "x_test", from_step=1_966_080, cwd=tmp_path, pokered_data=str(share_root)
    )
    assert got_sess == tmp_path / "runs_x_test"
    assert sidecar["global_step"] == 1_966_080
    # zip + pinned sidecar + tfevents were copied down
    assert (got_sess / "poke_1966080_steps.zip").exists()
    assert (got_sess / "poke_1966080_steps.json").exists()
    assert (got_sess / "poke_ppo_1" / "events.out.tfevents.1.host").exists()
    assert not (got_sess / "poke_2097152_steps.zip").exists()  # only the selected checkpoint
    assert Path(stem + ".zip").exists()


def test_resolve_extend_hard_fail(tmp_path):
    with pytest.raises(SystemExit, match="Refusing to start a fresh run"):
        resolve_extend("ghost", cwd=tmp_path, pokered_data=None)
    with pytest.raises(SystemExit, match="Refusing to start a fresh run"):
        resolve_extend("ghost", cwd=tmp_path, pokered_data=str(tmp_path / "nope"))
    # sidecars exist but all beyond from_step
    sess = tmp_path / "runs_x_test"
    sess.mkdir()
    make_checkpoint(sess, 500)
    with pytest.raises(SystemExit, match="Refusing to start a fresh run"):
        resolve_extend("x_test", from_step=100, cwd=tmp_path, pokered_data=None)


class FakeArgs:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __getattr__(self, name):
        return None


def test_contradiction_detection():
    sidecar = {
        "lineage": "x_test",
        "num_envs": 64,
        "n_steps": 2560,
        "seed": 0,
        "env_config": {"max_steps": 16384, "reward_scale": 0.5},
    }
    # explicit contradicting --n-steps -> error naming both values
    errors = check_contradictions(FakeArgs(n_steps=128), {"n_steps"}, sidecar)
    assert len(errors) == 1 and "--n-steps=128" in errors[0] and "2560" in errors[0]
    # explicit but matching -> fine
    assert check_contradictions(FakeArgs(n_steps=2560), {"n_steps"}, sidecar) == []
    # not explicit -> sidecar wins silently (no error)
    assert check_contradictions(FakeArgs(n_steps=128), set(), sidecar) == []
    # env_config-backed flag contradiction
    errors = check_contradictions(FakeArgs(reward_scale=1.0), {"reward_scale"}, sidecar)
    assert len(errors) == 1 and "reward_scale" in errors[0]


def test_physical_cap_resolution():
    assert resolve_physical_cap(4, None, 64, hostname="whatever") == 4  # flag wins
    assert resolve_physical_cap(None, "12", 64, hostname="win-p2kh1a2oie9") == 12  # env beats host map
    assert resolve_physical_cap(None, None, 64, hostname="WIN-P2KH1A2OIE9") == 16  # AM18
    assert resolve_physical_cap(None, "", 64, hostname="mac-mini") == 8
    # never exceeds logical envs
    assert resolve_physical_cap(None, None, 2, hostname="mac-mini") == 2
    assert resolve_physical_cap(32, None, 8, hostname="mac-mini") == 8
    # unknown host: min(logical, cpu_count)
    assert resolve_physical_cap(None, None, 2, hostname="strange-host") == 2
    assert resolve_physical_cap(None, None, 10**9, hostname="strange-host") == (os.cpu_count() or 1)


def test_ledger_append(tmp_path):
    path = tmp_path / "lineage.jsonl"
    e1 = {"name": "a", "lineage": "a", "parent": None, "status": "completed"}
    e2 = {"name": "a", "lineage": "a", "parent": {"lineage": "a", "step": 100}, "status": "failed"}
    append_ledger(e1, path)
    append_ledger(e2, path)
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["parent"] is None
    assert json.loads(lines[1])["parent"] == {"lineage": "a", "step": 100}
    assert json.loads(lines[1])["status"] == "failed"


def test_campaign_specs_parse_and_order():
    """The 9 campaign specs (030-038) must replay through the real argparse of
    baseline_fast_v2.py, sort into 19M < 27M < 35M execution order under
    LC_ALL=C, and use mega-update-aligned absolute targets."""
    from baseline_fast_v2 import build_parser, parse_args  # deferred: pulls pyboy

    jobs_dir = Path(__file__).resolve().parents[1] / "jobs"
    spec_paths = sorted(jobs_dir.glob("03[0-8]_*.json"))
    assert len(spec_paths) == 9, f"expected 9 campaign specs, got {[p.name for p in spec_paths]}"

    targets = []
    for path in spec_paths:
        spec = json.loads(path.read_text())
        assert set(spec) == {"name", "args"}
        args = parse_args(spec["args"])  # real parser, no SystemExit
        assert args.extend in {"t16_acc64_s0", "t16_g20480_s0", "t16_g2560_s0"}
        assert args.target_steps % 163_840 == 0
        assert args.target_steps % 20_480 == 0
        assert args.stream is False
        targets.append(args.target_steps)
        explicit = explicit_flag_dests(build_parser(), spec["args"])
        # declarative: no frozen-fact flags (geometry/seed/env_config) — the
        # sidecar owns them
        assert not (explicit & {"num_envs", "n_steps", "seed", "max_steps"})

    assert sorted(targets) == targets, "LC_ALL=C filename order must be execution order (19M, 27M, 35M)"
    assert targets == sorted(targets) and len(set(targets)) == 3
