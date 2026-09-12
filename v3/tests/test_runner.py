import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

V3_DIR = Path(__file__).resolve().parents[1]
BIN_DIR = V3_DIR / "bin"
sys.path.insert(0, str(BIN_DIR))

import frozen_manifest  # noqa: E402
import runner  # noqa: E402


def _manifest_ok():
    return frozen_manifest.VerifyResult(ok=True)


def _minimal_config(tmp: Path) -> runner.RunnerConfig:
    jobs = tmp / "jobs"
    for sub in ("queued", "running", "done", "failed"):
        (jobs / sub).mkdir(parents=True)
    ratchet_scratch = tmp / "ratchet"
    ratchet_scratch.mkdir()
    return runner.RunnerConfig(
        queued_dir=jobs / "queued",
        running_dir=jobs / "running",
        done_dir=jobs / "done",
        failed_dir=jobs / "failed",
        lockfile=jobs / ".runner.lock",
        runs_dir=tmp / "runs",
        default_num_envs=6,
        status_refresh_seconds=0.01,
        train_log="train.log",
        eval_log="eval.log",
        ledger_path=str(ratchet_scratch / "ledger.tsv"),
        milestones_path=str(ratchet_scratch / "milestones.jsonl"),
        champion_json=str(ratchet_scratch / "champion.json"),
        champion_dir=str(ratchet_scratch / "champion"),
    )


def _sample_scorecard() -> dict:
    return {
        "scorecard_version": "1.1.0",
        "score_version": "1.0.0",
        "eval_suite_version": "1.0.0",
        "commit": "abc123",
        "score": {"mean": 1.0, "max": 1.0},
        "components_mean": {
            "badges": 0.0,
            "events": 0.0,
            "dex_caught": 0.0,
            "dex_seen": 0.0,
            "unique_maps": 1.0,
            "level_sum_capped": 0.0,
        },
        "init_states": [{"name": "fresh_game", "file": "x.state", "sha256": "abc"}],
        "splits": {"achieved": []},
    }


def _ledger_rows(cfg: runner.RunnerConfig) -> list[dict]:
    import csv

    path = Path(cfg.ledger_path)
    if not path.is_file():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _valid_job(**overrides):
    data = {
        "name": "smoke01",
        "run_type": "cadence",
        "budget": {"total_timesteps": 8192},
        "num_envs": 6,
        "seed": 0,
        "init_state": "../init.state",
        "warm_start_from": None,
        "eval": {"enabled": True},
    }
    data.update(overrides)
    return data


def test_validate_job_accepts_cadence():
    cfg = _minimal_config(Path(tempfile.mkdtemp()))
    job = runner.validate_job(_valid_job(), cfg)
    assert job.name == "smoke01"
    assert job.run_type == "cadence"
    assert job.eval.enabled is True


def test_validate_job_rejects_bad_run_type():
    cfg = _minimal_config(Path(tempfile.mkdtemp()))
    with pytest.raises(runner.JobValidationError, match="run_type"):
        runner.validate_job(_valid_job(run_type="sprint"), cfg)


def test_validate_job_budget_xor():
    cfg = _minimal_config(Path(tempfile.mkdtemp()))
    with pytest.raises(runner.JobValidationError, match="exactly one"):
        runner.validate_job(_valid_job(budget={}), cfg)
    with pytest.raises(runner.JobValidationError, match="exactly one"):
        runner.validate_job(
            _valid_job(budget={"total_timesteps": 100, "minutes": 1}),
            cfg,
        )


def test_validate_job_tag_description():
    cfg = _minimal_config(Path(tempfile.mkdtemp()))
    job = runner.validate_job(_valid_job(tag="exp-a", description="try entropy"), cfg)
    assert job.tag == "exp-a"
    assert job.description == "try entropy"
    job2 = runner.validate_job(_valid_job(), cfg)
    assert job2.tag == ""
    assert job2.description == ""


def test_probe_defaults_eval_disabled():
    cfg = _minimal_config(Path(tempfile.mkdtemp()))
    job = runner.validate_job(
        _valid_job(run_type="probe", eval={}),
        cfg,
    )
    assert job.eval.enabled is False


