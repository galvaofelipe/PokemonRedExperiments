# 06 — Decisão: refactor do acumulador na v2, sim ou não (+ spec)

Type: grilling
Status: resolved
Blocked by: —

## Question

Com os resultados do ticket 05: o refactor do acumulador de batches na v2 é
necessário? A intuição registrada do operador é que sim, porque **desacopla a decisão
de geometria do hardware** — mas este mapa não pode terminar em "faz o refactor e
reza" nem em "não faz e reza": a resposta tem que vir da evidência do 05 contra a
rubrica do 03.

Se sim: produzir a **spec do refactor** (o que muda em `v2/baseline_fast_v2.py`,
semântica do GAE/bootstrap entre rounds, flags, como validar) como Answer — a
implementação é trabalho de outro mapa (Out of scope aqui). Se não: registrar qual
geometria de 8 envs vira o padrão das runs de referência, e por quê.

## Answer

Resolvido em 2026-09-13 (grilling com o operador, 5 rodadas). **Decisão: SIM — o
acumulador entra na v2.**

### Por que sim

- **O empate A/B do ticket 05 não separa geometrias** — e apesar do empate nos
  cortes, as trajetórias das duas células divergem bastante, o que torna ainda
  mais incerto extrapolar o que acontece com mais steps. O acumulador é o único
  braço que reproduz a **estrutura de correlação exata do autor** (64 chunks
  independentes de 2.560, mesmo π congelado, GAE bootstrapped por chunk — a
  única diferença estatística real identificada no ticket 04). Arquivar o
  acumulador agora seria apostar que geometria não importa sem nunca ter
  testado a geometria fiel.
- **b35m é datapoint, não evidência** pró nem contra (episódios de 18h foram
  não intencionais). A 3ª célula responde as duas leituras com o mesmo
  experimento.
- **O desacoplamento geometria↔hardware se paga sozinho** (custo-benefício):
  o auto-researcher passa a poder pedir 16/32/64 streams lógicas conforme o
  experimento, sem negociar com a máquina — o launcher resolve como satisfazer
  o pedido no hardware disponível. O experimento da 3ª célula é **validação,
  não gate**.

### Spec do refactor

**Desenho** (variante 1a "chained buffer" do ticket 04, confirmada): subclass
`AccumulatingPPO(PPO)` com override de `learn()` que roda `collect_rollouts`
stock R vezes com a política congelada (GAE nativo por round, bootstrap próprio
em cada fronteira de 2.560 — matemática idêntica à do buffer (2.560, 64) do
autor), concatena os R buffers de round num objeto com a interface mínima que
`PPO.train()` usa, e chama `train()` **uma vez por mega-update**. Sem tocar em
GAE, `policy.update`, clipping nem optimizer. Pico de RAM menor que a variante
mega-buffer (~3,3 GB extras para 64×2.560×~20 KB/amostra; fallback `np.memmap`
nas obs registrado, **não** implementado de início).

**CLI — separação streams lógicas × físicas** (a tradução mora no
`baseline_fast_v2.py`; a fila `run_queue.sh` continua burra e intocada):

- `--num-envs N` passa a significar **streams lógicas** que o experimento pede
  (o que o auto-researcher escreve no job: 64 = geometria do autor, 16, 32...).
- Teto físico da máquina: variável de ambiente **`V2_PHYSICAL_ENVS`** (8 no
  Mac, 16 no AM18) ou flag `--physical-envs` como override. **Ausente → físico
  = lógico** — comportamento bit a bit idêntico ao de hoje; jobs antigos
  (`--num-envs 8` no Mac com `V2_PHYSICAL_ENVS=8`) resolvem para 8×1 round.
- `rounds = lógico ÷ físico`, com erro claro se não divisível. Ex.:
  `--num-envs 64` no Mac → 8 subprocessos × 8 rounds = 64 chunks de 2.560 =
  update de 163.840 (geometria exata do autor). No AM18 com `=16` → 16×4,
  mesmo update.
