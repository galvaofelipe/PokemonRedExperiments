# STUB — explore-v2-training

> Stub pra ser refinado pelo wayfinder. Objetivo provisório (a definir):
> **validar que o `red_gym_env` da v2 (e, por extensão, o da v3) dá condições a
> uma PPO de convergir — de certa forma reproduzir os resultados do autor/paper
> original.**
>
> Delimitação acordada (2026-09-12): reproduzir a **dinâmica**, não a escala
> literal — compatível com os limites de hardware (este Mac 8 envs, AM18) e
> timeboxes razoáveis. A run de reprodução do artefato real (~440M steps)
> é viável (~7 dias neste Mac; ~19 EUR / 3,5 dias numa Hetzner CCX33) mas
> fica pra depois — ver "Escala de reprodução do autor".
>
> Cópia limpa do repo original p/ navegação: `~/dev/pwhiddy_pre_readonly/`
> (evita escavar o histórico git deste repo).

## O que é a v2

Fork do baseline do pwhiddy com runner parametrizado:

- Env: `v2/red_gym_env_v2.py` (PyBoy, Pokémon Red)
- Runner: `v2/baseline_fast_v2.py` — flags: `--num-envs`, `--max-steps`
  (duração do episódio em steps; 8.959 steps ≈ 1 game-hora), `--n-steps`
  (horizonte PPO; default derivado `max_steps // 64` reproduz as baselines
  antigas), `--total-timesteps`/`--minutes`, `--early-stop`,
  `--early-stop-survival` (default 0.05), `--seed`, `--session-path`, `--backup`
- Fila: `v2/jobs/*.json` → `v2/run_queue.sh`; observação: `v2/observe.sh`
  (watch_progress :8765 + tensorboard :6006 via symlink farm `.tb_logs/`,
  inclui jobs done)
- SPS ≈ 700–760 medido com 8–10 envs nesta máquina (desvio pequeno vs 720
  assumido; tratar SPS como quase-constante)

## Variáveis de controle (o que faz sentido controlar)

1. **Duração do episódio** (`--max-steps`, proxy de game-hours)
2. **Duração total da sessão** (`--total-timesteps`)
3. **Frequência de atualização da policy** (`--n-steps`)
4. **Regra de faint** (`--early-stop` + `--early-stop-survival`):
   - `nfr` = sem early-stop (faint nunca corta; jogo roda o blackout, agente
     volta do pokecenter dentro do mesmo episódio)
   - `fr5` = 95% dos episódios cortam no faint (terminated), 5% continuam
     (sorteio por episódio no reset)
   - `fr100` = survival 1.0 — **mecanicamente equivalente a `nfr`**
5. Secundárias fixas por ora: seed 0, n_steps 2560, SPS ~720
   (teto prático desta máquina ≈ 750 SPS agregado — ver "Fork vs upstream")

## Fork vs upstream (investigado 2026-09-12, clone limpo em `~/dev/pwhiddy_pre_readonly/`)

- **Hiperparâmetros PPO: zero desvio do fork.** batch 512, epochs 1,
  gamma 0.997, ent_coef 0.01, lr 3e-4 (default SB3), n_steps =
  `ep_length // 64` — a fórmula derivada é **literal do upstream**
  (`train_steps_batch = ep_length // 64`), o fork só expôs `--n-steps`.
  Ou seja: manter 2560/…//64 = manter o valor do autor. (Ref.: autor rodava
  `num_cpu = 64` envs.)
- **Level reward comentado é UPSTREAM, não nosso.** Commit do próprio autor
  `2f79c5a` (2025-02-27): *"as a result of marco's experiments, removed
  level reward and started from init state. now simpler and can go all the
  way from the very start to ss anne!"* — o mesmo commit moveu init_state
  `has_pokedex_nballs.state` → `init.state`, reduziu heal ×30→×10 e stuck
  threshold 300→600. A v1 (`baselines/red_gym_env.py`) mantém level ativo;
  a divergência de shaping v1↔v2 é deliberada do autor. **Não desfazer.**
