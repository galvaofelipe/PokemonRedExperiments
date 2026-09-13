# Handoff — explore-v2-training (wayfinder), pós-ticket 15

Data: 2026-09-13. Repo: `/Users/luizfelipegalvaoramos/dev/PokemonRedExperiments`.
**Substitui** `handoff-2026-09-13-post-ticket-06.md` (tickets 14 e 15 já resolvidos).

## O que fazer na próxima sessão

Invocar `/wayfinder` apontando pra este arquivo. Modo "work through the map", mapa em
`.scratch/explore-v2-training/map.md`.

**O alvo é o ticket 16** (desenho da run maior de validação do acumulador, grilling
HITL) — dando zoom no 08 antes: a run maior do 16 é a evidência de dose-resposta que
o go/no-go do runbook (08) consome; desenhar os dois isolados arrisca duas runs
longas redundantes (interplay anotado no corpo do 16). Os tickets 07 (benchmark AM18,
depende do operador/máquina) e 09 (veredito env-v3, grilling, ~80% investigado no
corpo) continuam fronteira em paralelo.

Bloqueado: 08 (por 07, 10 — 03 e 06 já saíram; verificar a linha `Blocked by:` do 08).

## Estado persistido (não re-investigar)

- **Ticket 15 resolvido** (2026-09-13): **acumulador ADOTADO** como geometria padrão
  das runs de referência. 3 seeds × 2M exato, sem problema claro (saúde, perf,
  estatística). Descoberta qualitativa central pro 16: a **forma** da trajetória é
  limitada pela contagem de updates — A côncava/estagna cedo; B/acc64 chapados até
  ~1,2–1,5M com subida tardia (ratio @1M÷@2M: A ~0,95 vs B/acc ~0,03–0,5).
  Catch-up vs deficit não se distingue em 2M. Tabela completa e saúde técnica no
  Answer/Comments de `issues/15-accumulator-cell-run.md`; screenshots do TB do
  operador em `.scratch/references/tensorboard_screenshots/`.
- **Ticket 14 resolvido**: `v2/accumulator_ppo.py` + wiring em `baseline_fast_v2.py`
  + suíte pytest (`cd v2 && ../.venv/bin/python -m pytest tests/`), commit `b0883e1`.
- **Tickets 05/06 resolvidos**: A/B não se separam em 2M; spec do acumulador e desenho
  da 3ª célula nos Answers respectivos.
- **Código não commitado** (decisão do operador, pendente desde o ticket 05):
  `v2/eval_pretrained.py` + `get_latest_stats()` em `red_gym_env_v2.py`, e agora
  também `watch_progress.py` e o resto da working tree. Commit do ticket 14
  (`b0883e1`) foi só os 4 arquivos do ticket.
- **Escalas do eixo `event`**: t05/t15 (reward_scale=0,5) → flags = `event ÷ 2`;
  eval_pretrained e runs antigas (reward_scale=1) → flags = `event ÷ 4`.
- **Ferramentas**: `tb_extract.py` e `cell_table.py` (novo, reproduz a tabela do
  ticket 05 — deaths = max da série, demais = valor no cutoff) em
  `.scratch/explore-v2-training/scripts/`, rodar de `v2/` com `../.venv/bin/python`.
  Fila: `v2/run_queue.sh`. Runs da 3ª célula em `v2/runs_t15_acc64_s{0,1,2}`,
  backups em `v2/baselines/t15_acc64_s{0,1,2}`.
- **Jobs do acumulador**: precisam de `--physical-envs 8` explícito (a fila não
  exporta a env var); `--total-timesteps` múltiplo de 163.840 pra cutoff exato
  (2M = 1.966.080). ~48 min/2M no Mac; pico RSS ~8 GB.
- **Referência de teto (checkpoint autor, congelado)**: @2h flags 17,5–20,
  coords 2.656–3.015, levels 12–14; badge ~2:10–2:20 de jogo; zero wipes em 72
  episódios. `v2/runs_eval_peter{,_2,_3}/eval_summary.json`.
- **ETA do watch**: média cumulativa, oscila no primeiro mega-update do acumulador
  (~2,5 min de train com steps congelados); estabiliza após 3–4 mega-updates.
  Comportamento esperado, não bug (analisado 2026-09-13).

## Estado do mapa

- Resolvidos: 01, 02, 03, 04, 05, 06, 10, 11, 12, 13, 14, 15.
- Fronteira: 07, 09, 16. Bloqueados: 08 (verificar linha `Blocked by:`).
- v3 intocável (trabalho v3 vive no mapa autoresearcher-gym). Um ticket por sessão.

## Suggested skills

- **wayfinder** (obrigatório — este handoff é o argumento).
- **grilling** + **domain-modeling** — tickets 09 e 16 são HITL de conversa.
