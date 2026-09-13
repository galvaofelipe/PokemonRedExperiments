# 06 — Runner + job queue

**What to build:** The v3 host-side runner (spec D3/D11): drains a jobs directory
one job at a time, where each job is JSON describing an experiment — name, run
type (cadence/marathon/probe), budget, env count, seed, init state, warm-start
source, eval block (suite, seeds, episodes). At launch the runner stamps the
current git commit into the run metadata and **rejects a dirty tree**. A job
executes train → eval → Scorecard; probes skip eval unless requested. The old
v2 queue is not modified and finishes its current work untouched.

**Blocked by:** 04 — eval protocol + Scorecard.

**Status:** ready-for-human

- [x] Hand-submitting a smoke job produces: training output, eval Scorecard,
      per-run directory with logs, and job status transitions
      (queued/running/done/failed) — smoke 2026-09-11:
      `v3/verify/runner_smoke.py` green; run dir
      `v3/runs/smoke_runner_20260911_175508/` (train.log, eval.log,
      scorecard.json 1.1.0, run_metadata.json, checkpoints 2048+4096), job
      landed in `done/Mac-Mini.hitronhub.home-smoke_runner.json`, queue dirs
      drained
- [x] The run metadata contains the exact git commit; a job submitted with
      uncommitted changes is refused — `run_metadata.json` stamps
      `git rev-parse HEAD` + hostname; dirty-tree rule rejects any tracked
      change outside `v2/` (untracked ignored). Unit tests:
      `test_dirty_tree_allows_v2_only`, `test_dirty_tree_rejects_v3`
- [x] Crash handling: a dead training process yields status=failed, not a hang
      — subprocess + `poll()` loop, exit≠0/signal → `failed/` with reason.
      Unit test: `test_train_crash_goes_failed`
- [x] One job in flight at a time (structural semaphore) — single-process
      drain loop + atomic rename claim (`queued/` → `running/<host>-<job>.json`)
      + pid lockfile `v3/jobs/.runner.lock` with stale-pid detection
- [x] warm_start_from is honored (checkpoint loads before training) — job
      field maps to `train.py --checkpoint` (unit-tested in cmd builder)
- [x] v2's queue and active run are undisturbed — runner reads/writes only
      `v3/jobs/` + `v3/runs/`; git status confirms no v2 edits

## Comments

- 2026-09-11: Implemented per approved gap-analysis decisions (11 items) plus
  the remote-marathon-worker design-goal disciplines (atomic rename claim with
  host prefix, `v3/bin/runner_config.json` for machine-local values, hostname in
  run metadata, status.json written early + refreshed every 15s via
  write-temp-then-rename with retry/backoff, local session dir). Code:
  `v3/bin/runner.py`, `v3/bin/status.py`, `v3/bin/runner_config.json`,
  `v3/jobs/{queued,running,done,failed}/`, `v3/tests/test_runner.py` (20 tests,
  65/65 suite green), `v3/verify/runner_smoke.py`. Schema extension approved
  during planning: optional eval passthrough keys (`max_steps`, `state_filter`,
  `seed_filter`, `suite_path`), default = frozen suite. Frontier with 08
  respected: no Ledger append. Runner-crash recovery is manual (documented in
  runner docstring): move stranded `running/<host>-<job>.json` back to
  `queued/` or `failed/`. Remaining: hand-run smoke, then commit.
- 2026-09-11: INBOX wants ETA + started-at + elapsed on the progress page.
  Do that on the v3 runner status from the start. Leave `v2/watch_progress.py`
  and the live b35m job alone (this ticket already forbids modifying the v2
  queue). PPO finishing a rollout can overshoot the planned timestep budget
  (b45 showed 100.1%); show planned vs actual rather than treating overshoot
  as a runaway.
