# 15 — Run da 3ª célula: acumulador 8-rounds (2M × 3 seeds)

Type: task
Status: resolved
Blocked by: — (14 implementado 2026-09-13, `ready-for-human`, commit `b0883e1`)

## Question

Rodar a 3ª célula de geometria conforme o ticket 06: 2M × seeds 0/1/2, config
verbatim do autor (a mesma das células t05: `init.state`, nfr, heal ×10, stuck,
gamma 0.997, reward v2, reward_scale 0,5, episódios 16.384 steps), geometria
64 lógicas × 2.560 via acumulador (8 físicas × 8 rounds no Mac, ~1h wall cada).

- Agente prepara os jobs em `v2/jobs/` (modelo: `jobs/done/013_t05_g2560_s0.json`);
  operador roda `v2/run_queue.sh`.
- Extração com `tb_extract.py` (flags = `event ÷ 2`), mesma tabela do ticket 05,
  comparável 1:1 com A/B no cutoff 2M.
- **Veredito: judgement call** (ticket 06) — agente no JSON/estatística,
  operador nos gráficos do TB, decisão junta. Sem fórmula de reprovação.
- Adoção: acumulador vira padrão das runs de referência salvo problema claro
  (underperformance vs A/B, saúde, falha técnica).

Saída: tabela 3 seeds × métricas no Answer + veredito registrado. Alimenta o
ticket 16 (desenho da run maior).

## Notas operacionais (medição do smoke do ticket 14, 2026-09-13)

- **Os jobs precisam passar `--physical-envs 8` explicitamente** —
  `run_queue.sh` não exporta `V2_PHYSICAL_ENVS`; sem a flag, 64 lógicas
  virariam 64 subprocessos (OOM). Args de cada job: `--num-envs 64
  --physical-envs 8` (rounds=8 implícito).
- **Overshoot de mega-update**: SB3 só para na fronteira de update —
  `--total-timesteps 2000000` rodaria 13 mega-updates (2.129.920). Para o
  cutoff 2M exato, usar `--total-timesteps 1966080` (= 12 × 163.840).
- **Throughput medido** (8 físicas / 64 lógicas, Mac): ~1.500 sps na coleta,
  ~660 sps médio incluindo train → 2M ≈ 50–55 min wall por seed. Pico RSS
  5,0 GB. Fonte: `v2/runs/smoke_acc_64/resource_summary.txt`.

## Comments

**2026-09-13 — jobs preparados e validados (agente).** `v2/jobs/019_t15_acc64_s0.json`,
`020_t15_acc64_s1.json`, `021_t15_acc64_s2.json`. Args = modelo t05 + `--num-envs 64
--physical-envs 8` + `--total-timesteps 1966080` (12 mega-updates de 163.840, cutoff
2M exato, sem overshoot). Validados replayando cada args[] pelo parser real:
logical=64 physical=8 rounds=8, updates=12 exatas. Fila estava vazia/parada (sem
lock). Falta: operador rodar `cd v2 && ./run_queue.sh` (~50–55 min/seed, ~2,5–3h
total), depois extração com `tb_extract.py` (flags = `event ÷ 2`) + veredito
judgement call junto.

**2026-09-13 07:56 — análise pós-run (metade do agente; timer cron).** 3/3 jobs
completos e limpos: s0 05:03→05:52 (49 min), s1 →06:40 (48 min), s2 →07:27 (46,5 min).
Sem erros nos logs; as 3 runs fecharam **exatamente 1.966.080 steps** (12 mega-updates,
zero overshoot). Backups em `v2/baselines/t15_acc64_s{0,1,2}`. Extração validada
reproduzindo a tabela do ticket 05 com 100% de match (script novo:
`.scratch/explore-v2-training/scripts/cell_table.py`).

### Tabela no cutoff 2M (flags = `event ÷ 2`)

| run | flags_max | coord_max | levels_max | maps_max | dex_max | mmp | deaths_max | wipes |
|---|---|---|---|---|---|---|---|---|
| acc64 s0 | 7 | 306 | 6 | 6 | 4 | 2 | 4 | 0 |
| acc64 s1 | 6 | 118 | 6 | 4 | 2 | 1 | 2 | 0 |
| acc64 s2 | 7 | 436 | 7 | 6 | 4 | 2 | 3 | 0 |

Máximo-ao-longo-do-tempo: acc64 flags 7/7/7, coords 400/388/436 (A: 7/8/8, 413/599/487 ·
B: 7/7/7, 477/388/449). Mesma foto.

### Contra a rubrica N1 (mediana das 3 seeds)

- **acc64**: flags 7 ✓ (≥4), coord 306 ✗ (<350, falha marginal), levels 6 ✗ (<7, no
  fio), deaths 3 ✓ (≤7). Tropeça em 2 pisos — mesmo padrão de B (levels 6 ✗) e pior
  que A (passou). Mas: s1 é o ponto fraco (coord 118, mmp 1, maps 4); s2 é comparável
  às melhores t05 (coord 436, levels 7).

### Saúde técnica (vs t05)

- **approx_kl** med 0,0066–0,0077, máx ≤0,0128 — na faixa de B (0,0066–0,0072), acima
  de A (0,0034–0,0039). São em todas.
