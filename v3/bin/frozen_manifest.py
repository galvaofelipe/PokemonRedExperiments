#!/usr/bin/env python3
"""Frozen-set hash manifest: generation, verification, and pre-commit guard.

Protected scope (membership via filesystem walk):
  - Every file under v3/frozen/ on disk (excluding __pycache__ trees)
  - init.state, fast_text_start.state, has_pokedex.state, has_pokedex_nballs.state
    at the repo root

Committed manifest: v3/frozen_manifest.sha256 (shasum -a 256 format, two spaces
between hex digest and repo-relative path, sorted by path). Verify by hand:

    shasum -a 256 -c v3/frozen_manifest.sha256

Hook install (repo-local only; chains ~/.githooks/pre-commit for secret scan):

    git config core.hooksPath v3/bin/git-hooks

Relative hooksPath is resolved from the common git directory (worktree root).
If hooks fail when committing from a subdirectory, use an absolute path:

    git config core.hooksPath "$(git rev-parse --show-toplevel)/v3/bin/git-hooks"
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

MANIFEST_REL = "v3/frozen_manifest.sha256"
FROZEN_PREFIX = "v3/frozen/"
ROOT_STATE_FILES = (
    "init.state",
    "fast_text_start.state",
    "has_pokedex.state",
    "has_pokedex_nballs.state",
)

BLOCK_MESSAGE = """\
[frozen-set] commit blocked — staged changes touch Frozen paths:
{paths}

These files define how progress is measured. Changing them silently
invalidates every Score in the Ledger, so they change only by explicit
human decision.

Do this instead:
  1. Unstage the Frozen paths:  git restore --staged <path>...
  2. Commit your Editable changes (v3/train.py) normally and resubmit.
  3. If you believe a Frozen file genuinely needs to change, write the
     proposal and rationale in the journal / job description and move on
     to other work — the human reviews it.

