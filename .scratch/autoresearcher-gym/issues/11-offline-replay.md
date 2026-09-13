# 11 — Offline trajectory replay

**What to build:** Replay of a finished run from its recorded telemetry:
trajectories of all envs rendered onto the stitched Kanto map after the fact —
either by adapting the existing BetterMapVis renderers to the v3 telemetry format
or by feeding recorded messages through the viz frontend's offline format.
Distinct from live watching: this is the Audit/inspection tool for any past run.

**Blocked by:** 03 — telemetry recording.

**Status:** ready-for-agent

- [ ] A completed run's telemetry replays into a map trajectory visualization
      without the run being live
- [ ] Replay works for any run with telemetry, old runs included
- [ ] Per-env trajectories are distinguishable (color/label)