- **Seed 0 é convenção herdada, não decisão de reprodutibilidade.** Upstream
  fixa `seed=0` hardcoded em `make_env`; o fork só virou flag (`--seed`,
  commit local `d7aaa29`). A v3 usa seeds determinísticas só pra **eval**
  (`v3/frozen/eval/seeds.py`, paired-seed por suite/state/index) —
  `v3/program.md` não menciona reprodutibilidade de treino. Multi-seed de
  treino continua sendo lacuna nossa (ver abaixo).
- **Teto de SPS: CPU + head serial, não RAM nem GIL.** Medido: 8 envs →
  ~691–736 SPS (86–92 SPS/env, ~34,7–37x speedup); 10 envs → ~747–761 SPS
  (75 SPS/env, ~30x). +25% envs rendeu só +2–8% SPS: com 8 workers em 10
  cores cada emulador já tinha ~1 núcleo; com 10 + head + OS há time-slicing
  e a CPU média até CAI (~647% vs ~726%). O head é serial (round-trip de
  pipe por env por step + update PPO). RAM ok (520–790 MB/env, sem swap).
  **Implicação pra matriz:** cells de 8 vs 10 envs diferem em batch/update
  (20.480 vs 25.600) — confound conhecido; daqui pra frente padronizar.

## Lacunas pra próxima rodada (não bloqueiam a matriz atual)

- **Seed**: 2–3 seeds nas células-chave antes de qualquer afirmação de
  convergência.
- **n_steps**: nunca variado; interage com episódios curtos (fr5 chegou a
  episódios de ~400 steps < 1 rollout de 2.560 — sinal de terminated dilui).
- **watch_progress.py**: job args já chegam em `load_jobs()` mas `num_envs`
  não é exibido — adicionar coluna/linha "Envs" (~linhas 109 e 356).

## Matriz de runs

| run | total | episódio | faint | envs | status |
|---|---|---|---|---|---|
| b45 | ~1,94M | 18h | nfr | 8 | done (era `--minutes 45`) |
| b11m | 11M | 18h | nfr | 8 | done |
| b35m | 35M | 18h | nfr | 8 | done |
| b2m_2hep | 2M | 2h | nfr | 10 | done |
| b2m_fr5 | 2M | 18h | fr5 | 10 | done |
| b11m_2hep | 11M | 2h | nfr | 8 | done |
| b11m_fr5 | 11M | 18h | fr5 | 8 | done |
| **b2m_2hep_fr5** | 2M | 2h | fr5 | 10 | done (008) — completa a matriz 2M |

### Resultado b2m_2hep_fr5 (dose-resposta do P1)

188 episódios: 110 wipes (58,5%), 78 max_steps; survival 5,85% ≈ 5% ✔.
Duração dos wipes cai DENTRO da run de 45 min: média 9,6k → 4,0k steps
(mín 814); coord_count **decaindo** (1º⅓ 263 → últ⅓ 217), max_map_progress
preso em 1. É a pior célula — a pinhata reabastece a cada 2h **e** a cada
morte. Contraste: b2m_fr5 (18h) teve ZERO wipes na mesma janela de 2M (o
farm só aparece nela em 11M); b2m_2hep (nfr) teve ~2–3 mortes/env e
explorou mais (progress 2, coord até 347). **Quanto mais frequente o reset
do mundo, mais rápido o farm emerge** — confirmação dose-resposta do P1.

### Escala de reprodução do autor (corrigido 2026-09-12)

105B steps é só o default uncapped do script (`ep_length × 64 envs ×
10.000` = "rodar pra sempre"). O artefato publicado real (derrota Brock,
chega em Mt. Moon) é **~440M steps (~50k horas simuladas) — ~0,4% de 105B**.
Reproduzir = 440M. Custos estimados:

- Este Mac (8 envs, ~720 SPS): ~7 dias, ~US$2–3 de eletricidade
- AM18: ~4–5 dias
- Hetzner CCX33 (16 cores): ~19 EUR, ~3,5 dias ← sweetspot
- Hetzner CCX43 (16 vCPU dedicados, 64GB): US$20–40, 1,2–14 dias

