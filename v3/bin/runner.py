#!/usr/bin/env python3
"""Host-side v3 job runner (Human-owned).

Drains v3/jobs/queued/ one job at a time: train → eval → Scorecard.
Neither Frozen nor Editable — lives outside the agent sandbox.

Job JSON schema (required):
  name, run_type (cadence|marathon|probe), budget ({total_timesteps}|{minutes}),
  num_envs, seed, init_state, warm_start_from (null|checkpoint path without .zip),
  eval.enabled (bool; default false for probe, true for cadence/marathon).

Optional fields:
  max_steps — train episode cap (train.py default if omitted)
  tag, description — recorded verbatim in the Ledger (default "")
  eval.max_steps, eval.state_filter, eval.seed_filter, eval.suite_path
    — forwarded to frozen.eval; absent keys use frozen suite defaults.

Recovery: if the runner crashes mid-job, a claimed file may remain in
jobs/running/. Move it back to queued/ or to failed/ manually before restarting.

v2/ is never read or written.
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from frozen_manifest import verify as verify_frozen_manifest
import ratchet

# Keep in sync with v3/train.py
SPS_PER_ENV = 90

_CHECKPOINT_RE = re.compile(r"^poke_(\d+)_steps\.zip$")
_RUN_TYPES = frozenset({"cadence", "marathon", "probe"})
_NAME_RE = re.compile(r"^[\w.-]+$")

V3_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = V3_ROOT.parent
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "runner_config.json"


class JobValidationError(ValueError):
    pass


@dataclass
class EvalConfig:
    enabled: bool
    max_steps: int | None = None
    state_filter: str | None = None
    seed_filter: int | None = None
    suite_path: str | None = None


@dataclass
class Job:
    name: str
    run_type: str
    budget: dict[str, Any]
    num_envs: int
    seed: int
    init_state: str
    warm_start_from: str | None
    max_steps: int | None
    eval: EvalConfig
    tag: str
    description: str
    raw: dict[str, Any] = field(repr=False)


@dataclass
class RunnerConfig:
    queued_dir: Path
    running_dir: Path
    done_dir: Path
    failed_dir: Path
    lockfile: Path
    runs_dir: Path
    default_num_envs: int
    status_refresh_seconds: float
    train_log: str
    eval_log: str
    ledger_path: str
    milestones_path: str
    champion_json: str
    champion_dir: str


@dataclass
class RunContext:
    job: Job
    run_dir: Path
    claimed_path: Path
    started_at: datetime
    planned_timesteps: int
    commit: str
    hostname: str
    train_ended_at: datetime | None = None


_lock_path: Path | None = None


def load_config(config_path: Path | None = None, v3_root: Path = V3_ROOT) -> RunnerConfig:
    path = config_path or DEFAULT_CONFIG_PATH
    data = json.loads(path.read_text())
    queue = data["queue"]
    return RunnerConfig(
        queued_dir=v3_root / queue["queued_dir"],
        running_dir=v3_root / queue["running_dir"],
        done_dir=v3_root / queue["done_dir"],
        failed_dir=v3_root / queue["failed_dir"],
        lockfile=v3_root / queue["lockfile"],
        runs_dir=v3_root / data["runs_dir"],
        default_num_envs=int(data["default_num_envs"]),
        status_refresh_seconds=float(data["status_refresh_seconds"]),
        train_log=str(data["train_log"]),
        eval_log=str(data["eval_log"]),
        ledger_path=str(data["ledger_path"]),
        milestones_path=str(data["milestones_path"]),
        champion_json=str(data["champion_json"]),
        champion_dir=str(data["champion_dir"]),
    )


def validate_job(data: dict[str, Any], config: RunnerConfig) -> Job:
    if not isinstance(data, dict):
        raise JobValidationError("job must be a JSON object")

    name = data.get("name")
    if not name or not isinstance(name, str) or not _NAME_RE.match(name):
        raise JobValidationError("name must be a non-empty safe token")

    run_type = data.get("run_type")
    if run_type not in _RUN_TYPES:
        raise JobValidationError(f"run_type must be one of {sorted(_RUN_TYPES)}")

    budget = data.get("budget")
    if not isinstance(budget, dict):
        raise JobValidationError("budget must be an object")
    has_ts = "total_timesteps" in budget
    has_min = "minutes" in budget
    if has_ts == has_min:
        raise JobValidationError("budget must have exactly one of total_timesteps or minutes")
    if has_ts:
        ts = budget["total_timesteps"]
        if not isinstance(ts, int) or ts <= 0:
            raise JobValidationError("budget.total_timesteps must be a positive int")
    if has_min:
        mins = budget["minutes"]
        if not isinstance(mins, (int, float)) or mins <= 0:
            raise JobValidationError("budget.minutes must be a positive number")

    num_envs = data.get("num_envs", config.default_num_envs)
    if not isinstance(num_envs, int) or num_envs <= 0:
        raise JobValidationError("num_envs must be a positive int")

    seed = data.get("seed")
    if not isinstance(seed, int):
        raise JobValidationError("seed must be an int")

    init_state = data.get("init_state")
    if not init_state or not isinstance(init_state, str):
        raise JobValidationError("init_state must be a non-empty string")

    warm_start = data.get("warm_start_from")
    if warm_start is not None and not isinstance(warm_start, str):
        raise JobValidationError("warm_start_from must be null or a string path")

    max_steps = data.get("max_steps")
    if max_steps is not None:
        if not isinstance(max_steps, int) or max_steps <= 0:
            raise JobValidationError("max_steps must be a positive int")

    eval_raw = data.get("eval", {})
    if eval_raw is None:
        eval_raw = {}
    if not isinstance(eval_raw, dict):
        raise JobValidationError("eval must be an object")

    if "enabled" in eval_raw:
        eval_enabled = eval_raw["enabled"]
        if not isinstance(eval_enabled, bool):
            raise JobValidationError("eval.enabled must be a bool")
    else:
        eval_enabled = run_type != "probe"

    eval_max_steps = eval_raw.get("max_steps")
    if eval_max_steps is not None and (not isinstance(eval_max_steps, int) or eval_max_steps <= 0):
        raise JobValidationError("eval.max_steps must be a positive int")

    state_filter = eval_raw.get("state_filter")
    if state_filter is not None and not isinstance(state_filter, str):
        raise JobValidationError("eval.state_filter must be a string")

    seed_filter = eval_raw.get("seed_filter")
    if seed_filter is not None and not isinstance(seed_filter, int):
        raise JobValidationError("eval.seed_filter must be an int")

    suite_path = eval_raw.get("suite_path")
    if suite_path is not None and not isinstance(suite_path, str):
        raise JobValidationError("eval.suite_path must be a string")

    eval_cfg = EvalConfig(
        enabled=eval_enabled,
        max_steps=eval_max_steps,
        state_filter=state_filter,
        seed_filter=seed_filter,
        suite_path=suite_path,
    )

    tag = data.get("tag", "")
    if tag is None or not isinstance(tag, str):
        raise JobValidationError("tag must be a string")

    description = data.get("description", "")
    if description is None or not isinstance(description, str):
        raise JobValidationError("description must be a string")

    return Job(
        name=name,
        run_type=run_type,
        budget=budget,
        num_envs=num_envs,
        seed=seed,
        init_state=init_state,
        warm_start_from=warm_start,
        max_steps=max_steps,
        eval=eval_cfg,
        tag=tag,
        description=description,
        raw=data,
    )


def planned_timesteps(job: Job) -> int:
    if "total_timesteps" in job.budget:
        return int(job.budget["total_timesteps"])
    sps = job.num_envs * SPS_PER_ENV
    return int(job.budget["minutes"] * 60 * sps)


def compute_save_freq(planned: int, max_steps: int) -> int:
    default = max_steps // 2
    return max(1, min(planned, default))


def default_max_steps() -> int:
    return 2048 * 80


def dirty_tracked_paths(repo_root: Path = REPO_ROOT) -> list[str]:
    out = subprocess.check_output(
        ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=no"],
        text=True,
    )
    dirty: list[str] = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        path_part = line[3:].strip()
        if " -> " in path_part:
            path_part = path_part.split(" -> ", 1)[1]
        if not path_part.startswith("v2/"):
            dirty.append(path_part)
    return dirty


def git_head_commit(repo_root: Path = REPO_ROOT) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()


def latest_checkpoint_steps(run_dir: Path) -> int | None:
    best = 0
    for p in run_dir.glob("poke_*_steps.zip"):
        m = _CHECKPOINT_RE.match(p.name)
        if m:
            best = max(best, int(m.group(1)))
    return best if best > 0 else None


def latest_checkpoint_path(run_dir: Path) -> Path | None:
    steps = latest_checkpoint_steps(run_dir)
    if steps is None:
        return None
    return run_dir / f"poke_{steps}_steps.zip"


def atomic_write_json(path: Path, data: dict[str, Any], retries: int = 5, backoff: float = 0.2) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=False) + "\n"
    tmp = path.parent / f".{path.name}.tmp"
    last_err: OSError | None = None
    for attempt in range(retries):
        try:
            tmp.write_text(payload)
            tmp.replace(path)
            return
        except OSError as exc:
            last_err = exc
            if attempt + 1 < retries:
                time.sleep(backoff * (2 ** attempt))
    raise last_err  # type: ignore[misc]


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def acquire_lock(lockfile: Path) -> None:
    global _lock_path
    lockfile.parent.mkdir(parents=True, exist_ok=True)
    if lockfile.exists():
        try:
            old_pid = int(lockfile.read_text().strip())
        except ValueError:
            old_pid = -1
        if pid_alive(old_pid):
            raise SystemExit(f"runner already running (pid {old_pid})")
        print(f"stale lock (pid {old_pid}), replacing", file=sys.stderr)
    lockfile.write_text(str(os.getpid()) + "\n")
    _lock_path = lockfile
    atexit.register(release_lock)
    signal.signal(signal.SIGINT, _signal_cleanup)
    signal.signal(signal.SIGTERM, _signal_cleanup)


def release_lock() -> None:
    global _lock_path
    if _lock_path and _lock_path.exists():
        try:
            if int(_lock_path.read_text().strip()) == os.getpid():
                _lock_path.unlink(missing_ok=True)
        except (ValueError, OSError):
            pass
    _lock_path = None


def _signal_cleanup(signum, frame) -> None:
    release_lock()
    raise SystemExit(128 + signum)


def claim_job(job_path: Path, running_dir: Path, hostname: str | None = None) -> Path:
    running_dir.mkdir(parents=True, exist_ok=True)
    host = hostname or socket.gethostname()
    claimed = running_dir / f"{host}-{job_path.name}"
    os.rename(job_path, claimed)
    return claimed


def make_run_dir(runs_dir: Path, name: str, now: datetime | None = None) -> Path:
    ts = (now or datetime.now(timezone.utc)).strftime("%Y%m%d_%H%M%S")
    run_dir = runs_dir / f"{name}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def status_path(config: RunnerConfig, job_name: str) -> Path:
    return config.running_dir / f"{job_name}.status.json"


def build_status(
    ctx: RunContext,
    state: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    elapsed = max(0.0, (now - ctx.started_at).total_seconds())
    actual = latest_checkpoint_steps(ctx.run_dir) or 0
    observed_sps = (actual / elapsed) if elapsed > 0 else None
    remaining = max(0, ctx.planned_timesteps - actual)
    eta_s = (remaining / observed_sps) if observed_sps and observed_sps > 0 else None
    rel_run_dir = str(ctx.run_dir.relative_to(V3_ROOT)) if ctx.run_dir.is_relative_to(V3_ROOT) else str(ctx.run_dir)
    return {
        "state": state,
        "job_name": ctx.job.name,
        "run_type": ctx.job.run_type,
        "run_dir": rel_run_dir,
        "started_at": ctx.started_at.isoformat(),
        "elapsed_s": round(elapsed, 1),
        "planned_timesteps": ctx.planned_timesteps,
        "actual_timesteps": actual,
        "observed_sps": round(observed_sps, 1) if observed_sps is not None else None,
        "eta_s": round(eta_s, 1) if eta_s is not None else None,
    }


def write_status(config: RunnerConfig, ctx: RunContext, state: str) -> None:
    atomic_write_json(status_path(config, ctx.job.name), build_status(ctx, state))


def build_run_metadata(
    ctx: RunContext,
    *,
    status: str,
    failure_reason: str | None = None,
    train_exit_code: int | None = None,
    eval_exit_code: int | None = None,
    eval_checkpoint: str | None = None,
    ended_at: datetime | None = None,
) -> dict[str, Any]:
    actual = latest_checkpoint_steps(ctx.run_dir)
    rel_run = str(ctx.run_dir.relative_to(V3_ROOT)) if ctx.run_dir.is_relative_to(V3_ROOT) else str(ctx.run_dir)
    meta: dict[str, Any] = {
        "commit": ctx.commit,
        "hostname": ctx.hostname,
        "job": ctx.job.raw,
        "run_dir": rel_run,
        "claimed_as": ctx.claimed_path.name,
        "status": status,
        "failure_reason": failure_reason,
        "timestamps": {
            "started_at": ctx.started_at.isoformat(),
            "ended_at": (ended_at or datetime.now(timezone.utc)).isoformat() if status in {"done", "failed"} else None,
        },
        "budget": {
            "planned_timesteps": ctx.planned_timesteps,
            "actual_timesteps": actual,
            "planned_minutes": ctx.job.budget.get("minutes") if "minutes" in ctx.job.budget else None,
        },
        "train": {
            "exit_code": train_exit_code,
            "log": config_train_log_name(),
        },
        "eval": {
            "enabled": ctx.job.eval.enabled,
            "exit_code": eval_exit_code,
            "checkpoint": eval_checkpoint,
            "log": config_eval_log_name(),
        },
    }
    return meta


_config_for_metadata: RunnerConfig | None = None


def config_train_log_name() -> str:
    return _config_for_metadata.train_log if _config_for_metadata else "train.log"


def config_eval_log_name() -> str:
    return _config_for_metadata.eval_log if _config_for_metadata else "eval.log"


def write_run_metadata(ctx: RunContext, **kwargs: Any) -> None:
    atomic_write_json(ctx.run_dir / "run_metadata.json", build_run_metadata(ctx, **kwargs))


def build_train_cmd(
    job: Job,
    run_dir: Path,
    planned: int,
    python: str | None = None,
) -> list[str]:
    max_steps = job.max_steps or default_max_steps()
    save_freq = compute_save_freq(planned, max_steps)
    cmd = [
        python or sys.executable,
        "train.py",
        "--num-envs",
        str(job.num_envs),
        "--seed",
        str(job.seed),
        "--init-state",
        job.init_state,
        "--session-path",
        str(run_dir),
        "--save-freq",
        str(save_freq),
        "--no-stream",
    ]
    if "total_timesteps" in job.budget:
        cmd += ["--total-timesteps", str(planned)]
    else:
        cmd += ["--minutes", str(job.budget["minutes"])]
    if job.max_steps is not None:
        cmd += ["--max-steps", str(job.max_steps)]
    if job.warm_start_from:
        cmd += ["--checkpoint", job.warm_start_from]
    return cmd


def build_eval_cmd(
    job: Job,
    run_dir: Path,
    checkpoint: Path,
    python: str | None = None,
) -> list[str]:
    cmd = [
        python or sys.executable,
        "-m",
        "frozen.eval",
        "--checkpoint",
        str(checkpoint.with_suffix("")),
        "--session-path",
        str(run_dir),
    ]
    if job.eval.max_steps is not None:
        cmd += ["--max-steps", str(job.eval.max_steps)]
    if job.eval.state_filter is not None:
        cmd += ["--state-filter", job.eval.state_filter]
    if job.eval.seed_filter is not None:
        cmd += ["--seed-filter", str(job.eval.seed_filter)]
    if job.eval.suite_path is not None:
        cmd += ["--suite-path", job.eval.suite_path]
    return cmd


def fail_job(
    config: RunnerConfig,
    claimed_path: Path,
    reason: str,
    ctx: RunContext | None = None,
    train_exit_code: int | None = None,
    eval_exit_code: int | None = None,
    repo_root: Path = REPO_ROOT,
) -> None:
    config.failed_dir.mkdir(parents=True, exist_ok=True)
    reason_path = config.failed_dir / f"{claimed_path.stem}.reason.txt"
    reason_path.write_text(reason + "\n")
    if ctx is not None:
        write_run_metadata(
            ctx,
            status="failed",
            failure_reason=reason,
            train_exit_code=train_exit_code,
            eval_exit_code=eval_exit_code,
            ended_at=datetime.now(timezone.utc),
        )
        write_status(config, ctx, "failed")
        status_file = status_path(config, ctx.job.name)
        if status_file.exists():
            status_file.unlink(missing_ok=True)
    dest = config.failed_dir / claimed_path.name
    if claimed_path.exists():
        os.rename(claimed_path, dest)
    if ctx is not None:
        ratchet.finalize_job(
            config,
            ctx,
            repo_root=repo_root,
            outcome="crash",
            train_ended_at=ctx.train_ended_at,
            v3_root=V3_ROOT,
        )


def complete_job(
    config: RunnerConfig,
    ctx: RunContext,
    claimed_path: Path,
    train_rc: int,
    eval_rc: int | None,
    repo_root: Path = REPO_ROOT,
) -> None:
    ckpt = latest_checkpoint_path(ctx.run_dir)
    write_run_metadata(
        ctx,
        status="done",
        train_exit_code=train_rc,
        eval_exit_code=eval_rc,
        eval_checkpoint=str(ckpt) if ckpt else None,
        ended_at=datetime.now(timezone.utc),
    )
    write_status(config, ctx, "done")
    status_file = status_path(config, ctx.job.name)
    if status_file.exists():
        status_file.unlink(missing_ok=True)
    config.done_dir.mkdir(parents=True, exist_ok=True)
    os.rename(claimed_path, config.done_dir / claimed_path.name)
    ratchet.finalize_job(
        config,
        ctx,
        repo_root=repo_root,
        outcome="success",
        train_ended_at=ctx.train_ended_at,
        v3_root=V3_ROOT,
    )


def run_train(
    config: RunnerConfig,
    ctx: RunContext,
    python: str | None = None,
) -> subprocess.Popen:
    cmd = build_train_cmd(ctx.job, ctx.run_dir, ctx.planned_timesteps, python=python)
    log_path = ctx.run_dir / config.train_log
    log_f = open(log_path, "w")
    return subprocess.Popen(
        cmd,
        cwd=V3_ROOT,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
    )


def run_eval(
    config: RunnerConfig,
    ctx: RunContext,
    checkpoint: Path,
    python: str | None = None,
) -> subprocess.Popen:
    cmd = build_eval_cmd(ctx.job, ctx.run_dir, checkpoint, python=python)
    log_path = ctx.run_dir / config.eval_log
    log_f = open(log_path, "w")
    return subprocess.Popen(
        cmd,
        cwd=V3_ROOT,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
    )


def wait_with_status_refresh(
    config: RunnerConfig,
    ctx: RunContext,
    proc: subprocess.Popen,
    state: str,
) -> int:
    while proc.poll() is None:
        write_status(config, ctx, state)
        time.sleep(config.status_refresh_seconds)
    write_status(config, ctx, state)
    return proc.returncode or 0


def process_job(
    config: RunnerConfig,
    claimed_path: Path,
    repo_root: Path = REPO_ROOT,
    python: str | None = None,
    hostname: str | None = None,
) -> None:
    try:
        job = validate_job(json.loads(claimed_path.read_text()), config)
    except (json.JSONDecodeError, JobValidationError) as exc:
        fail_job(config, claimed_path, f"invalid job: {exc}")
        return

    dirty = dirty_tracked_paths(repo_root)
    if dirty:
        fail_job(config, claimed_path, f"dirty tree (commit first): {', '.join(dirty)}")
        return

    manifest_result = verify_frozen_manifest(repo_root)
    if not manifest_result.ok:
        fail_job(
            config,
            claimed_path,
            f"frozen manifest mismatch: {manifest_result.summary()}",
        )
        return

    started_at = datetime.now(timezone.utc)
    try:
        run_dir = make_run_dir(config.runs_dir, job.name, now=started_at)
    except FileExistsError:
        # Extremely unlikely same-second collision; nudge timestamp.
        started_at = datetime.now(timezone.utc)
        time.sleep(1.1)
        run_dir = make_run_dir(config.runs_dir, job.name, now=started_at)

    planned = planned_timesteps(job)
    ctx = RunContext(
        job=job,
        run_dir=run_dir,
        claimed_path=claimed_path,
        started_at=started_at,
        planned_timesteps=planned,
        commit=git_head_commit(repo_root),
        hostname=hostname or socket.gethostname(),
    )

    write_run_metadata(ctx, status="running")
    write_status(config, ctx, "training")

    train_proc = run_train(config, ctx, python=python)
    train_rc = wait_with_status_refresh(config, ctx, train_proc, "training")
    ctx.train_ended_at = datetime.now(timezone.utc)
    if train_rc != 0:
        fail_job(
            config,
            claimed_path,
            f"train exited with code {train_rc}",
            ctx=ctx,
            train_exit_code=train_rc,
            repo_root=repo_root,
        )
        return

    eval_rc: int | None = None
    if job.eval.enabled:
        write_status(config, ctx, "evaluating")
        ckpt = latest_checkpoint_path(ctx.run_dir)
        if ckpt is None:
            fail_job(
                config,
                claimed_path,
                "no checkpoint for eval",
                ctx=ctx,
                train_exit_code=train_rc,
                repo_root=repo_root,
            )
            return
        eval_proc = run_eval(config, ctx, ckpt, python=python)
        eval_rc = wait_with_status_refresh(config, ctx, eval_proc, "evaluating")
        if eval_rc != 0 or not (ctx.run_dir / "scorecard.json").is_file():
            fail_job(
                config,
                claimed_path,
                f"eval failed (exit {eval_rc})",
                ctx=ctx,
                train_exit_code=train_rc,
                eval_exit_code=eval_rc,
                repo_root=repo_root,
            )
            return

    complete_job(config, ctx, claimed_path, train_rc, eval_rc, repo_root=repo_root)


def drain_queue(
    config: RunnerConfig,
    repo_root: Path = REPO_ROOT,
    python: str | None = None,
    hostname: str | None = None,
) -> int:
    config.queued_dir.mkdir(parents=True, exist_ok=True)
    jobs = sorted(config.queued_dir.glob("*.json"), key=lambda p: p.name)
    if not jobs:
        print("jobs/queued/ is empty; nothing to run")
        return 0

    for job_path in jobs:
        if not job_path.exists():
            continue
        claimed = claim_job(job_path, config.running_dir, hostname=hostname)
        print(f"starting job {claimed.name}")
        process_job(config, claimed, repo_root=repo_root, python=python, hostname=hostname)

    print("queue finished")
    return 0


def main(argv: list[str] | None = None) -> int:
    global _config_for_metadata
    p = argparse.ArgumentParser(description="Drain v3 job queue (one job at a time).")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    args = p.parse_args(argv)

    config = load_config(args.config)
    _config_for_metadata = config
    for d in (config.queued_dir, config.running_dir, config.done_dir, config.failed_dir, config.runs_dir):
        d.mkdir(parents=True, exist_ok=True)

    acquire_lock(config.lockfile)
    return drain_queue(config)


if __name__ == "__main__":
    raise SystemExit(main())
