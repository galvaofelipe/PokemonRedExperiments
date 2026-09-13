# Handoff — 2026-09-13 (evening) — AM18 benched; checkpoint extension tonight

**For:** the next sessions tonight — (2nd) checkpoint handling ~22h GMT-3, then
(3rd) setting up the 20M/30M/35M extension jobs.
**Supersedes** the morning "WSL2 bring-up + SPS benchmark" handoff (its work is all
done and committed).

## Machine / env (stable, don't redo)

AM18: Ryzen 7 PRO 8845HS (8C/16T), 30 GB RAM, Radeon 780M (no CUDA). WSL2 Ubuntu
26.04, `.wslconfig` = 24 GB RAM / 16 procs / 16 GB swap. venv `.venv/` (Python
3.12.14 via uv, torch 2.5.0+cpu). System python3 is 3.14 — do NOT use it.
No passwordless sudo — mounts/apt are operator-run.
WSL gotchas: `zsh -c` does NOT source `.zshrc` (use `zsh -ic` or `bash -lc`);
from Git Bash call `MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' wsl.exe -d Ubuntu -- bash -lc '...'`.

## Tower share (done, standardized)

- `POKERED_DATA=$(scripts/ensure_tower.sh)` — mounts at `~/mnt/tower`, idempotent,
  probes LAN then falls back to `tower.ide-pogona.ts.net` (time-bounded).
  Currently mounted via the tailnet name. LAN 192.168.0.9 accepts :445 but stalled
  SMB once (possibly fixed: operator switched Windows network to Private — retest
  only if bulk copies get slow).
- Sharing conventions (publish/consume, what to skip): **HANDOFF-mac-share.md**.

## Bench results (done) → docs/perf/am18.md

- Raw sweep + geometry tables live in `docs/perf/am18.md` (manifest convention:
  `docs/perf/README.md`); issue 07 has the same in PT. Mac manifest = ticket 20.
- **Pick: acc40_p20** (1008 SPS, 21.4 GB peak, ~2.5 GB headroom). 64 streams fits
  only on the edge (22.9/24 GB); **80 streams does not fit — it swap-hung the whole
  VM** (do not retry without the ticket-18 memmap diet). Rule of thumb:
  buffer ≈ 105 KB/sample (logical × n_steps) + ~0.6 GB/physical env.
- Telemetry is now correct on Linux (`v2/resource_callback.py`): footprint = PSS,
  cpu_pct = interval. Don't compare mem/cpu columns with Mac numbers — SPS only.
- Still pending: 30–60 min steady-state validation at the chosen geometry before
  a week-long run (bursts sag maybe 10–20% under thermal soak).

## Checkpoint extension (tonight's mechanism — TESTED)

`baseline_fast_v2.py` grew `--target-steps N [--base-steps M]`:

- Resumes with the global clock (`reset_num_timesteps=False`, `model.num_timesteps`
  set to base): checkpoint names and TB steps **continue the lineage numbering —
  no tb_stitch, no manual offset**. Verified on stock + accumulator geometries.
- TB of the new leg goes to its own `--session-path` (loaded models otherwise keep
  writing to the original run's dir — SB3 stores tensorboard_log in the zip).
- **Mac t16 zips store per-leg steps (9,011,200), so pass `--base-steps 10977280`.**
  New legs started from now on store global steps and need no `--base-steps`.
- `accumulation_rounds` is NOT in the SB3 zip — geometry comes from the job spec /
  CLI (`--num-envs/--physical-envs/--n-steps`), as before.
- Additional steps round UP to the mega-update boundary (accumulator).
- Ticket 19 = the full system (sidecars, lineage ledger, portable refs). The above
  is the working slice for tonight.

## Tonight's sessions

1. **Checkpoint session (~22h GMT-3, when the Mac's 3 t16 jobs finish):** Mac
   publishes the 11M checkpoints to `pokered/runs/v2/` (see HANDOFF-mac-share.md);
   copy the CHOSEN ones down (not all 3 seeds); write extension job specs
   (`--target-steps` 20M/30M/35M, `--base-steps 10977280`, geometry matching the
   source run); sanity-run one extension for a few minutes before queueing.
2. **Long-jobs session:** pick production geometry per `docs/perf/am18.md`
   (recommendation: acc40_p20, or acc64_p16 + `.wslconfig` bump to 26–27 GB),
   run the 30–60 min steady-state validation FIRST, then launch.

## Open threads

- **`.wslconfig` upgrade (operator, needs `wsl --shutdown` — apply between
  sessions):** `memory=26GB`, `swap=32GB` (swap is a sparse VHDX on the Windows
  drive; only consumes disk as used — needs headroom on C:). 26/32 absorbs the
  acc64 peak (~27.6 GB demand) slow-not-crashed; go `memory=27GB`–`28GB` if the
  BIOS UMA shrink below lands. If the box is used as a desktop while training,
  stay at 24–26 GB memory so Windows keeps 4+ GB.
- **BIOS: 4 GB hardware-reserved RAM** = iGPU UMA framebuffer (Radeon 780M;
  workload is headless). Look for "UMA Frame Buffer Size" / "iGPU Memory" (often
  Advanced → AMD CBS → NBIO → GFX). 1–2 GB is plenty; frees 2–3 GB system RAM.
- **Ticket 21**: audit where the accumulator's ~105 KB/sample goes (obs space is
  ~21.6 KB) — dtype casts, train-phase transients, allocator fragmentation.
- cursor-delegate MCP untested in WSL (needs cursor-agent CLI; `doctor` deep:true).
- fstab/`~/.smbcredentials` persistence for the share — still TODO.
- kimi `/login` + `GITHUB_PERSONAL_ACCESS_TOKEN` export on this box (GitHub MCP).
