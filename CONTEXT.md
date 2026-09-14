# CONTEXT.md

Glossary for the Pokémon Red auto-researcher project. Terms here are canonical;
challenge any usage that drifts from these meanings.

## Mutability classes

- **Frozen** — artifacts the auto researcher may never modify (evaluation machinery,
  RAM maps, save states, split definitions). Enforced in code, not by instruction.
- **Editable** — artifacts the auto researcher is expected to modify per experiment
  (training configuration, network architecture, training reward).
- **Human-owned** — artifacts only the human iterates (research program instructions,
  frozen-set membership).
- **Host-side** — Human-owned machinery that runs outside the agent sandbox and is
  neither Frozen (it defines no measurement) nor Editable (the agent never edits it):
  the job runner, queue layout, and status tooling (`v3/bin/`, `v3/jobs/`).

## Core concepts

- **Score** — the frozen scalar measuring genuine game progress, produced exclusively
  by evaluation runs. The sole basis for keep/discard decisions. Training-time reward
  is never the Score.
- **Audit** — post-hoc verification that a reported Score is genuine and reproducible.
  Distinct from scoring: an Audit checks a claim, it does not produce one.
- **Scorecard** — the machine-readable artifact produced by one run's evaluation:
  the Score, its component breakdown, and the run's progress signals. One per run.
- **Report** — the periodic human-readable digest (the "daily score card") rendered
  from the day's Scorecards and Milestones. Influences no automated decision.
- **Seam** — the boundary between Frozen and Editable code. A good Seam lets the
  researcher change everything that matters about training while touching no file
  that defines how progress is measured.

## Run taxonomy

- **Lineage** — a run and all its continuations under one identity: one
  TensorBoard curve and one run directory, extended leg after leg. Fixed within
  a lineage: training reward, env config, and logical geometry (streams ×
  n_steps); physical env count is a machine property and may differ between legs.
- **Leg** (perna) — one continuation segment of a lineage: same identity, larger
  step budget, possibly another machine. Changing anything beyond the step budget
  and the machine is not a leg.
- **Branch** — a new lineage forked from a checkpoint of a parent lineage (e.g. a
  different reward or logical geometry from that point on); the parent checkpoint
  is recorded in the lineage ledger.
- **Lineage ledger** — the append-only, runner-written record mapping each run to
  the checkpoint it resumed from. Provenance, not results — distinct from the
  **Ledger** (experiment outcomes and keep/discard).
- **Cadence run** — a short, fixed-budget train+eval experiment used for day-to-day
  iteration. Results are comparable only to other Cadence runs of the same budget.
- **Marathon** — a long (weekend-scale) run warm-started from the Champion, used to
  test whether Cadence-run gains convert into real milestone progress.
- **Champion** — the current best kept configuration and its checkpoint; the lineage
  every new experiment is compared against and Marathons warm-start from.
- **Ratchet** — the keep/discard discipline: an experiment is kept only if its Score
  beats the Champion's by more than the minimum-effect threshold (δ); otherwise the
  lineage resets to the Champion.

## Training loop

- **Run** — one execution of a job (training and/or evaluation), producing its
  artifacts under a single directory. The Ledger has one row per run.
  _Avoid_: "session" (legacy code term for the run directory).
- **Env** — one emulator instance running the game inside a run. Training uses
  several envs in parallel, each stepping independently.
- **Episode** — one reset-to-done sequence within an env, bounded by the step
  budget — or, in runs with faint-reset enabled, by a party wipe. Training
  episodes shape the policy; eval episodes are the frozen replays that produce
  the Score. Only the latter count for keep/discard.
- **Party wipe** (blackout) — every party Pokémon fainted; the game respawns
  the player at the last Pokémon Center and play continues. An in-game event,
  not an episode boundary by default.
- **Faint-reset** — ending the episode on a party wipe. Optional per run; the
  Reference baselines run without it.
- **Wipe survival** — the configured fraction of episodes that, with
  faint-reset enabled, deliberately do not end on a wipe. Sampled per episode
  at reset, so the policy can experience post-blackout play.
- **Step** (decision step) — one agent action applied to an env. Step budgets,
  telemetry cadence, and split first-hit counts are all measured in decision
  steps.
- **Frame** — one emulator tick, the finest time grain. A step spans a fixed
  number of frames. In-game split times use the play clock, never frames or
  steps.
