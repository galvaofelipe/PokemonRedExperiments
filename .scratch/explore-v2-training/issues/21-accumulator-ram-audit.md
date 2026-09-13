# 21 — Auditoria de RAM do acumulador: de onde vêm os ~105 KB/amostra?

Type: task
Status: open
Blocked by: —

## Question

A matemática do observation_space não fecha com o footprint medido — investigar se
estamos sendo dispendiosos e onde. Números de partida (medidos no AM18, ticket 07):

- **Obs por amostra (espaço declarado)**: screens (72×80×3) uint8 = 17.280 B +
  map (48×48×1) uint8 = 2.304 B + events MultiBinary(2488) = 2.488 B +
  health/level/badges/recent_actions ≈ 70 B ≈ **21,6 KB/amostra** (+ actions/values/
  log_probs/advantages/returns/episode_starts, desprezível).
- **Medido**: buffer de 163.840 amostras ≈ **17 GB** ≈ **105 KB/amostra** — ~5× o
  espaço declarado. E a medição externa (ticket 18, `scripts/mem_watch.py`) mostra
  demanda real de pico ~27–28 GB (PSS só vê residente; ~5 GB foram pro swap).

Suspeitos a quantificar, em ordem de prioridade:

1. **Dtype cast em algum lugar**: uint8→float32 seria 4× — quase exatamente o gap.
   Auditar o que o `DictRolloutBuffer` da SB3 2.3.2 realmente aloca por chave
   (ela respeita `space.dtype`? algo no caminho env→buffer promove pra float?).
2. **Atribuição do pico**: o pico é durante `train()` — separar o que é buffer
   residente vs transientes (batches torch em float32, optimizer state, cópias do
   `np.concatenate` de values/returns/advantages no `ChainedRolloutBuffer`).
   Método: `resource_callback` + `/proc/<pid>/smaps` do pai por mapping
   (anon/heap/file) no pico + introspecção dos arrays (`nbytes` por chave do
   `rollout_buffer`).
3. **Fragmentação de alocador**: glibc malloc arenas / numpy não devolvendo páginas
   (PSS vs demanda real inclui isso). Checar com `MALLOC_TRIM_THRESHOLD_` ou
   medir heap anon vs soma dos arrays vivos.
4. **Alavancas de dieta** (quantificar o ganho de cada uma, alimenta a decisão do
   ticket 18): `np.memmap` das obs (disco em vez de RAM — viabiliza 80 lógicas),
   screens em uint8 garantido ponta a ponta, `del` explícito de round buffers após
   o train (hoje vivem até a próxima mega-update reatribuir), batch gather sem
   cópia extra.

Critério de aceite: tabela de orçamento de memória por componente pra uma
mega-update (medida, não estimada), desperdícios identificados com ganho
quantificado de cada alavanca, e a decisão de dieta registrada no Answer do
ticket 18.

Relacionado: 18 (decisão de dieta), 07 (medições AM18), 06 (desenho do acumulador).

## Comments
