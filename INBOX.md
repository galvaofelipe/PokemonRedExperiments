# TODO

## Training queue (`v2/watch_progress.py`) — leftover ops, not a v3 ticket

v3's runner is issue 06; that ticket must not modify the v2 queue. These were
local UI nits on the old page:

- [x] Show ETA + started at + elapsed
- [x] 100.1% on b45 (1,945,600 / 1,944,000) is PPO finishing the last rollout,
      not a runaway. Display planned vs actual, or cap the bar at 100% and
      show the extra steps as overshoot
- [x] SPS / RSS sparklines were lying: per-row autoscale of cumulative `avg_sps`
      made a 5-step drift look like a crash. Shared y-axis 0–900, 5 min MA of
      instant SPS, hover + caption for axis/series range; RSS chart dropped,
      peak folded into the RAM / CPU cell
- When building the v3 runner status page in [06](.scratch/autoresearcher-gym/issues/06-runner-and-job-queue.md),
      put ETA / start / elapsed in from the start so this does not recur.
      Same for a shared SPS axis and no RSS sparkline.

## TensorBoard for future v3 runs

Overnight v2 was hard to read: `env_stats/map` averaged map ids, `event` was
scaled reward, unique map names were never a scalar, and game stats only
flushed every 1.31M steps. Main work:
[14 — training TensorBoard scalars](.scratch/autoresearcher-gym/issues/14-training-tensorboard-scalars.md).

How to use the current UI (v2, leave the 35M job alone):
[overnight-runs canvas](/Users/luizfelipegalvaoramos/.cursor/projects/Users-luizfelipegalvaoramos-dev-PokemonRedExperiments/canvases/overnight-runs-tensorboard.canvas.tsx).

Items, each pointing at the ticket that should absorb it:

- [ ] Unique **map names / unique map count during training** (the question
      “are we scoring/reporting how many map names each game saw?”)
      - Scoring: already in the Frozen Score as `unique_maps`
        ([02](.scratch/autoresearcher-gym/issues/02-frozen-scorer.md), done)
      - Eval Scorecard breakdown: [04](.scratch/autoresearcher-gym/issues/04-eval-protocol-and-scorecard.md)
        (spec already says maps/dex/level stats — include `unique_maps` and
        names, not a mean of map ids)
      - Live TensorBoard scalar + name list: [14](.scratch/autoresearcher-gym/issues/14-training-tensorboard-scalars.md)
      - Geography while it trains: [10](.scratch/autoresearcher-gym/issues/10-live-map-viz.md);
        after the fact: [11](.scratch/autoresearcher-gym/issues/11-offline-replay.md)
- [ ] Raw **events** vs shaped reward on TensorBoard
      - Files already have raw `event_count` per step:
        [03](.scratch/autoresearcher-gym/issues/03-telemetry-recording.md) (done)
      - Live scalars (`event_count` beside `reward/event`; stop treating 16 as
        “story” when it is eight Oak-intro bits): [14](.scratch/autoresearcher-gym/issues/14-training-tensorboard-scalars.md)
      - Named split first-hits (Brock, Mt. Moon, …) on the Scorecard:
        [05](.scratch/autoresearcher-gym/issues/05-split-extraction.md)
      - 0/1 `flags/…` scalars for the overnight-style bits (Pokédex, Route 22
        rival) plus those split names: [14](.scratch/autoresearcher-gym/issues/14-training-tensorboard-scalars.md)
- [ ] **Reward plots** that are not the keep/discard Score
      - Episode return curve + `reward/*` vs `env_stats/*` namespaces: [14](.scratch/autoresearcher-gym/issues/14-training-tensorboard-scalars.md)
      - Do **not** retune explore vs badge weights until the v2 45min / 11M /
        35M reference baselines are backed up. That is an Editable `train.py`
        experiment, not a dashboard fix, and it would break the yardstick
- [ ] Denser game-stat cadence, stop averaging `map`/`x`/`y`/`step`, stop
      keeping 163k `agent_stats` dicts per env:
      [14](.scratch/autoresearcher-gym/issues/14-training-tensorboard-scalars.md)
      (parity only compares `agent_stats[-1]`)

## Map progression order ("expected sequence")

Absorbed as two Frozen tables, not a single 248-map list. Score unchanged
(`unique_maps` stays the unordered count). Report (09) / TensorBoard (14) /
viz (10, 11) consume later.

- [x] Decide graph vs sequence vs DAG, surfaces, D1–D4 — see CONTEXT (Map
      graph, Route DAG, Spine)
- [ ] Map graph (warp destinations into Frozen metadata):
      [16](.scratch/autoresearcher-gym/issues/16-map-graph.md)
- [ ] Route DAG + Scorecard compass:
      [17](.scratch/autoresearcher-gym/issues/17-route-dag.md)

## v2 A/B after b35m (do not touch the live job)

One-factor runs against the existing 11M / 35M yardstick. Queue only after
b35m finishes and backs up. Do not combine 2h episodes and faint-reset in
the same job.

- [ ] Fix `--early-stop` so it actually ends the episode on faint. Today the
      flag is stuffed into `env_config` and ignored: `check_if_done` is only
      `step_count >= max_steps - 1`, and the faint line is commented out.
      v1's `early_stop` was “blank screen,” not whiteout — wire faint, not
      that. Leave default off so b11m/b35m stay comparable.
- [ ] Add `--n-steps` to `v2/baseline_fast_v2.py` (and v3 `train.py` when
      convenient). Today `n_steps = max_steps // 64`, so shortening the
      episode silently shrinks the PPO horizon. Default stays 2560
      (`163840 // 64`) so current jobs do not change.
      Pleines et al. 2025 (Table I / §III): worker horizon **2048 beat 512
      and 1024**. They did not report 256; `--max-steps 16384` without
      pinning `--n-steps` would drop to 256 and confound the episode-length
      test. For 2hep jobs pin `--n-steps 2560` (or 2048 to match the paper).
- [ ] Run **b11m_2hep**: same 11M / 8 envs / seed 0 as b11m, `--max-steps
      16384` (~1.83 in-game hours, Peter’s YouTube length), `--n-steps`
      pinned. Compare `max_map_progress`, `coord_count`, deaths-per-life — 
      not wall clock.
- [ ] Run **b11m_esfaint**: same 11M / 18h episodes / pinned `n_steps` as
      b11m, only faint-reset on. Blocked on the `--early-stop` fix.
- [ ] If either 11M probe actually leaves Pallet/Viridian (Forest / Pewter /
      a badge), then run **b35m_2hep** and/or **b35m_esfaint** — same one
      factor, 35M budget. Do not marathon a recipe that already failed at
      11M.


## Unraid
- [ ] Subir um tensorboard no unraid pra inspecionar as runs na share. (talvez copiar tfevents pra share via filewatcher ou algo assim durante o run_queue.sh)


## AM18 peformance analisys
- [ ] analisar performance em diferentes geometrias (.scratch/explore-v2-training/issues/22-accumulator-geometry-alternatives.md)
      - physical environments interest data points = 8, 12, 16, 20, 24, 28, 30
      - logical environts to consider when searching for multiples = 40, 48, 60, 120, 140
      - .scratch/explore-v2-training/issues/22-accumulator-geometry-alternatives.md