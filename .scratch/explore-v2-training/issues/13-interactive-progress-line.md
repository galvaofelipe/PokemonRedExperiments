# 13 — Linha de progresso no watch do checkpoint (honrar debug)

Type: task
Status: ready-for-agent

## Question

Rodar `v2/run_pretrained_interactive.py` contra o zip do autor
(`runs/poke_26214400`) só dá a janela do PyBoy. Pra saber se bateu Brock / entrou
em Mt. Moon / comprou Magikarp foi preciso pausar e abrir o trainer card. O
`env_config` já manda `'debug': False` e `'print_rewards': True`, mas o env v2
**não lê `debug`** e o printer que existe está morto.

Conserto pequeno: uma linha de progresso no stdout durante o watch, lida do
`agent_stats` que o env já calcula. Sem telemetria gzip, sem Scorecard, sem
mudar a v3.

## O que está quebrado hoje

- `v2/run_pretrained_interactive.py` coloca `'debug': False` no config (linha ~67)
  e não expõe `--debug`. `baseline_fast_v2.py` já tem `--debug` e passa
  `config["debug"]`.
- `v2/red_gym_env_v2.py` nunca acessa `config["debug"]`. No v1
  (`baselines/red_gym_env.py:29`) o campo é guardado em `self.debug` e também
  nunca é consultado — dead config nos dois.
- `print_rewards` *é* lido, e `save_and_print_info` imprime
  `step` + componentes de reward + `sum`. A chamada em `step()` está comentada
  (`# self.save_and_print_info(...)`). Descomentar **não** resolve: a mesma
  função grava `curframe_*.jpeg` a cada 50 steps — inutilizável a 100–300×.

Campos já presentes em `append_agent_stats` (commit `62e198c` / ticket 12):
`step`, `map`, `max_map_progress`, `unique_maps`, `dex_seen`, `badge`, `event`,
`levels_sum`, `coord_count`, `deaths`. Relógio in-game (h:m do trainer card,
2:13 no watch de 2026-09-12) **não** está no dict; só incluir se for um
`read_m` trivial e já conhecido. Não inventar endereço.

## O que construir

1. **Env.** `config["debug"]` (default `False` se a chave faltar, pra não
   quebrar callers). Quando True, imprimir **uma** linha `\r` no stdout, no
   máximo a cada N steps **ou** quando `map` / `badge` / `max_map_progress`
   mudar — o que vier primeiro. N default 64 (um pouco mais que 1s de jogo a
   `action_freq=24`). Conteúdo mínimo:

   `step map mmp unique_maps badge event dex_seen levels_sum`

   Sem jpeg, sem `plt.imsave`, sem abrir `save_and_print_info`. Não descomentar
   aquele caminho.

2. **Interactive.** `--debug` / `--no-debug` (BooleanOptionalAction), default
   **True** neste script — o ponto do watch é ver progresso. Passar
   `debug=args.debug` no `env_config`. `--speed` já existente fica como está.

3. **Treino.** `baseline_fast_v2.py --debug` continua default False. Não
   spammar o log das jobs da fila. Se alguém ligar `--debug` numa run de 8
   envs, uma linha por env é aceitável; não precisa de lock sofisticado.

Fora de escopo: persistir `agent_stats` em disco, Scorecard, splits, v3 eval
(obs 2560 bits — o zip do autor não carrega lá), cap de `max_steps` no
interactive (`2**23` é outro problema).

## Acceptance

- [ ] `python run_pretrained_interactive.py --checkpoint runs/poke_26214400 --speed 0`
      imprime linhas de progresso sem flag extra
- [ ] `--no-debug` silencia a linha
- [ ] Mudança de mapa ou de badge aparece na próxima linha, não só no tick de N
- [ ] Nenhum jpeg novo em `session_*` por causa desse printer
- [ ] `baseline_fast_v2.py` sem `--debug` não muda o stdout das jobs
- [ ] `config` sem chave `debug` não quebra o env
