#!/usr/bin/env python3
"""Human-only command to regenerate v3/frozen_manifest.sha256.

Refuses to run when protected paths have uncommitted tracked changes.
Legitimate flow after a Frozen change:
  1. Commit the Frozen change alone with --no-verify
  2. Run this script
  3. Commit the manifest update with --no-verify

Never commits.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from frozen_manifest import (
    MANIFEST_REL,
    atomic_write_text,
    dirty_protected_paths,
    generate_manifest_content,
    manifest_diff,
    parse_manifest,
    repo_root_from_module,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Regenerate v3/frozen_manifest.sha256.")
    p.add_argument("--repo-root", type=Path, default=None)
    args = p.parse_args(argv)

    repo_root = args.repo_root or repo_root_from_module()
    dirty = dirty_protected_paths(repo_root)
    if dirty:
        print(
            "protected paths have uncommitted changes — commit the Frozen change first, then re-hash:\n"
            f"  {', '.join(dirty)}\n\n"
            "Legitimate flow:\n"
            "  1. git commit --no-verify   (Frozen paths only)\n"
            "  2. python v3/bin/rehash_frozen_manifest.py\n"
            "  3. git add v3/frozen_manifest.sha256 && git commit --no-verify",
            file=sys.stderr,
        )
        return 1

    manifest_path = repo_root / MANIFEST_REL
    old: dict[str, str] = {}
    if manifest_path.is_file():
        try:
            old = parse_manifest(manifest_path.read_text())
        except ValueError as exc:
            print(f"existing manifest is invalid: {exc}", file=sys.stderr)
            return 1

    new_content = generate_manifest_content(repo_root)
    new = parse_manifest(new_content) if new_content.strip() else {}

    atomic_write_text(manifest_path, new_content)

    added, removed, changed = manifest_diff(old, new)
    if not added and not removed and not changed:
        print("manifest unchanged")
        return 0

    if added:
        print("added:")
        for path in added:
            print(f"  + {path}")
    if removed:
        print("removed:")
        for path in removed:
            print(f"  - {path}")
    if changed:
        print("changed:")
        for path in changed:
            print(f"  ~ {path}")

    print(f"wrote {MANIFEST_REL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
