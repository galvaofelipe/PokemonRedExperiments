# 14 — Implementar o acumulador de batches na v2

Type: task
Status: ready-for-human
Blocked by: —

## Question

Implementar a spec do ticket 06 (Answer completo lá — ler antes de começar):

1. **`v2/accumulator_ppo.py`** (novo, ~80–120 linhas): `AccumulatingPPO(PPO)`
   com override de `learn()` — R × `collect_rollouts` stock com política
   congelada, chained buffer com a interface mínima do `PPO.train()` stock, um
   `train()` por mega-update. Cadência: `_update_current_progress_remaining` e
   `_dump_logs` uma vez por mega-update; episódios atravessam rounds; bootstrap
   por round = chunk do autor.
2. **`v2/baseline_fast_v2.py`**: `--num-envs` vira streams lógicas;
   `V2_PHYSICAL_ENVS` / `--physical-envs` como teto físico (ausente → físico =
   lógico, retrocompatível); `rounds = lógico ÷ físico` com erro claro se não
   divisível; warning de OOM olha o físico; print da geometria resolvida;
   escolha da classe nos ramos de load (`:262`) e construtor (`:271`).
3. **Validação** (as três camadas da spec): `v2/tests/test_accumulator_gae.py`
   (GAE à mão vs subclass, γ=0.997 λ=0.95); smoke ~100k com 64 lógicas
   (8×8 rounds) — mega-update a cada 163.840, KL/entropy/EV sãos, RAM < ~12 GB;
   smoke rounds=1 ≡ stock.

Agente implementa e roda as três camadas; operador revisa. Não tocar em
`red_gym_env_v2.py`, callbacks nem `run_queue.sh`. RAM estourando → registrar
e discutir fallback `np.memmap` antes de implementar.

## Result

Implementado em 2026-09-13; as três camadas de validação passaram. Falta a
revisão do operador.

**Código** (commit próprio nesta branch):
- `v2/accumulator_ppo.py` (novo): `AccumulatingPPO(PPO)` com override de
  `learn()` (espelha o loop stock do SB3 2.3.2, marcado em comentário) e
  `ChainedRolloutBuffer` zero-copy — view que encadeia os R buffers de round e
  expõe `get(batch_size)`/`values`/`returns`, a interface exata que
  `PPO.train()` toca (verificado contra `ppo.py:207,288`). GAE stock por round
  com bootstrap na fronteira; `_dump_logs` e `_update_current_progress_remaining`
  uma vez por mega-update; `rounds=1` delega ao `learn()` stock.
- `v2/baseline_fast_v2.py`: `--num-envs` = streams lógicas; `--physical-envs` /
  `V2_PHYSICAL_ENVS` (ausente → físico = lógico, retrocompatível);
  `resolve_geometry()` com `SystemExit` claro se não divisível; warning de OOM
  e `SubprocVecEnv`/`ResourceCallback` olham o físico; print
  `logical=64 physical=8 rounds=8 update=163840`; `ppo_cls` nos dois ramos.
- Desvios conscientes da lista "só" do 06 (registrados no code review):
  `--sps` default agora usa o físico (throughput escala com subprocessos, não
  com streams lógicas — sem isso `--minutes` erraria 8×) e `ResourceCallback`
  recebe o físico (atribuição de RAM/tempo por env é por subprocesso). Ambos
  bit a bit idênticos quando físico = lógico.

**Validação**:
1. `v2/tests/test_accumulator_gae.py` (4 testes, primeira suíte pytest da v2;
   rodar de `v2/` com `../.venv/bin/python -m pytest tests/`): GAE à mão
   (γ=0.997, λ=0.95) vs buffers de round com bootstrap de fronteira capturado
   por spy — confere; gather do chained buffer exato; cadência stock com
   rounds=1 (`_n_updates` 3× vs 1×); `resolve_geometry`.
2. Smoke `runs/smoke_acc_64` (64 lógicas, 8 físicas × 8 rounds,
   `V2_PHYSICAL_ENVS=8`, 200k pedidos): mega-updates logados em 163.840 e
   327.680 (`iterations` 1 e 2), `approx_kl=0.0097`, `entropy_loss=-1.94`
   (≈ln 7, política ~uniforme no init), `explained_variance=0.013`,
   `clip_fraction=0.05` — sãos. Pico RSS 5.004 MB « 12 GB (chained zero-copy;
   fallback memmap não necessário).
3. Guarda stock `runs/smoke_stock_8` (`--num-envs 8`, sem env var):
   `rounds=1 update=20480`, updates em 20.480/40.960/61.440 — cadência
   idêntica ao stock.

**Code review** (dois eixos, sub-agentes): Standards sem violações duras
(smells corrigidos: `--physical-envs 0` caía em falsy-shortcut — agora erro
explícito; loop de gather duplicado extraído). Spec sem violações; os dois
desvios (b) acima documentados.

**Próximo**: ticket 15 desbloqueado (operador dispara a fila da 3ª célula).