def test_cadence_defaults_eval_enabled():
    cfg = _minimal_config(Path(tempfile.mkdtemp()))
    job = runner.validate_job(_valid_job(eval={}), cfg)
    assert job.eval.enabled is True


def test_planned_timesteps_minutes():
    cfg = _minimal_config(Path(tempfile.mkdtemp()))
    job = runner.validate_job(
        _valid_job(budget={"minutes": 1.0}, num_envs=6),
        cfg,
    )
    assert runner.planned_timesteps(job) == int(1.0 * 60 * 6 * runner.SPS_PER_ENV)


def test_compute_save_freq_tiny_budget():
    assert runner.compute_save_freq(100, 2048 * 80) == 100
    default = (2048 * 80) // 2
    assert runner.compute_save_freq(50000, 2048 * 80) == 50000
    assert runner.compute_save_freq(200000, 2048 * 80) == default


def test_latest_checkpoint_steps(tmp_path):
    (tmp_path / "poke_100_steps.zip").write_bytes(b"x")
    (tmp_path / "poke_4096_steps.zip").write_bytes(b"x")
    (tmp_path / "poke_2000_steps.zip").write_bytes(b"x")
    assert runner.latest_checkpoint_steps(tmp_path) == 4096
    assert runner.latest_checkpoint_path(tmp_path).name == "poke_4096_steps.zip"


def test_dirty_tree_allows_v2_only():
    with patch.object(
        runner.subprocess,
        "check_output",
        return_value=" M v2/foo.py\n",
    ):
        assert runner.dirty_tracked_paths() == []


def test_dirty_tree_rejects_v3():
    with patch.object(
        runner.subprocess,
        "check_output",
        return_value=" M v3/train.py\n",
    ):
        dirty = runner.dirty_tracked_paths()
        assert dirty == ["v3/train.py"]


def test_claim_atomic_rename(tmp_path):
    cfg = _minimal_config(tmp_path)
    job_path = cfg.queued_dir / "job.json"
    job_path.write_text("{}")
    claimed = runner.claim_job(job_path, cfg.running_dir, hostname="testhost")
    assert claimed.name == "testhost-job.json"
    assert claimed.exists()
    assert not job_path.exists()


def test_atomic_write_json_retries(tmp_path):
    target = tmp_path / "out.json"
    original_replace = Path.replace
    calls = {"n": 0}

    def flaky_replace(self, other):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated failure")
        return original_replace(self, other)

    with patch.object(Path, "replace", flaky_replace):
        runner.atomic_write_json(target, {"ok": True}, retries=3, backoff=0.001)
    assert target.exists()
    assert json.loads(target.read_text()) == {"ok": True}


def test_build_train_cmd_includes_save_freq():
    cfg = _minimal_config(Path(tempfile.mkdtemp()))
    job = runner.validate_job(_valid_job(budget={"total_timesteps": 100}), cfg)
    cmd = runner.build_train_cmd(job, Path("/tmp/run"), 100)
    assert "--save-freq" in cmd
    assert "--no-stream" in cmd


def test_build_eval_cmd_passthrough():
    cfg = _minimal_config(Path(tempfile.mkdtemp()))
    job = runner.validate_job(
        _valid_job(
            eval={
                "enabled": True,
                "max_steps": 512,
                "state_filter": "fresh_game",
                "seed_filter": 0,
            }
        ),
        cfg,
    )
    cmd = runner.build_eval_cmd(job, Path("/tmp/run"), Path("/tmp/run/poke_100_steps.zip"))
    assert "--max-steps" in cmd
    assert "--state-filter" in cmd
    assert "--seed-filter" in cmd


