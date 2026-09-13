# 10 — Live map visualization

**What to build:** A local instance of the pokerl-map-viz tool (the cloned repo's
frontend patched to the local websocket, server run locally) with v3 telemetry
rebroadcast to it: each env appears as a sprite on the stitched Kanto map, with
metadata identifying the run (job name as user, env id, color) so multiple runs
are distinguishable and filterable. Streaming is optional per job and always
secondary to recording — the websocket dropping loses nothing.

**Blocked by:** 03 — telemetry recording.

**Status:** ready-for-agent

- [ ] During a training run, all envs appear live on the local map, labeled by
      run and env id
- [ ] The frontend connects to localhost, not the public server
- [ ] Training throughput is unaffected when streaming is off; degraded
      gracefully (run continues) when the viz server is down
- [ ] Two concurrent/overlapping runs are distinguishable via metadata filtering
