# 03 — Per-step telemetry recording

**What to build:** Every v3 run (training or eval) records per-decision-step
telemetry per env, gzipped: step, x, y, map id, badges, event-flag count, dex
seen/caught, party level sum, and the in-game play clock (hours/min/sec/frames —
plain binary per the disassembly). This is the shared foundation for replay,
split timing, live visualization, and Audit. Recording is always on; live
streaming, when it exists, is a rebroadcast of this same data.

**Blocked by:** 01 — v3 scaffold + Seam split.

**Status:** ready-for-human

- [x] A short run leaves one gzipped telemetry file per env per episode
- [x] Records contain all fields above, with the play clock decoded from the
      verified addresses
- [ ] Recording overhead does not measurably reduce training throughput (SPS)
      — PENDENTE (human): rodar o A/B real (telemetria on vs
      `V3_TELEMETRY_OFF=1`, `--total-timesteps` fixo, fps do SB3) depois que o
      b35m terminar e a máquina ficar livre. Microbench: bulk read + gzip ≈
      0.02 ms/step (~0.5% do tempo de emulação).
      Preview 2026-09-11 (b35m rodando, 6 envs × ~2.8 min cada, back-to-back):
      avg_sps 450.8 on vs 463.3 off (ResourceCallback; −2.7% on, dentro do
      ruído de carga — fps por iteração do SB3 emparelhado chegou a dar on à
      frente em 4 de 4 pontos). Sem regressão mensurável no preview; a
      medição definitiva continua pendente.
- [x] Format is close enough to the legacy agent-stats cadence that existing
      trajectory renderers can be adapted without re-recording

## Implementation notes (2026-09-11)

- Writer + reader + format: `v3/frozen/telemetry.py`. One chunked-gzip file per
  env per episode at `<session_path>/telemetry/<instance_id>_ep<reset:04d>.telemetry.gz`.
  Chunks: tag 0x00 header (magic `V3TEL1` + JSON: schema_version, instance,
  episode, snapshot size, CSV columns), 0x01 decoded CSV row, 0x02 raw 2275-byte
  snapshot. Gzip written with `mtime=0` so fixture regeneration is byte-identical.
- Decided jointly (human + coordinator): record BOTH the raw snapshot window
  (canonical; replays straight into `frozen.scorer.core.score_snapshots` — Audit
  needs the individual event/dex bits, which a count cannot reconstruct) AND a
  decoded CSV row (superset of legacy `agent_stats` columns incl. `last_action`
  for replay, plus dex counts and the 5 raw play-clock bytes). All decoded
  values are RAW (no baseline subtraction, no museum mask, no level cap —
  scorer logic stays in the scorer); derived from the same per-step snapshot,
  never from the Editable reward object.
- Recorder is instantiated unconditionally inside `RedGymEnv` (Frozen core) —
  not a wrapper — so the Editable `train.py` cannot bypass it. One bulk slice
  read per step (`memory[0xD163:0xDA46]`), popcounts via
  `int.from_bytes(...).bit_count()`, streaming writes, flush every 512 steps.
  Human-only kill switch `V3_TELEMETRY_OFF=1` for the A/B benchmark skips the
  RAM read too.
- `v3/train.py`: one-line change, `instance_id=str(rank)`, so telemetry files
  map to vec-env rank.
- Tests: `v3/tests/test_telemetry.py` (reader-only, no pyboy at test time) +
  generator `v3/verify/capture_telemetry_fixtures.py` (independent decode;
  scenarios `telemetry_init`, `telemetry_has_pokedex`, 2 episodes each).
  Includes the contract test: telemetry snapshots feed `score_snapshots`
  directly and match scoring of independently captured snapshots.
- Verified independently by coordinator: 21/21 pytest green, parity
  `PASS: 512 steps`, smoke `v3/verify/telemetry_smoke.py` (2 envs × 300 steps),
  fixtures byte-identical across regenerations, kill switch leaves zero files.
- v2 untouched (the `v2/jobs/002_b11m.json` deletion in git status is the
  human's queue rotation to done/, not part of this work).

## Comments

- 2026-09-11: overnight v2 TensorBoard was unreadable (mean of map ids, scaled
  `event` reward, stats only on env-0 done). Raw fields this ticket records are
  enough to derive unique maps and flag counts after the fact. Live scalars
  belong in issue 14, not a reopen of 03. Do not change in-flight v2 runs.
