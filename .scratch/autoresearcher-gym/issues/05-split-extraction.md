# 05 — Split extraction + Scorecard integration

**What to build:** The 16 disassembly-verified split conditions (from the reviewed
splits draft, frozen as v3 data) plus a split extractor that reads telemetry and
reports each split's first-hit decision step and in-game play-clock time. Eval
Scorecards gain a splits section (achieved splits with timing); the same
extractor works on training telemetry so mid-training progress is inspectable.
Mt. Moon uses its combo condition (Super Nerd fight + Route 4 entry); all other
splits are single verified bits.

**Blocked by:** 03 — telemetry recording; 04 — eval protocol + Scorecard.

**Status:** ready-for-human

- [x] The frozen split data matches the verified draft (16 splits, route order)
      (`v3/frozen/splits/splits.json` byte-idêntico a
      `.scratch/references/splits_draft.json` — diff canonicalizado vazio;
      sha256 pinado em `v3/frozen/splits/manifest.json` e validado no load)
- [x] Extractor reports first-hit step + in-game time per achieved split from a
      telemetry file (`v3/frozen/splits/extractor.py`:
      `extract_splits_from_telemetry` → first_hit_step + game_time "H:MM:SS" +
      game_time_frames + clock_maxed; `v3/tests/test_splits.py`:
      `test_brock_first_hit`, `test_initial_at_step_0`)
- [x] Mt. Moon does not fire on the Super Nerd fight alone — the Route 4 entry is
      required (combo: sticky 0xD7F6-1 + map id 15; first-hit no step da entrada
      em Route 4; `test_mt_moon_positive` dispara no step 7,
      `test_mt_moon_negative` não dispara sem map 15; sem fallback de fóssil)
- [x] Scorecards include the splits section after this ticket
      (`SCORECARD_VERSION` → 1.1.0; `build_scorecard(episode_splits=...)` emite
      `splits` top-level {splits_version, order, achieved} + `splits.achieved`
      por episódio; `run_eval` sempre passa; sem `episode_splits` omite a seção
      → scorecards 1.0.0 continuam interpretáveis;
      `test_scorecard_splits_integration`)
- [x] Split timing is hardware-independent (in-game clock, not wall clock)
      (tudo derivado de `W_PLAY_TIME_*` 0xDA41–0xDA45 via `read_play_clock`;
      nenhum wall clock no caminho)

## Comments

- 2026-09-11: Decisões da implementação (aprovadas pelo humano no gap analysis):
  split set mora em `v3/frozen/splits/` com `SPLITS_VERSION` próprio (1.0.0);
  badge splits usam só o badge bit 0xD356 (event-flag alternativa fica como
  documentação no JSON); shape da seção inspirado em `.lss` (route order, tempo
  cumulativo no first-hit + `segment_time` = delta desde o split anterior **em
  completion order** — splits podem cair fora da route order, e segmentos nunca
  são negativos) — inspiração, não padrão rígido; comparação com WR pace (D17)
  NÃO entrou nesta ticket (é do Report). `initial: true` marca split já setado no step 0 (suite
  futura com milestone states). CLI de inspeção: `python -m frozen.splits
  <telemetry.gz|dir>` — cobre "extractor funciona em telemetria de treino".
  Verificação independente pós-delegação: 44 passed em `v3/tests/`,
  `v3/verify/splits_eval_full.py` assertou 0 splits nos 6 episódios reais de
  `v3/runs/eval_full/`, CLI conferida na mesma telemetria. A revisão humana do
  splits draft (open item da spec) aconteceu como parte desta ticket — o frozen
  data é verbatim do draft.
