# 25 — acc64 @ 35M from `has_pokedex_nballs.state` (skip Oak/parcel)

Type: task
Status: ready-for-human
Blocked by: —

## Question

Ticket 24 showed `t16_acc64_s0` (64×2560, `init.state`) clears Pokédex+parcel by
~9–11M then **never enters Route 2** through ~19M. Author/PokeRL yardstick
(ticket 11): Brock ~10M, SS Anne ~26M on similar geometry from the very start.

Hypothesis to test overnight: the early Oak/parcel phase is not the bottleneck —
give the fleet the author’s old head-start state (`has_pokedex_nballs.state`: dex +
balls already) and train the **same author geometry** straight to 35M. If they
still stall north of Viridian / never badge, the wall is post-dex policy/reward.
If they move (Forest → Pewter → Brock), the cold start / early-game shaping is
implicated.

## Spec (operator runs; agent does not launch)

| knob | value |
|---|---|
| geometry | 64 logical × `n_steps` 2560 (update 163 840) |
| accumulator | `--physical-envs 16` (rounds=4) — required so 64 fits AM18 |
| init | `../has_pokedex_nballs.state` |
| budget | `--total-timesteps 35061760` (214 mega-updates; one job, no splits) |
| seed | 0 |
| lineage / session | `t25_acc64_dexballs_s0` → `runs_t25_acc64_dexballs_s0` |
| job file | `v2/jobs/039_t25_acc64_dexballs_s0_35m.json` |

Wall estimate @ ~954 SPS (job 030 avg): **~10.2 h**.

## Launch (AM18)

Queue is empty after 030; only this job should be in `v2/jobs/`.

```bash
cd ~/dev/PokemonRedExperiments/v2
# terminal A
./observe.sh
# terminal B
./run_queue.sh
```

No `POKERED_DATA` required (fresh run, not `--extend`). Peek TB before bed;
verdict in the morning from `env_stats_max/{max_map_progress,badge,event,unique_maps}`
and the explore map.

## Success / read of results (morning)

- **mmp ≥ 4** (Route 2) and climbing, or **badge ≥ 1** by 35M → cold-start/parcel
  path was a major drag; open follow-up on early-game incentives.
- **Still mmp=3 / badge=0** at 35M → wall is post-dex (matches ticket 24); Discord /
  author-ckpt comparison (ticket 24 follow-up) stays the main thread.
- Do **not** treat this as a full author repro: different init than v2’s `init.state`
  run to SS Anne; it is a controlled ablation of the early story.

## Comments

- 2026-09-14: ticket + job authored on AM18 while operator continues ticket 24 on
  the Mac. Job not launched by the agent.
