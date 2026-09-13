# Handoff — explore-v2-training (wayfinder), pós-ticket 16

Data: 2026-09-13. Repo: `/Users/luizfelipegalvaoramos/dev/PokemonRedExperiments`.
**Substitui** `handoff-2026-09-13-post-ticket-15.md` (ticket 16 resolvido).

## O que fazer na próxima sessão

Invocar `/wayfinder` apontando pra este arquivo. Modo "work through the map", mapa em
`.scratch/explore-v2-training/map.md`.

**O alvo é o ticket 17** (execução da célula comparativa 11M, task) — mas o andamento
depende do operador:

- **Fase 1 pronta pra rodar**: jobs 022/023/024 em `v2/jobs/` (acc64 → B → A, seed 0,
  resume de 2M, alvo absoluto 10.977.280). Operador roda `cd v2 && ./run_queue.sh`
  (~4h cada, ~12h total). Se a fila já estiver rodando/terminada, verificar
  `v2/jobs/*.status` e `v2/logs/t16_*.log`.
- **Pós-fase 1**: extrair (`tb_extract.py` + `cell_table.py`, **offset +1.966.080**,
  flags = `event ÷ 2`), julgar seed 0 contra os MUST/SHOULD/COULD do Answer do 16
  (judgement call: agente no JSON, operador no TB), preparar jobs da fase 2
  (s1/s2, mesmo modelo — checkpoints de 2M já verificados nos 6 dirs).
- Tickets 07 (benchmark AM18) e 09 (veredito env-v3) continuam fronteira em paralelo.
- **Ticket 18 (novo, fronteira)**: telemetria de memória estava furada — `ps rss`
  ~4,5× abaixo do phys_footprint (Activity Monitor) e cega ao train(). Corrigido
  em `v2/resource_callback.py`/`watch_progress.py` (não commitado; vale só pras
  próximas runs). t16_acc64_s0 medida ao vivo: footprint 17GB num Mac 16GB. O 18
  re-baselina picos e decide dieta do acumulador; alimenta 07/08.
- Bloqueado: 08 (por 07; 16 optou por **não acoplar** a run N2 no runbook).

## Estado persistido (não re-investigar)

- **Ticket 16 resolvido** (2026-09-13): run maior = **célula comparativa de 3 braços
  em 11M** (A/B/acc64), resume do checkpoint exato de 2M, config verbatim t15, seeds
  em 2 fases (s0 primeiro, s1/s2 depois). Critérios MUST/SHOULD/COULD no Answer de
  `issues/16-accumulator-bigger-run-design.md`. Decisão explícita: **não acoplar**
  no runbook do 08 agora.
- **Fatos de resume verificados**: SB3 `learn()` default `reset_num_timesteps=True`
  → `--total-timesteps` é **adicional** e TB/checkpoints reiniciam em 0 (por isso
  session-paths novos `runs_t16_*` e offset +1.966.080 na extração). Resume do
  acumulador funciona via `ppo_cls.load` + `model.accumulation_rounds = rounds`
  (`baseline_fast_v2.py:303-314`). Checkpoint `poke_1966080_steps.zip` presente nos
  9 dirs (3 braços × 3 seeds).
- **Resume de B gasta o zip certo**: `runs_t05_g20480_s0` tem também
  `poke_2097152_steps.zip` (overshoot do job original de 2.000.000) — o job aponta
  explicitamente pro de 1.966.080, não usar `--resume` (pegaria o mais novo).
- **Custo medido/estimado**: ~3,6–4,2h por run de 9.011.200 steps (~600–710 SPS);
  acc64 pico RSS 6–8 GB. Fila serial, ordena por nome de arquivo (LC_ALL=C).
- **Ticket 15**: acumulador ADOTADO como geometria padrão; forma da trajetória é
  limitada pela contagem de updates (A côncava, B/acc chapados até ~1,2–1,5M) —
  catch-up vs deficit é o que a célula 11M responde (MUST 2 / SHOULD 1 do 16).
- **Ticket 14**: acumulador implementado, commit `b0883e1`.
- **Código não commitado** (decisão do operador, pendente desde o ticket 05):
  `v2/eval_pretrained.py` + `get_latest_stats()` em `red_gym_env_v2.py`,
  `watch_progress.py` e o resto da working tree. Jobs 022–024 também não commitados.
- **Escalas do eixo `event`**: t05/t15/t16 (reward_scale=0,5) → flags = `event ÷ 2`;
  eval_pretrained e runs antigas (reward_scale=1) → flags = `event ÷ 4`.
- **Ferramentas**: `tb_extract.py` e `cell_table.py` em
  `.scratch/explore-v2-training/scripts/`, rodar de `v2/` com `../.venv/bin/python`.
- **Referência de teto (checkpoint autor, congelado)**: @2h flags 17,5–20,
  coords 2.656–3.015, levels 12–14; `v2/runs_eval_peter{,_2,_3}/eval_summary.json`.

## Estado do mapa

- Resolvidos: 01, 02, 03, 04, 05, 06, 10, 11, 12, 13, 14, 15, 16.
- Fronteira: 07, 09, 17, 18. Bloqueados: 08 (por 07).
- v3 intocável (trabalho v3 vive no mapa autoresearcher-gym). Um ticket por sessão.

## Suggested skills

- **wayfinder** (obrigatório — este handoff é o argumento).
- **grilling** + **domain-modeling** — ticket 09 é HITL de conversa.
