# 12 — Telemetria v2: logar unique_maps e dex_seen

Type: task

Status: resolved

## Question

A rubrica (ticket 03) promoveu `unique_maps` e `dex_seen` a eixos secundários, mas a
v2 não os loga — o `agent_stats` (`v2/red_gym_env_v2.py:298-316`) só tem mmp,
coord_count, levels, event, badge, healr, deaths, hp. Adicionar (AFK, ~10–20 linhas):

- **`unique_maps`**: set cumulativo de map ids por episódio (`wCurMap` 0xD35E — já
  lido pro mmp em :620-628), logar `len(set)`; espelha a semântica da v3
  (`v3/frozen/scorer/core.py:78-82`, cap NUM_MAPS=248).
- **`dex_seen`**: popcount dos 19 bytes em 0xD30A–0xD31C, último byte mascarado com
  0x7F (bit 151 unused) — endereços verificados contra `~/dev/pokered`, constantes
  em `v3/frozen/ram_map.py`.

Ambos monótonos dentro do episódio por construção (set-once); zeram no reset junto
com o mundo, como os demais campos. Garantir que aparecem nos tags `env_stats/*` e
`env_stats_max/*` do tensorboard (via `agent_stats`, sem mexer no gating do callback).

Saída: campos logados + uma run curta de fumaça (~5–10 min) mostrando os dois tags
no tensorboard. Sem thresholds ainda — a calibração vem das primeiras runs do
ticket 05. Desbloqueia o 05.

## Answer

Resolvido em 2026-09-12. Implementação delegada via cursor-delegate (composer-2.5,
sessão `3b07a4be`), verificação própria. Commit `62e198c` — **só
`v2/red_gym_env_v2.py` mudou** (+15/−2); o callback não precisou de edição.

O que foi feito:

- **`unique_maps`**: `self.seen_maps = set()` em `init_map_mem()` (chamado no
  `reset`, junto com `seen_coords`); `update_map_progress()` adiciona o `wCurMap`
  (0xD35E) quando `< 248`; `append_agent_stats` loga `len(self.seen_maps)`.
  `update_map_progress()` foi movido pra logo depois de `run_action_on_emulator()`
  (antes de `append_agent_stats`) — sem isso o stat atrasaria 1 step. Verificado:
  `max_map_progress` só alimenta telemetria (campo `max_map_progress`), **não**
  entra em `get_game_state_reward`, então a reordenação não muda reward.
- **`dex_seen`**: `read_dex_seen()` faz popcount dos 19 bytes 0xD30A–0xD31C,
  último byte com máscara 0x7F, usando o helper `bit_count` já existente (:616).

Tags confirmados (nomes exatos): `env_stats/unique_maps`, `env_stats_max/unique_maps`,
`env_stats/dex_seen`, `env_stats_max/dex_seen`. O `TensorboardCallback` agrega
qualquer chave numérica de `agent_stats` (mean + max da frota, no done do env 0,
`v2/tensorboard_callback.py:42-52`) — fluxo automático confirmado no diff e na run.

Smoke run: `baseline_fast_v2.py --minutes 5 --max-steps 4096 --num-envs 2
--no-stream --session-path runs_smoke_t12` → 54.016 steps, 2,1 min wall (~437 SPS),
6 pontos de log (steps 8.192–49.152). Valores: `unique_maps` 2 → 4 (init.state em
Pallet; ≥ 1 e ≤ 248 ✓), `dex_seen` 0 (plausível: init.state é pré-pokédex e os
episódios de 4.096 steps mal saem de Pallet). Pegadinha do ticket 02 confirmada:
valores moram no campo `tensor` do proto; o EventAccumulator do tensorboard
resolve (script de leitura: `/tmp/read_t12_tags.py`). `runs_smoke_t12/` ficou no
disco — é coberto por `runs_*/` no .gitignore.

Desvio registrado: a delegação usou `248` literal em vez de importar `NUM_MAPS` da
v3 (escopo v2-only) — aceito, é a constante certa.

Fato pro ticket 05: a telemetria padrão da frota (mean/max no done do env 0) basta
pra rubrica; os dois eixos secundários já saem em qualquer run a partir deste
commit, sem flag extra.
