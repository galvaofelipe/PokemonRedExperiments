# 04 — Eval protocol + Scorecard

**What to build:** The Frozen eval protocol (spec D4/D6): load a trained
checkpoint, run the eval suite — the two save states already on disk (fresh game,
early-progression) × 3 seeds × 16,384-step cap — with the training reward and
exploration machinery disabled, score each episode with the Frozen scorer, and
emit a per-run machine-readable Scorecard: Score (mean across episodes, plus
max), component breakdown, and maps/dex/level stats. The Scorecard records
`score_version`, `eval_suite_version`, and the init states used, so old runs
stay interpretable as the suite grows.

**Blocked by:** 02 — Frozen scorer; 03 — telemetry recording.

**Status:** ready-for-human

- [x] Running eval on a checkpoint from a short v3 training run produces a
      Scorecard with Score mean/max and the full component breakdown
      (`v3/verify/eval_smoke.py`: checkpoint `runs/smoke/poke_40960_steps`,
      Scorecard com mean/max + components por episódio)
- [x] Eval episodes run with training reward disabled — only the Frozen scorer
      counts (Frozen `NullReward` em `v3/frozen/eval/null_reward.py`; env core
      intocado; scoring via read-back da telemetria → `score_snapshots`)
- [x] The same checkpoint evaluated twice with the same seeds produces the same
      Score (paired-seed determinism) (`eval_smoke.py`: duas execuções →
      mean/max idênticos; seeds derivadas via sha256(suite:state:idx))
- [x] Scorecard carries score version, eval suite version, and init states
      (`score_version`, `eval_suite_version`, `init_states` com sha256, mais
      commit + checkpoint sha256)
- [x] Suite membership is data-driven: adding a new save state file extends the
      suite without code changes (`v3/frozen/eval/suite.json` + `states/`;
      sha256 validado no load, baseline desconhecido rejeitado)

## Comments

- 2026-09-11: “maps/dex/level stats” on the Scorecard should include the Score
  component `unique_maps` (issue 02) and, if cheap, the map names — never a
  mean of map ids. That is the eval answer to INBOX (“are we scoring how many
  map names each game saw?”). Training TensorBoard for the same number is
  issue 14.
