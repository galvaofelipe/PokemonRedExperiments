# Reference: Long-term design goals — remote marathon worker + share-as-bus

**Audience:** the agent implementing ticket 06 (runner + job queue).
**Purpose:** 06's scope is unchanged. This document states two accepted long-term
design goals so 06's implementation choices don't create rework. Do NOT build
remote execution, multi-runner support, or scheduling in 06 — just don't
foreclose them.

## Goal A — AM18 as the marathon worker (Windows + WSL2)

A second machine (ACEMAGIC AM18: Ryzen 7 8845HS, 8C/16T, 32GB) will run
marathon jobs long-term, drained from a queue by a copy of the same runner.

**Scheduling note (inverts an earlier assumption):** the AM18 is used for
gaming on weekends, so **marathons on the AM18 run Monday–Friday**, not
weekends. Scheduling policy lives outside the runner either way.

Implications for 06:
- The runner must be **machine-portable**: no hardcoded absolute paths, no
  macOS-only assumptions (`caffeinate`, launchd), no baked-in hostnames.
  Machine-specific values (queue paths, env counts, local scratch dir) come
  from a small runner config file, not the code.
- Job JSON stays **machine-agnostic**: relative paths only; explicit
  `env_count`, `budget`, `init_state`, `warm_start_from` (06 already does
  this — keep it).
- Record the **hostname** in run metadata alongside the git commit stamp.
- Do **not** hardcode any schedule (e.g. "Friday 18:00") into the runner.
  The runner drains queues; *when* jobs land in them is a separate concern.

## Goal B — The UNRAID share is the queue/bus

Long-term, the queue directories and per-run result dirs live on (or sync to)
a UNRAID SMB share. The Mac agent submits jobs by writing job files to the
share; a runner on another machine polls that directory, executes locally,
and writes `runs/<id>/` + scorecard back to the share. The share is the
message bus; there is no central server.

Implications for 06:
- **Claim jobs atomically by rename** (move `queue/<job>.json` →
  `claimed/<host>-<job>.json` before starting). Rename-within-directory is
  atomic enough on SMB; a naive read-then-delete is a race once two runners
  exist.
- **Tolerate share I/O failures**: retry with backoff on transient errors
  when reading the queue dir or writing status; never corrupt or truncate
  `status.json` / `results.tsv` on a failed write (write-temp-then-rename).
- **Train on local disk, sync artifacts to the share.** The session dir must
  be a local path (config), never the mount. Copy checkpoints / scorecard /
  `run.json` out at completion (and optionally at checkpoint cadence).
- **A runner only claims from its configured queue dir(s).** Future topology:
  `queue/cadence/` drained by the Mac runner, `queue/marathon/` drained by
  the AM18 runner, both on the same share. One-runner-per-queue-dir is the
  structural semaphore's remote equivalent.
- Status fields already planned (ETA, started-at, elapsed, planned vs actual
  steps) are exactly what a remote observer needs — write `status.json`
  early and refresh it periodically, not only at transitions.

## Explicit non-goals for 06

- No remote execution, SSH, or multi-runner logic.
- No scheduler/cron of any kind.
- No SMB-specific code paths — just the IO disciplines above (atomic rename
  claims, temp-then-rename writes, retry with backoff, local scratch +
  artifact sync), which are correct on any filesystem.
