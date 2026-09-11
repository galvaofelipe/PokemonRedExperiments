#!/usr/bin/env python3
"""Hand-run smoke: pre-commit hook + runner frozen-manifest refusal.

    cd v3 && ../.venv/bin/python verify/frozen_hook_smoke.py

Not part of pytest — performs real git operations and temporarily modifies a
Frozen file (always restored). Requires a clean porcelain tree at start.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
V3_DIR = REPO_ROOT / "v3"
BIN_DIR = V3_DIR / "bin"
JOBS_QUEUED = V3_DIR / "jobs" / "queued"
RUNNER_TARGET = V3_DIR / "frozen" / "ram_map.py"
JOB_NAME = "smoke_frozen_manifest"
MANIFEST_PATH = V3_DIR / "frozen_manifest.sha256"


def run(cmd: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd or REPO_ROOT),
        text=True,
        capture_output=True,
        check=check,
    )


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["git", "-C", str(REPO_ROOT), *args], check=check)


def porcelain_clean() -> bool:
    out = git("status", "--porcelain").stdout
    return out.strip() == ""


def save_hooks_path() -> str | None:
    proc = git("config", "--local", "--get", "core.hooksPath", check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def restore_hooks_path(saved: str | None) -> None:
    if saved is None:
        git("config", "--local", "--unset", "core.hooksPath", check=False)
    else:
        git("config", "--local", "core.hooksPath", saved)


def install_local_hooks() -> None:
    git("config", "--local", "core.hooksPath", "v3/bin/git-hooks")


def hook_smoke(saved_hooks_path: str | None) -> int:
    if not porcelain_clean():
        print("skip hook smoke: working tree not clean")
        return 1

    install_local_hooks()
    editable = V3_DIR / "train.py"
    editable_original = editable.read_bytes()
    editable.write_bytes(editable_original + b"# hook-smoke-editable\n")
    git("add", str(editable.relative_to(REPO_ROOT)))

    ok = git("commit", "-m", "hook smoke editable", check=False)
    if ok.returncode != 0:
        editable.write_bytes(editable_original)
        git("restore", "--staged", str(editable.relative_to(REPO_ROOT)), check=False)
        print("editable commit failed unexpectedly:")
        print(ok.stdout)
        print(ok.stderr)
        return 1

    reset = git("reset", "--hard", "HEAD~1", check=False)
    if reset.returncode != 0 or editable.read_bytes() != editable_original:
        editable.write_bytes(editable_original)
        print("failed to reset after editable hook smoke")
        return 1

    tamper = RUNNER_TARGET
    original = tamper.read_bytes()
    tamper.write_bytes(original + b"# hook-smoke\n")
    git("add", str(tamper.relative_to(REPO_ROOT)))
    blocked = git("commit", "-m", "hook smoke frozen", check=False)
    git("restore", "--staged", str(tamper.relative_to(REPO_ROOT)), check=False)
    tamper.write_bytes(original)

    if blocked.returncode == 0:
        print("frozen commit should have been blocked")
        return 1
    if "[frozen-set] commit blocked" not in blocked.stderr:
        print("expected frozen-set block message on stderr:")
        print(blocked.stderr)
        return 1

    tamper.write_bytes(original + b"# hook-smoke-subdir\n")
    git("add", str(tamper.relative_to(REPO_ROOT)))
    blocked_sub = run(
        ["git", "commit", "-m", "hook smoke frozen subdir"],
        cwd=V3_DIR,
        check=False,
    )
    git("restore", "--staged", str(tamper.relative_to(REPO_ROOT)), check=False)
    tamper.write_bytes(original)

    if blocked_sub.returncode == 0:
        print("frozen commit from v3/ subdir should have been blocked")
        return 1
    if "[frozen-set] commit blocked" not in blocked_sub.stderr:
        print("expected frozen-set block message from subdir commit:")
        print(blocked_sub.stderr)
        return 1

    print("hook smoke OK")
    return 0


def runner_refusal_smoke() -> int:
    if not MANIFEST_PATH.is_file():
        print("skip runner refusal: v3/frozen_manifest.sha256 not present (bootstrap first)")
        return 0

    if not porcelain_clean():
        print("skip runner refusal: working tree not clean")
        return 1

    target = RUNNER_TARGET
    if not target.is_file():
        print(f"skip runner refusal: missing {target}")
        return 1

    install_local_hooks()
    original = target.read_bytes()
    tamper_committed = False
    rc = 1

    def cleanup() -> None:
        nonlocal rc
        if tamper_committed:
            reset = git("reset", "--hard", "HEAD~1", check=False)
            if reset.returncode != 0:
                print("ERROR: failed to reset tamper commit")
                rc = 1
        if target.read_bytes() != original:
            target.write_bytes(original)
        if not porcelain_clean():
            print("ERROR: working tree not clean after runner smoke cleanup")
            print(git("status", "--porcelain").stdout)
            rc = 1

    try:
        target.write_bytes(original + b"\n")
        if target.read_bytes() == original:
            print("failed to modify frozen target for runner smoke")
            return 1

        rel = str(target.relative_to(REPO_ROOT))
        git("add", rel)
        commit = git("commit", "--no-verify", "-m", "hook smoke tamper bypass", check=False)
        if commit.returncode != 0:
            print("failed to commit tamper with --no-verify:")
            print(commit.stdout)
            print(commit.stderr)
            return 1
        tamper_committed = True

        if not porcelain_clean():
            print("porcelain not clean after tamper commit (dirty-tree would mask manifest check)")
            print(git("status", "--porcelain").stdout)
            return 1

        python = V3_DIR.parent / ".venv" / "bin" / "python"
        if not python.is_file():
            python = Path(sys.executable)

        JOBS_QUEUED.mkdir(parents=True, exist_ok=True)
        job_path = JOBS_QUEUED / f"{JOB_NAME}.json"
        job = {
            "name": JOB_NAME,
            "run_type": "probe",
            "budget": {"total_timesteps": 64},
            "num_envs": 1,
            "seed": 0,
            "init_state": "../init.state",
            "warm_start_from": None,
            "eval": {"enabled": False},
        }
        job_path.write_text(json.dumps(job, indent=2) + "\n")

        subprocess.run(
            [str(python), str(BIN_DIR / "runner.py")],
            cwd=V3_DIR,
        )

        reason_files = list((V3_DIR / "jobs" / "failed").glob(f"*{JOB_NAME}*.reason.txt"))
        if not reason_files:
            print("expected failed job reason file for manifest mismatch")
            return 1

        reason = reason_files[0].read_text()
        if "frozen manifest mismatch" not in reason:
            print(f"unexpected failure reason:\n{reason}")
            return 1

        print("runner refusal smoke OK")
        rc = 0
        return 0
    finally:
        cleanup()


def main() -> int:
    if not shutil.which("git"):
        print("git not found")
        return 1

    saved_hooks = save_hooks_path()
    rc = 1
    try:
        hook_rc = hook_smoke(saved_hooks)
        runner_rc = runner_refusal_smoke()
        rc = 0 if hook_rc == 0 and runner_rc == 0 else 1
    finally:
        restore_hooks_path(saved_hooks)

    if not porcelain_clean():
        print("ERROR: porcelain not clean at exit")
        print(git("status", "--porcelain").stdout)
        return 1

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
