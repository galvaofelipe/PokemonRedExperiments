# Auto-researcher gym side (v3) — spec

Status: ready-for-agent

Scope: **gym side only** — everything this repo must provide so an external
auto-researcher agent (autoresearch-style loop) can iterate on PPO training code +
reward functions against a frozen evaluator. The auto researcher itself and any
prime-agent integration are explicitly out of scope.

Terminology per `CONTEXT.md`: Frozen / Editable / Human-owned, Score, Scorecard,
Audit, Report, Seam, Cadence run, Marathon, Champion, Ratchet, Split, Milestone,
Ledger, Reference baseline.

## Problem Statement

I want an auto researcher to eventually run multi-day unattended RL experiments on
this repo — editing the training reward and PPO config, launching runs, and being
judged by genuine in-game progress. Today that is impossible: the reward function
and PPO config are buried inside the training stack (no Seam), no run produces a
trustworthy progress measurement (no Score, no eval protocol, no Ledger), v2
persists no per-step game state (no replay, no split timing, no Audit possible),
and there is no way to watch or review what a run actually did beyond tensorboard
scalars. I need the gym side of the forever-agent architecture built and proven —
with the auto researcher simulated by hand — before investing in the agent itself.

## Solution

Build a clean-room `v3/` stack: a Frozen env core + scorer + eval protocol
(filesystem-enforced read-only for any agent process) beside a single Editable
`train.py` (reward + PPO config + observation selection). A host-side runner drains
a job queue — train, then evaluate from a versioned save-state suite — and emits a
per-run Scorecard (frozen Score + component breakdown + splits) into an append-only
Ledger. Full per-step telemetry recording underpins live map visualization, offline
replay, split timing against human WR pace, and post-hoc Audits. Champion promotion
is automatic behind a noise threshold, with manual undo via git. v2 keeps running
untouched as the Reference-baseline generator; v3 trains from scratch so every
Score in the Ledger is comparable.

## User Stories

1. As the human operator, I want v2 untouched while v3 is built, so the running
   baseline queue (b11m) completes safely.
2. As the human operator, I want v2's 45-min / 11M-step / 35M-step runs preserved
   as Reference baselines, so I can contextualize v3 Scores against the old stack.
3. As the auto researcher, I want one Editable file holding the reward function,
   reward/obs config, and PPO hyperparameters, so my iteration surface is obvious
   and total.
4. As the auto researcher, I want the env mechanics (emulator loop, RAM reads,
   observation construction) Frozen, so I can't accidentally break the substrate.
5. As the human operator, I want the Frozen set separable at the directory level,
   so an agent container can mount it read-only.
6. As the human operator, I want a hash manifest checked before every run plus a
   git hook on frozen paths, so tampering is caught even outside any sandbox.
7. As the auto researcher, I want to request runs only by dropping job files into
   a queue, so I can never thrash the hardware directly.
8. As the human operator, I want the runner daemon to live outside the agent
   sandbox, so it is the structural semaphore between the agent and the machine.
9. As the auto researcher, I want every job stamped with its git commit and dirty
   trees rejected, so every result is provably tied to exact code.
10. As the auto researcher, I want the keep/discard Score computed only from frozen
    eval episodes (final policy, reward disabled), so the Ratchet measures what the
    policy reliably does — not what exploration stumbled into during training.
11. As the human operator, I want the Score built from one-way, set-once game bits
    with grinding terms capped, so it resists the documented reward-hacking
    failure modes (heal-farming, nav-dominance, gym-skipping).
12. As the human operator, I want the Score formula and eval suite versioned and
    recorded on every result, so a definition change never silently inflates
    "progress" and old runs remain interpretable.
13. As the auto researcher, I want paired common seeds across experiments and a
    minimum-effect threshold δ, so the Ratchet doesn't ratchet on luck.
14. As the human operator, I want the eval suite to launch with the save states
    already on disk and grow as I capture more milestones, so bring-up is never
    blocked on manual gameplay.
15. As the human operator, I want every run to record per-decision-step telemetry
    (position, map, badges, event count, dex, levels), so replay, split timing,
    and Audit are possible for every run.
16. As the human operator, I want to watch a run live on a local stitched-map
    visualization, so I can see what the policy is doing while it trains.
17. As the human operator, I want to replay a finished run's trajectories offline,
    so I can inspect any experiment after the fact.
18. As the auto researcher, I want a per-run Scorecard with the Score, its
    component breakdown, splits achieved with first-hit step counts and in-game
    times, and deltas versus the Champion, so I know exactly where progress came
    from.
19. As the auto researcher, I want an append-only Ledger (one row per run) plus a
    journal file, so my memory survives session restarts, crashes, and model swaps.
20. As the human operator, I want a daily Report rendered from the day's Scorecards
    and Milestones, so I can review progress at a glance.