@patch.object(runner, "verify_frozen_manifest", return_value=_manifest_ok())
@patch.object(runner, "dirty_tracked_paths", return_value=[])
@patch.object(runner, "git_head_commit", return_value="abc123")
@patch.object(runner, "run_train")
@patch.object(runner, "run_eval")
def test_status_transition_done(mock_run_eval, mock_run_train, _git, _dirty, _manifest, tmp_path):
    cfg = _minimal_config(tmp_path)
    cfg.runs_dir.mkdir(parents=True, exist_ok=True)

    job_data = _valid_job(
        budget={"total_timesteps": 100},
        eval={"enabled": True, "max_steps": 64, "state_filter": "fresh_game", "seed_filter": 0},
    )
    claimed = cfg.running_dir / "host-smoke01.json"
    claimed.write_text(json.dumps(job_data))

    train_proc = MagicMock()
    train_proc.poll.side_effect = [None, 0]
    train_proc.returncode = 0
    mock_run_train.return_value = train_proc

    eval_proc = MagicMock()
    eval_proc.poll.side_effect = [0]
    eval_proc.returncode = 0
    mock_run_eval.return_value = eval_proc

    def fake_train(config, ctx, python=None):
        (ctx.run_dir / "poke_100_steps.zip").write_bytes(b"zip")
        (ctx.run_dir / "train.log").write_text("train ok\n")
        return train_proc

    def fake_eval(config, ctx, checkpoint, python=None):
        (ctx.run_dir / "scorecard.json").write_text(json.dumps(_sample_scorecard()))
        (ctx.run_dir / "eval.log").write_text("eval ok\n")
        return eval_proc

    mock_run_train.side_effect = fake_train
    mock_run_eval.side_effect = fake_eval

    runner.process_job(cfg, claimed)

    assert list(cfg.done_dir.glob("*.json"))
    assert not claimed.exists()
    meta_files = list(cfg.runs_dir.glob("smoke01_*/run_metadata.json"))
    assert meta_files
    meta = json.loads(meta_files[0].read_text())
    assert meta["status"] == "done"
    assert meta["commit"] == "abc123"
    rows = _ledger_rows(cfg)
    assert len(rows) == 1
    assert rows[0]["commit"] == "abc123"
    assert rows[0]["status"] == "keep"


@patch.object(runner, "verify_frozen_manifest", return_value=_manifest_ok())
@patch.object(runner, "dirty_tracked_paths", return_value=[])
@patch.object(runner, "git_head_commit", return_value="abc123")
@patch.object(runner, "run_train")
def test_train_crash_goes_failed(mock_run_train, _git, _dirty, _manifest, tmp_path):
    cfg = _minimal_config(tmp_path)
    job_data = _valid_job(budget={"total_timesteps": 100}, eval={"enabled": False})
    claimed = cfg.running_dir / "host-crash.json"
    claimed.write_text(json.dumps(job_data))

    train_proc = MagicMock()
    train_proc.poll.side_effect = [0]
    train_proc.returncode = 1
    mock_run_train.return_value = train_proc

    runner.process_job(cfg, claimed)

    assert list(cfg.failed_dir.glob("*.json"))
    assert (cfg.failed_dir / "host-crash.reason.txt").exists()
    rows = _ledger_rows(cfg)
    assert len(rows) == 1
    assert rows[0]["status"] == "crash"


@patch.object(runner, "verify_frozen_manifest", return_value=_manifest_ok())
@patch.object(runner, "dirty_tracked_paths", return_value=[])
@patch.object(runner, "git_head_commit", return_value="abc123")
@patch.object(runner, "run_train")
@patch.object(runner, "run_eval")
def test_eval_skipped_for_probe(mock_run_eval, mock_run_train, _git, _dirty, _manifest, tmp_path):
    cfg = _minimal_config(tmp_path)
    job_data = _valid_job(run_type="probe", eval={})
    claimed = cfg.running_dir / "host-probe.json"
    claimed.write_text(json.dumps(job_data))

    train_proc = MagicMock()
    train_proc.poll.side_effect = [0]
    train_proc.returncode = 0
    mock_run_train.return_value = train_proc

    runner.process_job(cfg, claimed)

    mock_run_eval.assert_not_called()
    assert list(cfg.done_dir.glob("*.json"))
    rows = _ledger_rows(cfg)
    assert len(rows) == 1
    assert rows[0]["status"] == "no-eval"