- **Action** — one discrete game input chosen by the policy at each step, from
  a fixed set.
- **Update geometry** — the shape of one PPO update: how many envs contribute how
  many steps each (n_envs × n_steps samples per update). The author's published run
  used 64 × 2,560 (= 163,840 samples per update); hardware with fewer envs must
  shrink the update, stretch it across accumulation rounds, or lengthen episodes —
  different geometries, not assumed equivalent.
- **Logical streams** — the number of independent rollout streams an experiment
  asks for. The launcher satisfies the request on the available hardware; the
  experiment never negotiates with the machine.
- **Physical envs** — the envs actually spawned in parallel on a machine; a
  hardware property (Mac: 8), not an experiment parameter.
- **Accumulation round** — one full rollout collection (physical envs × n_steps)
  taken with the policy frozen; several rounds combine into a single update.
  Each round's chunk bootstraps at its own boundary, matching the author's
  64 × 2,560 chunk math.
- **Mega-update** — the single PPO update consuming all rounds of one
  accumulation cycle: logical streams × n_steps samples, at the author's update
  cadence.
- **Observation** — the Frozen-constructed view of game state handed to the
  policy at each step.
- **Reward** (training reward) — the Editable per-step scalar the policy
  optimizes. It exists only to shape learning and is never evidence of
  progress — that is the Score's role.

## Progress signals

- **Split** — a named game milestone borrowed from speedrunning (Brock, Mt. Moon,
  Misty, …). A feedback signal for the researcher and the Report; never a component
  of the Score. The frozen split set's array order is the canonical **route order**:
  a reference progression for a relatively linear playthrough, not a completion
  requirement — splits may be achieved in any order.
- **Map graph** — Frozen ROM-derived adjacency of maps: overworld connections plus
  warp edges. Geography. It is not a progress signal.
  _Avoid_: treating graph distance or numeric map id as progress; pokerl's "Route"
  (a published quest sketch, not our artifact).
- **Route DAG** — Frozen directed graph of named story beats, each annotated with
  the essential maps needed for that beat. A compass for what can come next given
  what has already fired; never a Score component and never the only legal order.
  _Avoid_: expected map sequence, unique-map order, topological sort of the Map
  graph.
- **Spine** — the designated MUST path through the Route DAG, used as the main-route
  display order. Parallel branches off the Spine are still progress.
- **Milestone** — a first-time achievement (a Split reached, a badge earned) recorded
  permanently with the run and step count that produced it.
- **Ledger** — the append-only record of every experiment and its outcomes. Part of
  the researcher's persistent memory, together with the journal and the git lineage.
- **Reference baseline** — a fixed set of v2 runs (45-minute, 11M-step, 35M-step)
  preserved as the yardstick for what the pre-v3 stack achieved. v3 Scores are
  compared against Reference baselines for context, never for keep/discard.
- **Save-state suite** — PyBoy `.state` files used as episode starts for training
  and frozen eval. The four early-game files at the repo root (`init.state`,
  `fast_text_start.state`, `has_pokedex.state`, `has_pokedex_nballs.state`) are the
  stable paths jobs already use; `pyboy_states/` holds the same four plus later
  milestone captures for suite expansion. Both are Frozen.

## Conversion rubric

- **Conversion rubric** — the three-level test for whether v2 training converges
  to the same degree on our hardware: kill-fast floors at the short/medium
  reading points, plus a dose-response shape and a pace projection toward the
  long-run gate.
- **Reading point (N1 / N2 / N3)** — the budgets at which the rubric is read:
  N1 short (~2M steps, 3 seeds, judged on the median), N2 medium (~11M steps,
  ≥2 seeds), N3 the long-run gate — Brock within 25–35M total steps.
- **Event flags** — the game's set-once story bits; their popcount is monotone
  and dense and is the rubric's primary dose-response axis. Exploration growth
  (coords, maps) without flag ticks is not progress.
- **Unique maps** — cumulative count of distinct map ids entered; a monotone
  exploration signal far more granular than mmp.
- **mmp (max map progress)** — v2 telemetry index into a fixed story-ordered
  ladder of 15 maps (Oak's Lab → Cerulean Gym). A gate signal, not a continuous
  one; Brock is mmp 7.
- **Dex seen** — pokédex seen-flag popcount; auxiliary battle-engagement signal
  whose encounter luck averages out over long horizons.