21. As the auto researcher, I want splits detected from disassembly-verified RAM
    conditions and timed on the in-game play clock, so my progression feedback is
    dense, correct, and comparable to human speedrunner pace independent of which
    machine ran the job.
22. As the human operator, I want first-time Milestones (splits, badges) recorded
    permanently with run and step, so weekly badge milestones track themselves.
23. As the human operator, I want Champion promotion automatic behind the δ gate
    with manual demotion available, so the loop runs unattended without
    entrenching lucky winners.
24. As the human operator, I want v3 to train from scratch (with warm-start
    available as an explicit job option), so Ledger Scores stay comparable and no
    alien-reward checkpoint contaminates the baseline.
25. As the human operator, I want the gym side's definition of done to require zero
    auto-researcher code, so I can validate the whole half by hand before building
    the agent.

## Implementation Decisions

- **D1. Location.** Fresh `v3/` directory, clean-room: v2 files copied in, then
  split. v2 is mid-run and full of untracked WIP; v3 must not touch it. v2's
  ongoing role is producing the Reference baselines (45-min, 11M-step, 35M-step).
- **D2. The Seam.** The env is split behavior-preservingly into a Frozen env core
  (emulator loop, RAM reads, observation construction, step/reset mechanics) and an
  Editable `train.py` (reward function, reward/obs config, PPO hyperparameters).
  The agent-editable surface is exactly one file.
- **D3. Runner.** A new runner beside the old queue (which finishes its current
  work untouched), reading its own jobs directory. The runner stamps the git commit
  at launch and rejects a dirty tree. Cadence, Marathon, and Probe are job types
  distinguished by budget; Probes produce telemetry but no Scorecard unless eval is
  requested.
- **D4. Score source.** Keep/discard Scores come exclusively from frozen eval
  episodes. Training telemetry is logged in the same Ledger row as diagnostics,
  never compared for keeps.
- **D5. Score formula v1.**
  `Score = 100·badges + 1·events + 2·dex_caught + 0.5·dex_seen + 1·unique_maps + 0.1·min(level_sum, 100)`,
  all running maxima of one-way game bits. Event range: the full
  `0xD747–0xD886` (320 bytes, 2560 bits, `NUM_EVENTS=$A00`), minus a frozen baseline
  set, minus the museum-ticket bit. Money excluded (farmable). Formula versioned.
- **D6. Eval suite v1.** The two usable states already on disk (fresh game,
  early-progression), 3 seeds each, 16,384-step cap, δ = 2.0. Suite is versioned
  data, expanded as the human captures milestone states. => /dev/pokemonred_puffer/pyboy_states
- **D7. Telemetry.** Per env per episode, gzipped, per decision step:
  step, x, y, map id, badges, event count, dex seen/caught, level sum — plus the
  in-game play clock (see D16) so split times are hardware-independent. Same
  cadence as the legacy `agent_stats` dumps so existing renderers nearly consume
  it directly.
- **D8. Researcher feedback surface.** Per run, one machine-readable Scorecard:
  Score, component breakdown, splits achieved (first-hit step + in-game time),
  maps/dex/level stats, deltas vs Champion. No pre-computed cross-run trends — the
  researcher reads the Ledger for those. The daily Report renders from Scorecards
  + Milestones and adds WR-pace comparisons.
- **D9. Champion promotion.** Automatic on Score > Champion + δ (commit kept,
  checkpoint becomes Marathon warm-start target); human demotes via git when a
  winner looks lucky.
- **D10. Frozen enforcement.** Primary: directory-level separation so an agent
  container mounts the Frozen set read-only (container itself is out of scope —
  see below). Backup teeth, in scope now: a committed hash manifest checked by the
  runner before every launch (re-hash is a deliberate human command) and a git
  pre-commit hook rejecting frozen-path edits.
- **D11. Job schema.** JSON: name, run type, budget, env count, seed, init state,
  warm-start source, eval block (suite, seeds, episodes).
- **D12. Ledger schema.** Append-only tsv, one row per run: commit, tag, score
  mean/max, component counts (badges, events, dex caught, maps), steps, sps, train
  minutes, status (keep/discard/crash), description — plus run type, score version,
  eval suite version, init states. Splits live in Scorecards and the Milestones
  log, not in tsv columns.
- **D13. Acceptance test (definition of done).** (1) v3 baseline reproduces v2
  behavior within noise; (2) one full loop iteration by hand — edit `train.py`,
  submit job, receive Scorecard, Ledger row appended; (3) Frozen enforcement proven
  — hash check passes normally and catches deliberate tamper; (4) live map viz
  during a run + offline replay of a finished run; (5) daily Report renders from
  that day's data. No auto-researcher code involved. Marathon cycle not gated on.
- **D14. From scratch.** v3 trains from scratch for Ledger comparability;
  warm-start remains a supported job field for later Marathons.
