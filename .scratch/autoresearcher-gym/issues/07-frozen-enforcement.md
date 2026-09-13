# 07 — Frozen enforcement

**What to build:** The backup teeth for the Frozen set (spec D10): a committed
hash manifest covering every Frozen file, verified by the runner before every
launch — mismatch refuses the run. Re-hashing the manifest is a deliberate human
command. A git pre-commit hook rejects commits that touch frozen paths. (The
primary enforcement — read-only container mounts — is agent-side and out of
scope; the layout from ticket 01 already makes the Frozen set
directory-separable.)

**Blocked by:** 06 — runner + job queue.

**Status:** ready-for-human

- [x] A clean tree passes the manifest check and runs — real probe job
      `smoke_manifest_pass` (64 steps, eval off) landed in `jobs/done/` on the
      clean committed tree with the manifest in place, 2026-09-11; unit:
      `test_verify_passes_clean_fixture`
- [x] Deliberately modifying a Frozen file makes the runner refuse the job —
      `v3/verify/frozen_hook_smoke.py` green 2026-09-11: tamper committed via
      `--no-verify` (tree clean) → job in `failed/` with reason `frozen
      manifest mismatch: v3/frozen/ram_map.py`, tamper commit erased and bytes
      restored; unit: `test_process_job_fails_on_manifest_mismatch`
- [x] A commit touching frozen paths is rejected by the hook — smoke hook
      section green: staged Frozen change blocked from repo root AND from the
      `v3/` subdir (relative `core.hooksPath` works), block message on stderr;
      Editable-only commit passes with the global secret scanner chained.
      Hook installed repo-locally: `git config core.hooksPath v3/bin/git-hooks`
- [x] Re-hashing requires the explicit human command, and the manifest update
      is itself a visible commit — `v3/bin/rehash_frozen_manifest.py` refuses
      dirty protected paths (proven live, teaching message); bootstrap manifest
      `v3/frozen_manifest.sha256` (39 entries) committed visibly in `9c68598`;
      hand-verifiable: `shasum -a 256 -c v3/frozen_manifest.sha256` → 39/39 OK

## Comments

- 2026-09-11: Implemented per approved gap-analysis decisions. Code:
  `v3/bin/frozen_manifest.py` (shared stdlib module: FS-walk membership —
  NOT `git ls-files`, so untracked files under `v3/frozen/` are caught —
  generate/verify/diff + hook logic + `pre-commit`/`verify` CLI),
  `v3/bin/rehash_frozen_manifest.py` (human-only, no `--allow-dirty` hatch),
  `v3/bin/git-hooks/pre-commit` (dispatcher: execs `~/.githooks/pre-commit`
  if present — global scanner untouched — then the frozen check; skips
  gracefully inside a future Docker sandbox), runner integration in
  `process_job` between dirty-tree and launch. Tests:
  `v3/tests/test_frozen_enforcement.py` (17) + 1 runner test; suite 83/83
  green. Commit `9c68598`.
- 2026-09-11: Review fixes folded in before commit: `--no-renames` on the
  hook's staged diff (rename OUT of Frozen previously surfaced only the
  destination); smoke runner section models a COMMITTED tamper, because an
  uncommitted one is already caught by the dirty-tree layer first (layers:
  dirty-tree catches uncommitted, manifest catches committed).
- 2026-09-11: Design note for the future agent phase — the hook's block
  message is effectively a PROMPT: it is the main steering surface the auto
  researcher will ever see from the enforcement layer. Not optimized in this
  phase; revisit with real agent-reaction data during prompt tuning.
  Legitimate Frozen change flow is two visible commits: (1) Frozen paths
  alone with `--no-verify`, (2) re-hash + manifest commit. No escape hatches
  by design; pre-sandbox defense is attribution (every run stamps its commit),
  primary enforcement stays the read-only container mount (agent-side, later).