Em máquina com mais cores: ou se implementa o **acumulador de batches**
(8 rounds de 8 envs × 2.560 steps, GAE por segmento, um update por 64
segmentos — reproduz a geometria 64×2.560 do autor; SB3 não faz out of the
box) ou se aceita mais envs que cores com perda de eficiência. Nota de
rodapé por ora — não implementar agora.

Sessões: `v2/runs_<nome>/`; backups: `v2/baselines/<nome>/`.

## Problemas mapeados (reward hacking em `v2/red_gym_env_v2.py`)

### P1 — Recompensas renováveis a cada reset de episódio

`reset()` recarrega `init.state` (linha ~132) e zera `seen_coords`/
`explore_map`, `max_event_rew`, `total_healing_rew`, `base_event_flags`
(linhas ~137–175). Componentes ativos do reward (`get_game_state_reward`,
linha ~555): `event` (×4), `explore`, `heal` (×10), `badge`, `stuck` (−0,05).
Todos (menos stuck) voltam a ser ganháveis quando o mundo reseta → o early
game vira pinhata renovável. Com gamma < 1, farmar o começo e morrer/resetar
rápido vence empurrar fronteira.

Evidência (b11m_fr5): 95,3% dos episódios terminam por wipe; duração média
dos wipes cai com o treino (44k → 3,6k steps; mín 399); policy aleatória de
controle não reproduz (mín 7.4k) → comportamento aprendido, não mecânico.
O b2m_2hep/b11m_2hep têm a mesma dinâmica em escala menor (pinhata reabastece
a cada 2h). **Reward densa no começo e esparsa depois: o gradiente de
recompensa anda ao contrário do gradiente de dificuldade do jogo.**

### P2 — Morte é barata (ou recompensada)

Penalidade de morte comentada (linha ~563); no caminho que continua, o
blackout cura 0→100% e dispara o `heal` reward — morrer dá recompensa de
cura. No caminho fr5, o `terminated` corta o bootstrap (punição), mas o
mundo reseta e a pinhata do próximo episódio domina o retorno.

## Direções em discussão (não implementadas)

- **(2) Explore persistente:** não zerar `explore_map`/`seen_coords` no reset
  — anti-farm estrutural pra exploração. Sozinha não basta (event/heal/badge
  também renováveis).
- **(3/B) Mundo contínuo:** wipe → corte de episódio (`terminated` pro PPO),
  blackout em autoplay sem reward, episódio novo começa no pokecenter. Nada
  reseta → nada é renovável. 5% continuam como hoje (agente joga a volta).
  Decisão pendente: fim por max_steps vira hard reset pro `init.state`
  (safeguard contra soft-lock, como as baselines antigas a cada 18h) ou
  playthrough 100% contínua.
- Alternativa A (permadeath roguelike): manter reset pro `init.state` nos 95%
  e tornar TODAS as fontes não-renováveis via máximos persistentes — mais
  remendo, e frontier com starter lvl 5 toda vez é brutal.

## Estado do código

Diff não-commitado na working tree (3 arquivos): `baseline_fast_v2.py`
(flags novas), `red_gym_env_v2.py` (early-stop funcional, gate
`party_was_alive` contra falso wipe na aquisição do starter, `died_count` no
término por wipe, `last_episode_info`), `tensorboard_callback.py`
(telemetria `episode/*` por env via `dones`, sem perdas — mora em
`<run>/histogram/`).

Testes de verificação em `/tmp/test_wipe_*.py` (edge, forced, false-positive)
e `/tmp/test_fast_wipe.py` (controle random vs wipes curtos).

## Pendências operacionais

- `v2/runs_smoke_tele/` (smoke de verificação da telemetria) pode ser apagado.
- INBOX.md: itens "Fix --early-stop" e "Add --n-steps" da seção v2 A/B estão
  concluídos (não editado, arquivo do usuário).