- **D15. Widened event scan.** Both scorer and training observation scan the full
  event range (v2 stops 8 bytes early, missing Seafoam puzzle bits and Beat
  Articuno). Observation vector grows accordingly; bit-level obs compatibility
  with v2 is explicitly sacrificed.
- **D16. Split set and timing.** Sixteen splits, every condition verified against
  the pokered disassembly (badges via `0xD356` bits with event-flag alternatives;
  Mt. Moon via a Super-Nerd-fight + Route-4-entry combo; mid-game item splits via
  verified event bits; run end via Beat-Champion-Rival). The canonical mapping
  lives in `.scratch/references/splits_draft.json` and freezes into v3 as data;
  its array order is the canonical route order (reference progression, not a
  completion requirement), and segment times are computed in completion order —
  delta from the most recently achieved split — so out-of-order splits never
  produce negative segments.
  Split times recorded on the in-game play clock (hours/min/sec/frames, plain
  binary), which is hardware-independent and directly comparable to human WR
  real-time paces.
- **D17. Human pace references.** Frozen reference tables derived from the
  LiveSplit `.lss` files in `.scratch/references/lss/` (pokeguy PB 1:55:56 with
  WR-pace column; Headbob 2018-era 1:59:38). Thirteen of our sixteen splits have
  direct human counterparts; our Bill/HM01/Bike splits have none (extra feedback,
  no comparison); the human Nidoran/Route-3/Giovanni-1/Elite-Four sub-splits are
  not tracked (Elite Four room-entry bits exist if ever wanted). The Report shows
  agent split time vs WR pace where a counterpart exists.
- **D18. Verified address ground truth.** All addresses verified against the
  pokered disassembly (`wram.asm`, `event_constants.asm`, sym file): zero numeric
  corrections. Naming: money is `wPlayerMoney`; the excluded museum event is
  `EVENT_BOUGHT_MUSEUM_TICKET`. The DeepSeek autosplitter research was reconciled;
  its four wrong claims are documented in the splits draft metadata.
- **D19. Layout.** Frozen subtree (env core, scorer, eval, ram map, splits,
  reference tables, eval states) / Editable `train.py` / Human-owned `program.md` /
  RW workspace (jobs, runs, Ledger, journal, Milestones log) / host-side `bin/`.

## Testing Decisions

The repo has no test suite today, so there is no prior art to match; v3 introduces
the first one, and it tests external behavior only — never implementation details.

Three test seams, one per layer, each at the highest point that layer allows:

1. **Scorer seam (pure function).** The scorer consumes a sequence of RAM snapshots
  and produces a Score + breakdown. Tested by replaying recorded snapshots from
  real v2 runs and scripted walks: known milestones must move the Score by known
  amounts; repeatable actions (healing, pacing one route, wild-battle grinding past
  the cap) must not. This is the seam that proves the Score is hack-resistant.
2. **Runner seam (job in → artifacts out).** A tiny-budget smoke job through the
  full pipeline: training runs, eval episodes execute, Scorecard + Ledger row +
  telemetry appear, commit hash stamped, dirty-tree rejection works, tampered
  Frozen file is caught. This single seam covers the acceptance test's loop
  iteration end-to-end.
3. **Env-core parity seam.** The refactored Frozen core must behave like v2: same
  starting conditions produce matching telemetry/tensorboard trajectories within
  noise (modulo the deliberately widened event observation).

No tests for: the map visualization (manually verified via acceptance test 4) or
the Report renderer (spot-checked via acceptance test 5).

## Out of Scope

- The auto researcher itself: agent harness, LLM choice/routing, API budgets,
  prompt discipline, watchdog, Docker sandbox construction (the layout supports
  read-only mounts; building the container is agent-side work, later).
- prime-agent integration in any form.
- `program.md` content beyond a placeholder.
- Marathon scheduling automation (cron cadence, weekend runner) — the job type and
  warm-start field exist, the scheduler is agent-side.
- Long-term telemetry storage/archival on UNRAID — tracked as issue 01.
- Capturing new eval save states (human gameplay, happens alongside bring-up).
- Elite Four sub-splits and the 124-glitchless dex-count split table (references
  exist; not part of the split set).

## Further Notes

- Key references: `.scratch/references/forever_agent_pokemon_design.md` (the
  architecture this spec operationalizes), `.scratch/references/splits_draft.json`
  (verified split mapping; human-reviewed 2026-09-11, frozen as `v3/frozen/splits/splits.json`), `.scratch/references/lss/`
  (human pace data), `.scratch/references/auto-splitters-research.md` (partially
  wrong; reconciliation documented in the splits draft metadata),
  `.scratch/references/splits.txt` (original split list).
- The pokered disassembly clone at `~/dev/pokered/` is the address ground truth;
  re-verify against it if any RAM condition is ever questioned.
- Open items: UNRAID storage ticket; local
  pokerl-map-viz setup (one-line websocket URL patch + message recording).