- **entropy** −1,93 → −1,77/−1,91; **explained_variance** med 0,40–0,81, min > 0 —
  comparável às t05.
- **avg_sps final 669–708** (t05: 508–657) — o acumulador é ligeiramente **mais
  rápido** que as células de 8 envs no mesmo hardware.
- **Pico RSS 6,0–8,0 GB** — acima do smoke (5,0 GB), dentro do orçamento (<12 GB).
- **0 wipes** nas 3 seeds.

### Estatística (scipy)

acc64 vs pool t05 (A+B, n=6): Mann-Whitney flags p=0,165, coord p=0,381, levels
p=0,766 — nada se separa, e com n=3×6 o poder é ~nulo (descritivo). Spreads por seed
sobrepostos em todas as métricas. Leitura do agente: **nenhuma separação em 2M** —
mesma conclusão qualitativa do A-vs-B do ticket 05. Do lado do JSON não vejo problema
claro (saúde perfeita, throughput igual ou melhor, estatística indistinguível); a
pergunta que fica pro judgement call é se as medianas de coord/levels ligeiramente
abaixo de A pesam contra a adoção.

**Falta pro veredito**: operador nos gráficos do TB (`runs_t15_acc64_s{0,1,2}`,
comparar com `runs_t05_g*`), decisão junta → aí resolve o ticket e atualiza o mapa.

## Answer

Resolvido em 2026-09-13 (veredito judgement call, duas metades: agente no
JSON/estatística — comentário acima — operador nos gráficos do TB, screenshots em
`.scratch/references/tensorboard_screenshots/`).

### Veredito: ADOTA — o acumulador vira a geometria padrão das runs de referência

Pela regra travada no ticket 06 (adoção salvo problema claro: underperformance vs
A/B, saúde quebrada ou falha técnica), **nenhum dos três gatilhos disparou**:

- **Sem underperformance clara**: medianas acc64 flags 7 / coord 306 / levels 6 /
  deaths 3 vs A 8/368/7/5 e B 7/449/6/3 — tudo sobreposto, MWU p≥0,165 com poder
  ~nulo (n=3). acc64 tropeça nos pisos N1 de coord e levels, como B tropeçou em
  levels; s1 é a seed fraca (coord 118, mmp 1), s2 é comparável às melhores t05.
- **Saúde perfeita**: 0 wipes, KL 0,007–0,013 (faixa de B), entropy/EV normais.
- **Sem falha técnica**: 3× ~46–49 min, exatamente 1.966.080 steps (zero overshoot),
  pico RSS 6,0–8,0 GB (< 12 GB), avg_sps **669–708 — mais rápido** que A/B (508–657).

### Descoberta qualitativa (as duas metades concordam): a forma da trajetória

Operador no TB: acc64 se parece com g20480, não com g2560. Confirmado no dado —
fração do valor final já atingida em 1M (metade da run), média das 3 seeds:

| tag | A (g2560) | B (g20480) | acc64 |
|---|---|---|---|
| env_stats/event | 0,94 | 0,03 | 0,13 |
| env_stats/coord_count | 0,95 | 0,24 | 0,36 |
| env_stats/levels_sum | 0,99 | 0,00 | 0,12 |
| env_stats_max/coord_count | 0,93 | 0,24 | 0,37 |
| env_stats_max/event | 0,97 | 0,20 | 0,33 |

A (98 updates em 2M) tem forma côncava (√x): sobe cedo, estagna. B e acc64 (12
mega-updates em 2M) ficam chapados até ~1,2–1,5M e sobem no final — forma de subida
tardia. Leitura: **a forma é limitada pela contagem de updates**, e no cutoff 2M
B/acc64 ainda estão na parte crescente da curva enquanto A já estagnou. Em 2M isso
empata (o fim da subida de B/acc encontra o platô de A); **não dá pra distinguir
"catch-up que convergiria acima de A" de "deficit real" nessa escala** — essa é
exatamente a pergunta que o desenho da run maior (ticket 16) tem que responder.
E nota pra interpretação futura: o acumulador (estrutura de correlação exata do
autor) **não** se comportou diferente de B (horizonte longo puro) em 2M — a
diferença A↔B/acc é de cadência de update, não de mecanismo.

### Perf (sanity da surpresa do operador)

avg_sps maior no acc64 é consistente com amortização de overhead: 12 train() +
_dump_logs em vez de 98 (A) — cada update tem custo fixo de setup/GAE/logging. acc
vs B (ambos 12 updates) difere pouco (~10%, ruído de máquina). RAM comparável (o
chained buffer guarda as mesmas ~163.840 amostras, só fatiadas por round), CPU
maior porque o train de 163.840 amostras segura a CPU em blocos contínuos de ~2,5 min.

### Consequências

- **Acumulador = padrão** das runs de referência daqui pra frente (geometria do
  autor 64×2.560 via 8 físicas × 8 rounds no Mac).
- Desbloqueia o **16** (desenho da run maior) — com a pergunta central já afiada:
  a run maior tem que ser longa o bastante pra forma "subida tardia" se resolver
  (catch-up vs deficit), e o interplay com o 08 (runbook go/no-go) está no corpo
  do 16.
