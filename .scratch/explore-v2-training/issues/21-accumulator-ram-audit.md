# 21 — Auditoria de RAM do acumulador: de onde vêm os ~105 KB/amostra?

Type: task
Status: resolved
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

- 2026-09-13 (re-bench acc64_p16 pós-`.wslconfig` 27 GB/32 GB swap): evidência
  direta pra alavanca do `del` de round buffers. Run de 1 mega-update: pico de
  PSS **18,8 GB** (`v2/bench/geo_acc64_p16_swapcheck`). A mesma geometria com 2
  mega-updates: pico **26,0 GB**. Delta ~7 GB = round buffers da mega-update
  anterior vivos durante a seguinte (suspeita 4 do ticket). Também: SPS da
  1ª mega-update ~1000 vs ~919 em 2 — o pico de train cheio custa SPS mesmo sem
  thrash de swap. CSVs: `v2/bench/mem_watch_acc64_p16_27gb{,_2mu}.csv`.
- 2026-09-14 (auditoria instrumentada, ticket 21): runs curtas com introspecção
  de arrays vivos + `smaps_rollup` + `mallinfo2` + contadores de gc, script
  separado `v2/mem_audit_t21.py` (subclasse `AuditPPO`, medição apenas — zero
  mudança em código de produção; analisador `v2/analyze_audit_t21.py`).
  Geometrias: 8 lógicas/4 físicas/4 MUs, 32 lógicas/8 físicas×n_steps 1280/2 MUs
  (= 40.960 amostras, ¼ do acc64), e controle `--no-batch-wrap` + run com
  `MALLOC_TRIM_THRESHOLD_=131072 MALLOC_ARENA_MAX=4`. Artefatos:
  `v2/runs_scratch_t21_{small,small_nowrap,small_trim,mid}/audit_{timeline.csv,breakdown.json}`.

  **Orçamento medido por componente (mega-update de 163.840 amostras, escala do
  per-amostra medido em 2 geometrias + fixos medidos):**

  | componente | B/amostra | GB @ acc64 | base da medida |
  |---|---|---|---|
  | obs.screens (**float32 no buffer**) | 69.120 | 11,32 | nbytes vivo, exato |
  | obs.events (**float32**) | 9.952 | 1,63 | idem |
  | obs.map (**float32**) | 9.216 | 1,51 | idem |
  | badges/level/recent_actions/health | 80 | 0,013 | idem |
  | actions/rewards/returns/episode_starts/values/log_probs/advantages | 28 | 0,005 | idem |
  | concat values+returns+advantages (`ChainedRolloutBuffer`) | 12 | 0,002 | idem |
  | **buffer total** | **88.408** | **14,48** | exato, 2 geometrias |
  | baseline pai (python+torch+OMP) | fixo | 0,31 | PSS sem buffer |
  | transientes de train (batch 512: gather 2×45 MB + autograd) | fixo | ~0,1–0,2 | Δ pós/pré-train |
  | warmup torch (1×, ficou residente) | fixo | ~0,17 | só na MU1 |
  | heap livre retido glibc | fixo | 0,08–0,15 | mallinfo2 fordblks |
  | filhos pyboy | fixo | ~0,28/física (4,5 em p16) | tree−parent, estável |
  | fragmentação/ciclos de gc | — | ~0 | hblkhd constante; gc no-op |

  **Causa raiz do gap 5×:** (1) o `DictRolloutBuffer` da SB3 2.3.2 **hardcoded
  `np.float32` em toda chave de obs** — `buffers.py:747` (alloc) e cast na
  atribuição em `buffers.py:788`; a declaração `space.dtype` uint8 é ignorada.
  Isso dá 88,4 vs 21,6 KB/amostra = **4,09×**. (2) O restante (~0,7×) é overhead
  fixo amortizado: filhos pyboy ~27 KB/amostra a p16 + baseline/warmup ~3
  KB/amostra. Ou seja: não há vazamento nem fragmentação significativa — o
  "105 KB/amostra" = 88,4 (buffer float32) + ~17 (fixos), e o buffer sozinho é
  14,48 GB, não 17.

  **Atribuição de fase (medida, sem swap):** o pico do train de uma MU = buffer
  corrente + fixos (no acc64_p16: ~19,5 GB — fecha com o 18,8 GB histórico).
  **A janela double-alive é na COLETA da MU seguinte**, não no train: a chain
  antiga só é solta na reatribuição `self.rollout_buffer = ...`
  (`accumulator_ppo.py:159`), depois de toda a coleta. Medido: pico de coleta
  MU2 = 2×chain + fixos (7,3 GB no mid = 2×3,62+0,6); no acc64_p16 ≈ 34 GB de
  demanda → explica o 26,0 PSS + 6,1 GB de swap do mem_watch. O pico "de train"
  26,0 GB histórico é artefato de swap (thrash na troca coleta→train), não
  residente real do train.

  **Alavancas quantificadas (acc64):**
  1. **uint8 ponta a ponta** (buffer custom respeitando `space.dtype`, cast pra
     float32 só no forward do batch): 66.249 B/amostra → **−10,9 GB**
     (buffer 14,48 → 3,63 GB). É a alavanca principal.
  2. **Soltar a chain antiga logo após o train()** (`del`/None pós-`train()` no
     loop do `learn`): remove a double-alive da coleta → **−14,5 GB** de pico de
     coleta. (Refinamento da nota do ticket 18: `del` após o concat continua
     não servindo — a chain lê obs dos rounds durante o train; o ponto certo é
     depois do train, e o ganho é na fase de coleta, não no pico de train.)
  3. **np.memmap das obs**: −3,6 GB (uint8) ou −14,5 GB (float32) residentes;
     combina com (1). Com 1+2, o acc64 inteiro cabe em ~9 GB de pico de train /
     ~12,5 GB de coleta — sobra até pra 80 lógicas.
  4. Batch gather sem cópia: ~0,1 GB de pico — desprezível.
  5. `MALLOC_TRIM_THRESHOLD_`+`MALLOC_ARENA_MAX`: medido −132 MB — desprezível.
  6. Filhos pyboy 0,28 GB/física — não é alavanca do acumulador, mas p16→p8
     economiza 2,2 GB fixos.

  **Ressalvas:** (a) o "ratchet" de ~135 MB/MU que apareceu numa run inicial era
  artefato do meu monkeypatch de medição (ciclo de refs segurando chains mortas
  até o gc) — o controle `--no-batch-wrap` mostra PSS estável por MU e
  `gc.collect()` no-op; produção não retém. (b) transientes por batch e
  warmup medidos só na geometria pequena com wrapper (batch 512, igual ao
  acc64). (c) não rodei acc64 completo de propósito (thrash de swap); a
  linearidade de cada componente per-amostra foi validada em ¼ de escala e os
  fixos são constantes medidas. Recomendação registrada pro ticket 18: dieta
  1+2 (uint8 + free-after-train) antes de qualquer memmap.

- **2026-09-14 (verificação independente, agente principal):** rerun da mesma
  geometria pequena (`--tag verify`, 8 lógicas/4 físicas, 4 MUs) reproduziu os
  números do subagente dentro do ruído: dtypes/nbytes por chave idênticos
  (todas as obs float32; round_buffer 90.488.832 B/1024 amostras), progressão
  de PSS por MU igual (495→1200 MB com wrapper), e o controle
  `runs_scratch_t21_small_nowrap` confirma PSS flat 650 MB por MU (produção
  libera prontamente; o ratchet é artefato do wrapper de medição). Conferido
  também no código: `buffers.py:747` hardcoda float32 no DictRolloutBuffer do
  SB3 2.3.2 e `accumulator_ppo.py:159` só dropa a chain antiga após a coleta.
  Achados validados — ticket resolvido; desbloqueia o 22.