@patch.object(runner, "verify_frozen_manifest", return_value=_manifest_ok())
@patch.object(runner, "dirty_tracked_paths", return_value=[])
@patch.object(runner, "git_head_commit", return_value="abc123")
@patch.object(runner, "run_train")
def test_no_checkpoint_eval_enabled_fails(mock_run_train, _git, _dirty, _manifest, tmp_path):
    cfg = _minimal_config(tmp_path)
    job_data = _valid_job(budget={"total_timesteps": 100}, eval={"enabled": True})
    claimed = cfg.running_dir / "host-nozip.json"
    claimed.write_text(json.dumps(job_data))

    train_proc = MagicMock()
    train_proc.poll.side_effect = [0]
    train_proc.returncode = 0
    mock_run_train.return_value = train_proc

    runner.process_job(cfg, claimed)

    assert list(cfg.failed_dir.glob("*.json"))
    reason = (cfg.failed_dir / "host-nozip.reason.txt").read_text()
    assert "checkpoint" in reason.lower()


@patch.object(runner, "verify_frozen_manifest", return_value=_manifest_ok())
@patch.object(runner, "dirty_tracked_paths", return_value=[])
def test_process_job_fails_on_manifest_mismatch(_dirty, _manifest, tmp_path):
    cfg = _minimal_config(tmp_path)
    job_data = _valid_job(budget={"total_timesteps": 100}, eval={"enabled": False})
    claimed = cfg.running_dir / "host-manifest.json"
    claimed.write_text(json.dumps(job_data))

    bad = frozen_manifest.VerifyResult(
        ok=False,
        hash_mismatches=["v3/frozen/ram_map.py"],
    )
    with patch.object(runner, "verify_frozen_manifest", return_value=bad):
        runner.process_job(cfg, claimed)

    assert list(cfg.failed_dir.glob("*.json"))
    reason = (cfg.failed_dir / "host-manifest.reason.txt").read_text()
    assert "frozen manifest mismatch" in reason
    assert "v3/frozen/ram_map.py" in reason
    assert not list(cfg.runs_dir.glob("*"))


def test_invalid_job_goes_failed(tmp_path):
    cfg = _minimal_config(tmp_path)
    claimed = cfg.running_dir / "host-bad.json"
    claimed.write_text("{not json")

    runner.process_job(cfg, claimed)

    assert list(cfg.failed_dir.glob("*.json"))
    assert (cfg.failed_dir / "host-bad.reason.txt").exists()
    assert _ledger_rows(cfg) == []


@patch.object(runner, "verify_frozen_manifest", return_value=_manifest_ok())
@patch.object(runner, "dirty_tracked_paths", return_value=[])
def test_pre_run_failure_no_ledger(_dirty, _manifest, tmp_path):
    cfg = _minimal_config(tmp_path)
    job_data = _valid_job(budget={"total_timesteps": 100}, eval={"enabled": False})
    claimed = cfg.running_dir / "host-manifest.json"
    claimed.write_text(json.dumps(job_data))

    bad = frozen_manifest.VerifyResult(
        ok=False,
        hash_mismatches=["v3/frozen/ram_map.py"],
    )
    with patch.object(runner, "verify_frozen_manifest", return_value=bad):
        runner.process_job(cfg, claimed)

    assert _ledger_rows(cfg) == []


def test_build_status_eta(tmp_path):
    cfg = _minimal_config(tmp_path)
    job = runner.validate_job(_valid_job(), cfg)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "poke_5000_steps.zip").write_bytes(b"z")
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ctx = runner.RunContext(
        job=job,
        run_dir=run_dir,
        claimed_path=Path("x.json"),
        started_at=started,
        planned_timesteps=10000,
        commit="abc",
        hostname="h",
    )
    now = datetime(2026, 1, 1, 0, 0, 10, tzinfo=timezone.utc)
    status = runner.build_status(ctx, "training", now=now)
    assert status["actual_timesteps"] == 5000
    assert status["observed_sps"] == 500.0
    assert status["eta_s"] == 10.0
