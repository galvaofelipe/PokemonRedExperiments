# Handoff — explore-v2-training (wayfinder), pós-ticket 06

Data: 2026-09-13. Repo: `/Users/luizfelipegalvaoramos/dev/PokemonRedExperiments`.
**Substitui** `handoff-2026-09-13-post-ticket-05.md` (ticket 06 já resolvido).

## O que fazer na próxima sessão

Invocar `/wayfinder` apontando pra este arquivo. Modo "work through the map", mapa em
`.scratch/explore-v2-training/map.md`.

**Sequência esperada pelo operador**: (1) sessão implementa o ticket 14; (2) roda a
run do ticket 15 (operador dispara a fila; veredito judgement call com o agente);
(3) **a sessão seguinte abre o ticket 16** — atenção ao interplay com o 08, anotado
no corpo do 16: a run maior do 16 é a evidência de dose-resposta que o go/no-go do
runbook (08) consome; desenhar os dois isolados arrisca duas runs longas redundantes.
Se você está lendo isto **depois** de 14 e 15 resolvidos, o alvo é o 16 (dando zoom
no 08) — e os tickets 07/09 continuam fronteira em paralelo.

Fronteira (todos desbloqueados):
- **14 — Implementar o acumulador na v2** (task). Spec completa no Answer do 06 —
  ler antes. `v2/accumulator_ppo.py` novo (AccumulatingPPO, variante 1a chained
  buffer) + wiring em `baseline_fast_v2.py` (`--num-envs` = lógicas,
  `V2_PHYSICAL_ENVS`/`--physical-envs`, rounds = lógico ÷ físico). Validação em 3
  camadas: `v2/tests/test_accumulator_gae.py` (primeira suíte pytest da v2),
  smoke ~100k com 64 lógicas (8×8 rounds, RAM < ~12 GB), guarda do default
  rounds=1 ≡ stock. Agente implementa e roda as camadas; operador revisa.
- **07 — Benchmark AM18** (task; depende do operador/máquina AM18-WSL2).
- **09 — Veredito env-v3** (grilling HITL, ~80% investigado no corpo do ticket).

Bloqueados: 15 (por 14), 16 (por 15 — interplay com 08 no corpo do ticket), 08 (por 03, 07, 10 — 06 saiu).

## Estado persistido (não re-investigar)

- **Ticket 06 resolvido** (2026-09-13): **SIM pro acumulador**. Decisão, spec
  completa (desenho 1a, CLI lógico/físico, cadência, validação) e desenho da 3ª
  célula no Answer de `.scratch/explore-v2-training/issues/06-accumulator-decision.md`.
  3ª célula = validação, não gate; veredito judgement call (sem fórmula).
- **Ticket 05 resolvido**: 8×2.560 e 8×20.480 não se separam em 2M; tabelas e
  referência de teto (checkpoint do autor) no Answer do 05.
- **Código não commitado** (git estava limpo em `62e198c`): `v2/eval_pretrained.py`
  + acessor `get_latest_stats()` em `v2/red_gym_env_v2.py:494`. Decisão de commit
  é do operador.
- **Escalas do eixo `event`**: t05/treino reward_scale=0,5 → flags = `event ÷ 2`;
  eval_pretrained e runs antigas reward_scale=1 → flags = `event ÷ 4`.
- **Ferramentas**: `.scratch/explore-v2-training/scripts/tb_extract.py` (rodar de
  `v2/` com `../.venv/bin/python`). Fila: `v2/run_queue.sh` (snapshot no início).
  Jobs são `{name, args[]}` verbatim pro `baseline_fast_v2.py` (modelo:
  `v2/jobs/done/013_t05_g2560_s0.json`).
- **Referência de teto (checkpoint autor, congelado)**: @2h flags 17,5–20,
  coords 2.656–3.015, levels 12–14; badge ~2:10–2:20 de jogo; zero wipes em 72
  episódios. `v2/runs_eval_peter{,_2,_3}/eval_summary.json`.

## Estado do mapa

- Resolvidos: 01, 02, 03, 04, 05, 06, 10, 11, 12, 13.
- Fronteira: 07, 09, 14. Bloqueados: 08 (por 03, 07, 10), 15 (por 14), 16 (por 15).
- v3 intocável (trabalho v3 vive no mapa autoresearcher-gym). Um ticket por sessão.

## Termos novos no CONTEXT.md

Logical streams, physical envs, accumulation round, mega-update (seção Training
loop, junto de Update geometry).

## Suggested skills

- **wayfinder** (obrigatório — este handoff é o argumento).
- **tdd** — o ticket 14 inaugura a suíte pytest da v2; o teste de GAE vem antes.
- **grilling** + **domain-modeling** — tickets 09 e 16 são HITL de conversa.

## PS (2026-09-13, fim da sessão do ticket 14)

- **Ticket 14 resolvido** (`ready-for-human`, falta só a revisão do operador):
  `v2/accumulator_ppo.py` + wiring em `baseline_fast_v2.py` + primeira suíte
  pytest da v2 (`cd v2 && ../.venv/bin/python -m pytest tests/`, 4 verdes).
  Commit `b0883e1` — **só** os 4 arquivos do ticket; o resto da working tree
  (`red_gym_env_v2.py`, `watch_progress.py`, `eval_pretrained.py` etc.)
  continua não commitado, decisão pendente do operador.
- **15 desbloqueado**, com notas operacionais novas no corpo do ticket: jobs
  precisam de `--physical-envs 8` explícito (a fila não exporta a env var),
  overshoot de mega-update (usar `--total-timesteps 1966080` pro cutoff 2M),
  ~50–55 min wall por seed medidos no smoke.
- Smokes de validação em `v2/runs/smoke_acc_64` e `v2/runs/smoke_stock_8`
  (não deletar antes da revisão — são a evidência das camadas 2 e 3).
- Mapa: fronteira agora é 07, 09, 15. Bloqueados: 16 (por 15), 08 (por 07, 10).
