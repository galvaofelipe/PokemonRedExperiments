# 23 — Dieta de RAM do acumulador: uint8 ponta a ponta + free-after-train

Type: task
Status: claimed
Blocked by: — (21 resolvido 2026-09-14)

## Question

A auditoria do ticket 21 (achados verificados independentemente, ver comentários
lá) achou a causa raiz do gap de 5× na RAM por amostra e quantificou as
alavancas. Este ticket é a implementação das duas alavancas principais, sem
mudar a semântica de treino:

1. **uint8 ponta a ponta** — o `DictRolloutBuffer` do SB3 2.3.2 hardcoda
   `np.float32` pra toda obs key (`.venv/.../stable_baselines3/common/buffers.py:747`),
   ignorando `space.dtype`. Buffer deve alocar obs no dtype declarado do
   observation_space (uint8: screens/events/map) e o cast pra float32 acontece
   só no batch que vai pro forward da policy. Buffer de 88.368 → ~22.1 KB/amostra
   (**−10,9 GB** no acc64: 14,48 → 3,63 GB).
2. **Free-after-train** — hoje a chain da mega-update n fica viva durante toda a
   coleta de n+1 (só cai no reassignment de `accumulator_ppo.py:159`). Soltar a
   referência logo após `self.train()` remove a janela double-alive da coleta
   (**−14,5 GB** de pico de coleta no acc64: ~34 → ~19,5 GB de demanda).

Com as duas, o acc64 inteiro cabe em ~9 GB de train / ~12,5 GB de coleta —
sobra pra até 80 streams lógicas nas 26 GB visíveis do WSL. memmap (alavanca 3
do ticket 21) fica fora do escopo; gather sem cópia e MALLOC_TRIM são
desprezíveis (medidos).

## Constraints

- **Semântica de treino inalterada**: mesmas amostras por mega-update, mesma
  matemática de update, mesmos checkpoints (o rollout buffer não é serializado).
  Mudança é puramente de representação em memória e lifetime de objetos.
- Escopo v2 apenas (`v2/accumulator_ppo.py` + arquivos novos em `v2/`). Não
  tocar `v3/`, `baselines/`, jobs, runs.
- Atenção ao pós-train: se `_dump_logs`/callbacks leem `self.rollout_buffer`
  depois do `train()`, o free tem que preservar o que o logging precisa.
- O `ChainedRolloutBuffer` concatena values/returns/advantages (12 B/amostra) e
  serve obs dos round buffers — o cast uint8→float32 deve acontecer na montagem
  do batch, não em cópia integral da chain.

## Acceptance

1. Testes existentes passam: `cd v2 && ../.venv/bin/python -m pytest tests/`
   (17 hoje) + testes novos que travem: (a) dtype uint8 das obs no buffer,
   (b) chain antiga liberada após o train (referência None / refcount).
2. Verificação medida: rerodar
   `.venv/bin/python v2/mem_audit_t21.py --tag post_diet --num-envs 8 --physical-envs 4 --n-steps 256 --total-timesteps 8192`
   e o `audit_breakdown.json` deve mostrar obs.* dtype uint8 e round_buffer
   ~22,6 MB/1024 amostras (era 90,5 MB); pico de coleta sem double-alive.
3. Smoke train na geometria pequena completa e loga normalmente (SPS, losses).
4. Números de antes/depois registrados em `docs/perf/am18.md` e comentário de
   fechamento neste ticket.

## Comments

- **2026-09-14:** ticket aberto a partir dos achados verificados do 21. Medição
  de referência (antes): `v2/runs_scratch_t21_{small,verify}/`. Instrumentação
  pronta em `v2/mem_audit_t21.py` + `v2/analyze_audit_t21.py`. Implementação
  delegada ao Cursor (grok); verificação independente pelo agente principal
  antes de fechar.
- **2026-09-14 (implementação, Cursor):** as duas alavancas estão em
  `v2/native_dtype_rollout_buffer.py` + `v2/accumulator_ppo.py`. Pytest
  `cd v2 && ../.venv/bin/python -m pytest tests/` → **23 passed** (17
  anteriores + 6 novos: dtype uint8 no round buffer, nbytes 22.671.360/1024,
  chain/round buffers dead após `train()`). Smoke
  `mem_audit_t21.py --tag post_diet` (8/4, n_steps 256, 8192 steps):
  `round_buffer` obs **22.671.360 B / 1024 amostras** (era 90.488.832);
  screens/map **uint8**, events/badges **int8** (`MultiBinary.dtype`, 1 B —
  não uint8; mesmo tamanho); chain **22.180 B/amostra** (era 88.408). Timeline
  PSS de coleta pós-MU1 fica plana no PSS de `post_train` (525 MB) — sem
  double-alive. Treino loga fps/entropy/loss. Números também em
  `docs/perf/am18.md`. Desvio consciente: events/badges seguem `space.dtype`
  (int8), não um cast forçado pra uint8. Sem commit (working tree pro agente
  principal revisar).