- `--n-steps` continua sendo o horizonte por round (2.560).
- O aviso de OOM (`v2/baseline_fast_v2.py:228`) passa a olhar o físico; o
  print inicial mostra a geometria resolvida
  (`logical=64 physical=8 rounds=8 update=163840`).

**Código**: módulo novo `v2/accumulator_ppo.py` (~80–120 linhas).
`baseline_fast_v2.py` ganha só: os argumentos novos, a derivação
lógico/físico/rounds, e a escolha da classe nos dois ramos (`PPO.load` do
resume, `:262`, e o construtor, `:271`). Nada em `red_gym_env_v2.py`,
callbacks ou `run_queue.sh`.

**Cadência** (travada a partir do ticket 04): `_update_current_progress_remaining`
e `_dump_logs` **uma vez por mega-update** (cadência do autor); `_n_updates += 1`
por mega-update via `train()` stock; callbacks (`Checkpoint`/`Tensorboard`/
`Resource`) disparam por `num_timesteps`, que soma certo — sem efeito. Episódios
(16.384 steps no desenho t05) atravessam fronteiras de round normalmente; o
bootstrap de cada round em t=2.560 é o equivalente exato ao chunk do autor, e o
bootstrap de truncamento de episódio continua por-transição (stock,
`on_policy_algorithm.py:211-222`).

**Validação antes da fila** (três camadas):

1. **`v2/tests/test_accumulator_gae.py`** — primeira suíte pytest da v2 (a
   `.venv` já tem pytest). Recalcula o GAE à mão (recursão trás-pra-frente,
   γ=0.997, λ=0.95) num buffer pequeno e compara com a saída da subclass por
   round, incluindo bootstrap na fronteira.
2. **Smoke ~100k steps** com 64 lógicas (8 físicas × 8 rounds): um mega-update
   logado a cada 163.840 amostras; `approx_kl`/`entropy`/`explained_variance`
   em faixa sã (comparável às smokes do t05); pico de RAM < ~12 GB via
   `ResourceCallback`.
3. **Guarda do default**: smoke com `--num-envs 8` sem a env var (rounds=1)
   comporta-se exatamente como o stock.

### 3ª célula (validação, não gate)

- **Desenho**: repete o ticket 05 — 2M × seeds 0/1/2, config verbatim do autor
  (`init.state`, nfr, heal ×10, stuck, gamma 0.997, reward v2, reward_scale 0,5,
  episódios de 16.384 steps), 8 físicas × 8 rounds (64 lógicas) × 2.560,
  ~1h wall cada no Mac, jobs via `v2/jobs/` + `run_queue.sh` (operador roda;
  agente prepara os jobs e roda os smokes). Comparável 1:1 com as células A/B
  no cutoff 2M (flags = `event ÷ 2`).
- **Veredito: judgement call, sem fórmula.** O agente analisa o JSON com a
  estatística que o Python tiver à disposição, o operador olha os gráficos no
  TensorBoard, e a decisão é junta. Na escala de 2M estamos falando de peanuts;
  uma run maior provavelmente será necessária, e seu tamanho se decide com a
  informação da 3ª célula na mão (ticket 16).
- **Adoção**: o acumulador vira a geometria padrão das runs de referência
  **salvo** se a célula + judgement call indicarem problema (underperformance
  clara vs A/B, saúde quebrada, ou falha técnica — RAM, KL, GAE).

### Tickets filhos

- **14 — Implementar o acumulador** (task): spec acima; agente implementa e
  roda as três camadas de validação.
- **15 — Run da 3ª célula** (task; bloqueada por 14): operador roda a fila;
  veredito judgement call com o agente.
- **16 — Desenho da run maior de validação do acumulador** (grilling;
  bloqueado por 15): budget/seeds/MUST-SHOULD-COULD decididos com os
  resultados da 3ª célula na mão.
