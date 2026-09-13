# 01 — v3 scaffold + Seam split

**What to build:** A clean-room copy of the v2 training stack under a new top-level
`v3/`, refactored behavior-preservingly so the emulator mechanics (emulator loop,
RAM reads, observation construction, step/reset) live in a Frozen env core while
the reward function, reward/observation config, and PPO hyperparameters live in a
single Editable `train.py`. The event-flag observation is widened to the full
verified range (320 bytes / 2560 bits) — bit-level obs compatibility with v2 is
deliberately sacrificed. RAM address constants are extracted into a Frozen
`ram_map` using disassembly-verified names (`wPlayerMoney`,
`EVENT_BOUGHT_MUSEUM_TICKET`). The Frozen/Editable/Human-owned directory layout
(spec D19) is established so the Frozen set is separable at the directory level.
v2 is not touched; the running queue keeps working.

**Blocked by:** None — can start immediately.

**Status:** ready-for-human

- [x] A short v3 training run (minutes-scale) completes and produces checkpoints +
      tensorboard output comparable to v2
- [x] Parity check: same starting conditions produce telemetry/tensorboard
      trajectories matching v2 within noise (modulo the widened event observation)
- [x] The reward function and PPO config are changeable by editing only the
      Editable file — no Frozen file needs modification for a reward experiment
- [x] Frozen and Editable artifacts live in separate directories per the spec layout
- [x] v2's active run is undisturbed throughout

## Acceptance record (2026-09-11)

Human re-verified with own hands after issue 02 landed:

- Parity check re-run: `.venv/bin/python v3/verify/parity_v2_v3.py --steps 512`
  → `PASS: 512 steps` (rewards, observations, agent_stats and full WRAM
  byte-identical between v2 and v3 core, modulo the deliberately widened
  2560-bit event observation).
- `git diff d8ffed2 1452727 --stat -- v2/` → empty (v2 untouched).
- b11m baseline still running (PID 40380).
- Smoke artifacts from the original session: `v3/runs/smoke*/` with
  `poke_40960_steps.zip` checkpoints + tfevents.
