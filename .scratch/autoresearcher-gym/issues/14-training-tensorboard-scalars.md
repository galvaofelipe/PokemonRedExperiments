# 14 — Training TensorBoard scalars that match the Score language

**What to build:** Frozen training-time TensorBoard (and the env aggregates it
reads) so future v3 runs are readable the way overnight v2 was not. Telemetry
files already store per-step map id, raw event-flag count, badges, dex, and
levels (issue 03). The scorer already counts `unique_maps` (issue 02). The
callback still averages categorical map/x/y ids, publishes scaled training
reward under `env_stats/event`, and only dumps game stats when env 0 finishes
an episode (~1.31M steps). Fix the live scalars; do not change the PPO reward
or any in-flight v2 run.

This is logging only. New tags are additive so issue 12 can still overlay
v2-comparable `env_stats/*` keys. `agent_stats` keys that `parity_v2_v3.py`
compares stay stable; extra live fields live on separate env attributes (or
as additional keys with the parity check updated to allow a superset).

**Blocked by:** 03 — telemetry recording (writer exists; dashboard is out of
03's scope).

**Status:** ready-for-agent

- [ ] TensorBoard records `unique_maps` (distinct map ids this episode), mean
      and max across envs, plus a Text dump of sorted map names — not the mean
      of raw map ids
- [ ] Raw RAM counts are published next to shaped reward: `event_count` (flag
      popcount) beside `reward/event`; `badge` stays a raw count; explore
      tiles stay `coord_count` with the shaped term under `reward/explore`
- [ ] Named milestone bits are 0/1 scalars (`flags/got_pokedex`,
      `flags/route22_rival`, and the split names issue 05 will freeze), with
      `env_stats_max` showing whether any env hit them; `trajectory/all_flags`
      JSON remains for forensics
- [ ] Game stats flush on the same cadence as PPO logs (~every rollout / 20k
      timesteps), not only when env 0 is `done`
- [ ] Mean of `map` / `x` / `y` / `step` is no longer published (last or max
      is fine if a position debug tag is still wanted)
- [ ] Unbounded per-step `agent_stats` history is replaced by a last snapshot
      plus running aggregates (unique maps set, max map progress, max flags).
      Parity still compares the last row
- [ ] An episode-return curve exists (`reward/episode_return` or an SB3
      Monitor wrapper). There is still no `rollout/ep_rew_mean` today
- [ ] No change to Editable `train.py` reward weights, episode length, env
      count, or v2 session directories. Land before issue 07 or re-hash the
      frozen manifest after

## Why this is its own ticket

Issue 03 records the gzip. Issue 04 puts `unique_maps` on the eval Scorecard.
Issue 05 times speedrun splits. Issue 10 draws the live map. None of those
own `v3/frozen/tensorboard_callback.py`, which is what a human actually stares
at during a cadence run.

## Comments

- 2026-09-11: written from the overnight v2 read (b45 / b11m / b35m). b35m
  continues unmodified. Details: INBOX.md and the overnight-runs canvas.