Do not bypass with --no-verify: bypasses are permanent, visible git
history and any run stamped with a tampered commit is discarded.
"""


@dataclass
class VerifyResult:
    ok: bool
    hash_mismatches: list[str] = field(default_factory=list)
    missing_on_disk: list[str] = field(default_factory=list)
    extra_on_disk: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts: list[str] = []
        parts.extend(self.hash_mismatches)
        parts.extend(self.missing_on_disk)
        parts.extend(self.extra_on_disk)
        return ", ".join(parts)


def repo_root_from_module() -> Path:
    return Path(__file__).resolve().parents[2]


def is_protected_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if normalized == MANIFEST_REL:
        return True
    if normalized in ROOT_STATE_FILES:
        return True
    return normalized.startswith(FROZEN_PREFIX)


def protected_paths(repo_root: Path) -> list[str]:
    """Enumerate protected files via filesystem walk (not git ls-files)."""
    repo_root = Path(repo_root)
    paths: list[str] = []

    frozen_dir = repo_root / "v3" / "frozen"
    if frozen_dir.is_dir():
        for file_path in sorted(frozen_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if "__pycache__" in file_path.parts:
                continue
            rel = file_path.relative_to(repo_root).as_posix()
            paths.append(rel)

    for name in ROOT_STATE_FILES:
        state_path = repo_root / name
        if state_path.is_file():
            paths.append(name)

    return sorted(set(paths))


def sha256_hex(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def format_manifest_line(hex_digest: str, rel_path: str) -> str:
    return f"{hex_digest}  {rel_path}"


def generate_manifest_content(repo_root: Path) -> str:
    lines: list[str] = []
    for rel in protected_paths(repo_root):
        digest = sha256_hex(repo_root / rel)
        lines.append(format_manifest_line(digest, rel))
    return "\n".join(lines) + ("\n" if lines else "")


def parse_manifest(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise ValueError(f"malformed manifest line {lineno}: {line!r}")
        digest, rel_path = parts[0], parts[1]
        if not all(c in "0123456789abcdef" for c in digest):
            raise ValueError(f"invalid hex digest on line {lineno}")
        out[rel_path] = digest
    return out


def verify(repo_root: Path, manifest_rel: str = MANIFEST_REL) -> VerifyResult:
    repo_root = Path(repo_root)
    manifest_path = repo_root / manifest_rel
    expected = set(protected_paths(repo_root))

    if not manifest_path.is_file():
        return VerifyResult(
            ok=False,
            missing_on_disk=[manifest_rel],
        )

    try:
        listed = parse_manifest(manifest_path.read_text())
    except ValueError:
        return VerifyResult(ok=False, hash_mismatches=[manifest_rel])

    hash_mismatches: list[str] = []
    missing_on_disk: list[str] = []

    for rel_path, expected_digest in sorted(listed.items()):
        disk_path = repo_root / rel_path
        if not disk_path.is_file():
            missing_on_disk.append(rel_path)
            continue
        actual = sha256_hex(disk_path)
        if actual != expected_digest:
            hash_mismatches.append(rel_path)

    extra_on_disk = sorted(expected - set(listed.keys()))

    ok = not hash_mismatches and not missing_on_disk and not extra_on_disk
    return VerifyResult(
        ok=ok,
        hash_mismatches=hash_mismatches,
        missing_on_disk=missing_on_disk,
        extra_on_disk=extra_on_disk,
    )


def _porcelain_paths(repo_root: Path, path_args: list[str]) -> list[str]:
    if not path_args:
        return []
    cmd = [
        "git",
        "-C",
        str(repo_root),
        "status",
        "--porcelain",
        "--untracked-files=no",
        "--",
        *path_args,
    ]
    out = subprocess.check_output(cmd, text=True)
    dirty: list[str] = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        path_part = line[3:].strip()
        if " -> " in path_part:
            path_part = path_part.split(" -> ", 1)[1]
        dirty.append(path_part)
    return dirty


def dirty_protected_paths(repo_root: Path) -> list[str]:
    """Tracked changes under protected scope (for rehash guard)."""
    repo_root = Path(repo_root)
    scope_args = [FROZEN_PREFIX.rstrip("/"), MANIFEST_REL, *ROOT_STATE_FILES]
    return sorted(set(_porcelain_paths(repo_root, scope_args)))


def offending_staged_paths(staged_paths: Iterable[str]) -> list[str]:
    return sorted({p for p in staged_paths if is_protected_path(p)})


def manifest_diff(
    old: dict[str, str],
    new: dict[str, str],
) -> tuple[list[str], list[str], list[str]]:
    old_keys = set(old)
    new_keys = set(new)
    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    changed = sorted(k for k in old_keys & new_keys if old[k] != new[k])
    return added, removed, changed


def atomic_write_text(path: Path, content: str, retries: int = 5, backoff: float = 0.2) -> None:
    import time

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.tmp"
    last_err: OSError | None = None
    for attempt in range(retries):
        try:
            tmp.write_text(content)
            tmp.replace(path)
            return
        except OSError as exc:
            last_err = exc
            if attempt + 1 < retries:
                time.sleep(backoff * (2 ** attempt))
    raise last_err  # type: ignore[misc]


def staged_paths(repo_root: Path) -> list[str]:
    out = subprocess.check_output(
        [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "--cached",
            "--name-only",
            "--no-renames",
            "--diff-filter=ACDMRTUXB",
        ],
        text=True,
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def run_pre_commit(repo_root: Path) -> int:
    offending = offending_staged_paths(staged_paths(repo_root))
    if not offending:
        return 0
    formatted = "\n".join(f"  {p}" for p in offending)
    print(BLOCK_MESSAGE.format(paths=formatted), file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Frozen manifest utilities.")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("pre-commit", help="Pre-commit hook entry (staged frozen-path guard).")

    verify_p = sub.add_parser("verify", help="Verify manifest against disk.")
    verify_p.add_argument("--repo-root", type=Path, default=None)

    args = p.parse_args(argv)
    repo_root = args.repo_root if getattr(args, "repo_root", None) else repo_root_from_module()

    if args.command == "pre-commit":
        return run_pre_commit(repo_root)
    if args.command == "verify":
        result = verify(repo_root)
        if result.ok:
            print("frozen manifest OK")
            return 0
        print(f"frozen manifest mismatch: {result.summary()}", file=sys.stderr)
        return 1

    p.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
