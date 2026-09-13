# 19 — Sistema de checkpoints/resume (aposentar os gimmicks)

Type: task
Status: open
Blocked by: —

## Question

Continuar uma run hoje depende de gambiarras que já morderam e vão morder de novo
(quanto mais máquinas e runs paralelas, pior):

- **TB quebrado no resume**: SB3 `learn()` com default `reset_num_timesteps=True`
  loga a perna continuada do step 0. A extração exige offset manual (+1.966.080,
  registrado no handoff pós-16) e a série contínua só existe via
  `.scratch/explore-v2-training/scripts/tb_stitch.py` — 280 linhas de cirurgia de
  TFRecord com re-encode de scalars.
- **Seleção frágil de checkpoint**: `--resume` pega o zip mais novo — errado quando o
  dir tem overshoot (`runs_t05_g20480_s0` tem `poke_2097152_steps` além do
  `poke_1966080_steps` correto). Os jobs 022–024 contornam hardcodando o path exato.
- **Fixups manuais no load**: resume do acumulador exige reatribuir `n_steps`,
  `n_envs`, buffer size e `accumulation_rounds` na mão (`baseline_fast_v2.py:303-314`).
  Esquecer um vira bug silencioso de geometria.
- **Sem linhagem registrada**: nada persiste "run X saiu do checkpoint Y da run Z" —
  a célula 11M (ticket 17) depende disso por convenção verbal em handoff.
- **Referência não-portável**: jobs apontam paths locais de uma máquina
  (`runs_t05_*/...` só existe no Mac) e falham instantâneo na outra.

Desenhar e implementar o mínimo que aposenta os gimmicks:

1. **Checkpoint auto-descritivo**: sidecar `.json` junto ao zip com geometria
   (n_steps, logical/physical, accumulation_rounds), seed, env_config e **step global
   absoluto** da linhagem.
2. **Resume que restaura o relógio**: `reset_num_timesteps=False` ou offset explícito
   lido do sidecar → TB e nomes de checkpoint continuam a numeração global;
   `tb_stitch.py` aposentado.
3. **Ledger de linhagem**: arquivo pequeno em git (convenção dos job specs) mapeando
   run → checkpoint de origem → runs filhas.
4. **Referências portáveis**: jobs referenciam checkpoints por nome lógico resolvido
   via `POKERED_DATA` (layout em `HANDOFF-mac-share.md`), nunca por path de máquina.

Critério de aceite: rodar a fila 022–024 (ou equivalente) no AM18 com checkpoints
vindos do share — sem tb_stitch, sem offset manual na extração, sem fixup de
acumulador no código chamador, e TB contínuo 0→11M na extração.

## Comments
