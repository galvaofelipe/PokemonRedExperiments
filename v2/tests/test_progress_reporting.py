"""Extend-era progress reporting: --target-steps targets, lineage run dirs,
and leg-clock SPS rates (ticket 19 follow-ups)."""

import csv
import time

import watch_progress
from resource_callback import ResourceCallback
from watch_progress import job_session, planned_steps


def test_planned_steps_reads_target_steps():
    amap = watch_progress.arg_map(
        ["--extend", "t16_acc64_s0", "--target-steps", "19005440", "--no-stream"]
    )
    assert planned_steps(amap) == 19005440


def test_planned_steps_total_timesteps_still_works():
    amap = watch_progress.arg_map(["--total-timesteps", "12345"])
    assert planned_steps(amap) == 12345


def test_job_session_derives_lineage_dir_from_extend():
    amap = watch_progress.arg_map(["--extend", "t16_acc64_s0", "--target-steps", "1"])
    assert job_session(amap) == "runs_t16_acc64_s0"


def test_job_session_strips_runs_prefix():
    amap = watch_progress.arg_map(["--extend", "runs_t16_acc64_s0"])
    assert job_session(amap) == "runs_t16_acc64_s0"


def test_job_session_explicit_session_path_wins():
    amap = watch_progress.arg_map(["--session-path", "runs_custom", "--extend", "t16_x"])
    assert job_session(amap) == "runs_custom"


def test_job_session_no_extend_stays_empty():
    assert job_session(watch_progress.arg_map(["--no-stream"])) == ""


class _FakeModel:
    num_timesteps = 0
    logger = None


def _sampled_row(cb):
    cb._write_row_unsafe()
    with cb.log_path.open() as f:
        return list(csv.DictReader(f))[-1]


def test_resource_callback_rates_use_leg_clock(tmp_path):
    cb = ResourceCallback(tmp_path, num_envs=8, action_freq=24, interval_s=999)
    cb.model = _FakeModel()
    base = 10_944_512
    cb.start_steps = base
    cb.last_steps = base
    cb.t0 = time.monotonic() - 100.0  # 100 s of leg wall time
    cb.last_t = time.monotonic() - 5.0
    cb.log_path.parent.mkdir(exist_ok=True)
    cb.log_path.write_text(
        "wall_s,timesteps,instant_sps,avg_sps,game_s,per_env_game_s,"
        "per_env_speedup,rss_mb,footprint_mb,cpu_pct,n_procs\n"
    )
    cb.model.num_timesteps = base + 50_000  # 50k leg steps in 100 s -> 500 SPS

    row = _sampled_row(cb)
    assert abs(float(row["avg_sps"]) - 500.0) < 50.0
    # Global clock would have reported ~110k SPS; make sure we did not.
    assert float(row["avg_sps"]) < 1000.0
    assert abs(float(row["instant_sps"]) - 10_000.0) < 1000.0
    # timesteps column stays on the global lineage clock.
    assert int(row["timesteps"]) == base + 50_000
