# 02 — Evidência pra rubrica de conversão: telemetria das 8 runs + referência do autor

Type: research
Status: resolved

## Question

Montar o corpo de evidência do qual a rubrica de conversão (ticket 03) será travada.
Das **8 runs já concluídas** (b45, b11m, b35m, b2m_2hep, b2m_fr5, b11m_2hep, b11m_fr5,
b2m_2hep_fr5 — sessões em `v2/runs_*/`, backups em `v2/baselines/`, ver matriz no
STUB), extrair por run, em função dos steps:

1. Trajetórias de progresso: `max_map_progress`, coord_count (coords únicas), eventos,
   levels, badges — o que a telemetria/tensorboard (`<run>/histogram/`) e os
   `agent_stats` permitem reconstruir.
2. Sinais de saúde vs farm: duração média de episódio, taxa de wipe (onde aplicável),
   tendência (crescente/decaindo) de cada sinal por terço da run.
3. **Dose-resposta**: progresso final vs budget (45min → 2M → 11M → 35M) nas células
   nfr — o progresso ainda cresce com o budget? Em qual taxa? Há sinal de saturação
   ou de colapso?
4. Se o ticket 01 já tiver produzido a curva de referência do autor, anotar onde ela
   se sobrepõe em budget com as nossas runs (pontos comparáveis).

O produto é uma tabela/série de números + uma **proposta de thresholds N1/N2** (o que
conta como "converge no mesmo grau" em escala curta e média), a ser decidida no
ticket 03. Não decidir — apresentar a evidência e o rascunho.

Contexto: STUB em `.scratch/explore-v2-training/STUB.md` (seções Matriz, P1, P2).

## Answer

Resolvido em 2026-09-12. Extração feita com scripts temporários em `/tmp`
(`evidence_extract.py` → CSVs em `/tmp/evidence/`, `evidence_analyze*.py` →
agregações). Fonte primária: event files tensorboard de cada run —
`v2/runs_<run>/poke_ppo_1/events.out.tfevents.*` (tags `env_stats/*` = média da
frota e `env_stats_max/*` = máximo da frota, logadas quando o env 0 termina um
episódio; x = step global) e `v2/runs_<run>/histogram/events.out.tfevents.*`
(tags `episode/{length,survival,end_wipe,end_max_steps}`, logadas por done de
qualquer env). Valores lidos do campo `tensor` do proto (torch SummaryWriter).
Budgets/wall de `v2/runs_<run>/resource_summary.txt`; configs de
`v2/jobs/<run>.status`. Sem dados inventados: todo número abaixo vem desses
arquivos (scripts reproduzem a extração).

### 0. Descobertas estruturais (condicionam toda a leitura)

1. **As runs 18h nfr são UMA única trajetória.** Seed 0 fixa + env/PPO
   determinísticos ⇒ `b45` (1.9456M, `--minutes 45`) é um prefixo, `b11m` (11M) é
   a mesma trajetória completa, e `b35m` (35M) re-executou do zero e reproduziu
   os primeiros 8 snapshots de `b11m` **bit-a-bit** (coord_count
   507/534/622/624/555/585/1173/999 nos mesmos steps 1.31M–10.49M; wall_times
   distintos provam re-execução, não append). A "dose-resposta 45min→11M→35M" é
   uma curva de aprendizado com 3 leituras, **não 3 amostras independentes**.
2. **Telemetria `episode/*` existe só em 4/8 runs**: b2m_2hep (11 eps),
   b11m_2hep (672), b11m_fr5 (662), b2m_2hep_fr5 (188). b45/b11m/b35m/b2m_fr5
   só têm snapshots `env_stats*`. Anomalia: b2m_fr5 tem 1 snapshot env_stats
   (done do env 0 em 1.6384M globais) mas zero scalares `episode/*` — não
   explicado (runs anterior e posterior têm).
3. **Resolução dos snapshots**: 1 por episódio do env 0 (steps-globais = steps
   por env × num_envs). Com episódio de 163840 (18h) e 8 envs, há 1 snapshot a
   cada 1.31M globais: b45=1, b11m=8, b35m=26 pontos. Células 2h (16384): 84
   pontos em 11M. `agent_stats` por step NÃO é persistido (só agregados nos
   event files; os zips `poke_*_steps.zip` são pesos do modelo).
4. **Sem variância entre seeds em nenhuma célula** (seed 0 única) — qualquer
   threshold abaixo tem n=1 por configuração.

Escala: `max_map_progress` (mmp) = índice 0–14 na progressão de mapas do env
(`essential_map_locations`, 40→0→12→1→13→51→2→54→14→59→60→61→15→3→65).
`event` = max_event_rew × 4 (reward_scale=1). `levels_sum` = soma dos 6 slots
da party. `badge` = bitmask (0 em todos os snapshots de todas as runs).
`deaths` = blackouts por episódio (zera no reset junto com o mundo).
`coord_count` = `len(seen_coords)`, zera no reset (renovável — cf. P1).

### 1. Trajetórias de progresso (fleet-max; first / fim-terço1 / fim-terço2 / last | peak)

| run (budget, ep, faint) | mmp | coord_count | levels_sum | event | badge | healr | deaths |
|---|---|---|---|---|---|---|---|
| b45 (~1.94M, 18h, nfr) | 2 / 2 / 2 / 2 \| 2 | 507 (1 snapshot só) | 7 | 16 | 0 | 1.6 | 4 |
| b11m (11M, 18h, nfr) | 2 / 2 / 2 / 3 \| 3 | 507 / 534 / 555 / 999 \| **1173** | 7 / 8 / 7 / 13 \| 13 | 16 / 16 / 16 / 16 \| **30** | 0 | 1.6 / 1.3 / 1.3 / 1.5 \| 1.9 | 4 / 13 / 9 / 18 \| 18 |
| b35m (35M, 18h, nfr) | 2 / 3 / 3 / 3 \| 3 | 507 / 999 / 1296 / 1566 \| **1566** | 7 / 13 / 12 / 15 \| 20 | 16 / 16 / 30 / 26 \| 30 | 0 | 1.6 / 1.5 / 0.8 / 1.7 \| 1.9 | 4 / 18 / 14 / 27 \| 31 |
| b2m_2hep (2M, 2h, nfr) | 1 / 2 / 2 / 2 \| 2 | 237 / 358 / 407 / 354 \| 415 | 0 / 6 / 6 / 7 \| 8 | 2 / 14 / 14 / 16 \| 16 | 0 | 0 / 0.6 / 0.6 / 0.5 \| 0.8 | 0 / 3 / 5 / 4 \| 7 |
| b2m_fr5 (2M, 18h, fr5) | 1 (estagnado) | 251 (1 snapshot) | 0 | 2 | 0 | 0 | 0 |
| b11m_2hep (11M, 2h, nfr) | 1 / 2 / 3 / 3 \| 3 | 250 / 419 / 1281 / 1472 \| **1505** | 6 / 7 / 9 / 7 \| 12 | 12 / 14 / 18 / 26 \| 30 | 0 | 0.4 / 0.7 / 0.7 / 1.0 \| 1.4 | 1 / 3 / 6 / 4 \| 11 |
| b11m_fr5 (11M, 18h, fr5) | 2 / 3 / 2 / 3 \| 3 | 553 / 682 / 623 / 1046 \| **1046** | 8 / 11 / 18 / 16 \| 18 | 16 / 16 / 16 / 18 \| 18 | 0 | 1.0 / 1.3 / 1.0 / 1.2 \| 1.3 | 16 / 12 / 12 / 12 \| 16 |
| b2m_2hep_fr5 (2M, 2h, fr5) | 1 / 1 / 1 / 2 \| 3 | 237 / 303 / 138 / 206 \| **519** | 0 / 6 / 5 / 7 \| 7 | 2 / 14 / 10 / 12 \| 14 | 0 | 0 / 0.8 / 0.0 / 0.8 \| 0.8 | 0 / 1 / 1 / 1 \| 2 |

Fleet-mean no último terço (progresso típico, não do melhor env): b35m mmp 3.0
/ coord 1196 / levels 10.9 / event 18.5; b11m_2hep coord 859 / event 20.0;
b11m coord 740 / event 15.8; b11m_fr5 coord 434 / event 15.8;
b2m_2hep coord 293 / event 14.2; b2m_2hep_fr5 coord 125 / event 8.8;
b45 coord 441 / event 12.5; b2m_fr5 coord 136 / event 0.2.

Forma da curva (série completa, `envmax`): 18h nfr fica em platô
(coord ~507–624, event 16) até ~7.9M e salta em 9.18M (coord 1173, event 30,
mmp 3); de 11.8M a 34M oscila coord 990–1566 em degraus, sem novo salto de mmp.
2h nfr (b11m_2hep, 84 pontos): sobe de ~250 para ~1000+ entre 4.3M e 6.3M,
plateau ~1300–1500 depois; event salta 16→18 em ~6.3M e 26–30 só após ~8.7M.

### 2. Saúde vs farm (por terço)

**fr5 (contagens exatas de end_reason; batem com o STUB):**

| run | t1 | t2 | t3 | total |
|---|---|---|---|---|
| b2m_2hep_fr5 | wipe_rate 0.220, wipe_len 9423 | 0.586 / 7791 | **0.753 / 4893** | 110 wipes (58.5%), 78 max_steps, 11 survival (5.9%) |
| b11m_fr5 | 0.966 / 16864 | 0.952 / **4479** | 0.946 / 9190 | 631 wipes (95.3%), 31 max_steps, 30 survival (4.5%) |

Tendência: b2m_2hep_fr5 — wipe rate sobe 22→75% e wipe_len cai ~48% dentro da
run (aprende a morrer mais rápido; mín 814). b11m_fr5 — wipe rate estável ~95%,
wipe_len despenca 16864→4479 (mín 399). Episódios survival terminam por
max_steps (163840 ✔ / 16384 ✔) — o survival sorteado é 5%/episódio como
configurado.
**nfr (100% max_steps, 0 wipes — faint nunca corta; saúde via deaths/healr/hp
por episódio):** deaths fleet-mean (first/t1/t2/last): b11m 2.5/10.1/5.6/12.9;
b35m 2.5/12.9/6.5/15.0; b2m_2hep 0/1.3/1.9/2.5; b11m_2hep 0.1/2.4/4.3/2.6. hp
fleet-mean termina 0.79–0.89 nas 18h (b11m_fr5 cai para 0.60). healr por
episódio fica ≤ 1.9 em todas (curas do blackout dominam; b2m_2hep_fr5 oscila
0→0.8→0→0.8).

**Diagnóstico farm por célula:** (a) b2m_2hep_fr5 — pior célula: coord
fleet-mean cai 175→107→125, event cai no t3 (10.2→8.8), wipe rate crescente =
pinhata 2h reabastecida a cada morte (confirma P1). (b) b11m_fr5 — troca
fronteira por level: levels 16–18 > nfr (13) com event 18 < nfr (30) e coord
1046 < 1173. (c) b2m_fr5 — congelada: 2M steps = 1 episódio de 18h por env, 0
mortes, levels 0, event 2; fr5 é inerte nessa escala. (d) nfr 18h — sem colapso,
mas deaths/épisódio cresce com o budget (4→18→31) e healr não: fração crescente
do rollout gasta em wipe, sem progresso de mmp/event correspondente.

### 3. Dose-resposta nfr (progresso vs budget)

**18h (mesma trajetória; leituras em 1.94M / 11M / 35M):**

| budget | mmp | coord_max | levels_max | event_max | deaths/ep máx |
|---|---|---|---|---|---|
| ~1.94M | 2 | 507 | 7 | 16 | 4 |
| 11M | 3 | 1173 | 13 | 30 | 18 |
| 35M | 3 | 1566 | 20 | 30 | 31 |

Taxa coord: +666 coords em 1.9→11M (~74/M) depois +567 em 11→35M (~24/M) —
**desacelera ~3×**. mmp satura em 3 a partir de ~9M; event satura em ~30 (≈7–8
flags) também por volta de 9M; levels ainda cresce (7→13→20) mas a passos
menores; **deaths não satura** (4→18→31, crescimento quase linear). Ou seja:
progresso ainda cresce em 35M em coord/levels, mas o retorno marginal por step
cai e vem acompanhado de monotonização crescente (deaths) — nenhum colapso em
nfr, saturação parcial (mmp/event), e um custo de "saúde" crescente.

**2h (duas células independentes, envs diferentes):**

| budget | mmp | coord_max | levels_max | event_max | deaths/ep máx |
|---|---|---|---|---|---|
| 2M (b2m_2hep) | 2 | 415 | 8 | 16 | 7 |
| 11M (b11m_2hep) | 3 | 1505 | 12 | 30 | 11 |

Taxa coord +1090 em 2→11M (~121/M) — ~5× a taxa do regime 18h na mesma
janela; event também chega a 30; porém levels_sum fleet-mean estagna (6→6) e
deaths/ep máx sobe (7→11). Episódio curto não é panaceia: explora mais por
step global, mas a pinhata 2h ainda renova event/heal a cada 16384 steps.

### 4. Referência do autor (ticket 01 — resolvido, usar a Answer dele)

A curva quantitativa do autor **não é extraível** (ticket 01: zero event files;
só o checkpoint final de 439.746.560 steps e o notebook estático com médias
finais). Pontos de comparação que ele permite:

- **Geometria**: a run original usava `ep_length = 2048×8 = 16384` — o mesmo
  `max_steps` do nosso regime "2h". A célula mais próxima em geometria é
  b11m_2hep (diverge: 8 vs 44 envs, n_steps 2560 vs 16384, gamma 0.997 vs
  0.999, `init.state` vs `has_pokedex_nballs.state`). As células 18h (163840)
  não têm equivalente na run do autor.
- **Budget**: nossos 35M ≈ 8% dos 439.7M dele. Marcos dele em steps:
  gym_well ~24M, past_gym1 ~49.7M, Mt. Moon ~440M (nomes de checkpoints do
  git). Nosso 35M ≈ 70% do "past_gym1".
- **Nível de progresso**: autor (notebook, média sobre 44 envs no último step
  de cada rollout, 610 rollouts): total_levels ~20→35–40, event ~8–10 (escala
  do reward dele, sem o ×4 do v2), healr ~9, deaths ~4, **badge ≈ 0 em toda a
  curva**. Nosso melhor (b35m): levels_sum máx ~20 (fleet-max; fleet-mean 11),
  event 30 = 7–8 flags (escala v2), badge 0. levels_sum e coord_count são os
  comparáveis diretos; em levels estamos ~2× atrás do nível final dele (com 12×
  menos steps).
- Âncora útil pra rubrica: "passar do ginásio" em ~50M steps (past_gym1) na
  config original; badge é marco fraco em ambos (≈0 até muito longe).

### 5. Proposta de thresholds N1/N2 (RASCUNHO — decisão no ticket 03)

Calibrado com a baseline atual (n=1 por célula, seed 0 — trat como referência,
não como meta final). Nível de "converge no mesmo grau" = ficar dentro da
faixa que as células nfr saudáveis da matriz atingem.

**N1 — escala curta (~2M steps globais, ~45 min, config 2h/10 envs ou equivalente):**

- Progresso mínimo: `event_max ≥ 16` (4 flags; 2 = nada aconteceu) **e**
  `coord_max ≥ ~350` (nfr saudável: 354–415; células doentes: 251/206)
  **e** `levels_sum ≥ ~7` ao fim (0 = run congelada, cf. b2m_fr5).
- Saúde mínima: `deaths/episódio_max ≤ ~7`; `event` não regredir no último
  terço; se fr5: wipe_rate do último terço não > 2× o do primeiro com
  wipe_len caindo > 40% (assinatura do farm de wipe).
- Sinais de reprovação imediata: levels_sum ≈ 0; mmp estagnado em 1 com
  event ≤ 2 (b2m_fr5); coord fleet-mean decaindo de terço a terço
  (b2m_2hep_fr5: 175→107→125).

**N2 — escala média (~11M steps globais, ~4–4,5 h):**

- Progresso mínimo: `mmp ≥ 3` **e** `event_max ≥ ~26` (≈6–7 flags; nfr 11M
  atingiu 30, fr5 doente 18) **e** `coord_max ≥ ~1000` (nfr: 1173/1505;
  fr5-doença com levels altos e event baixo não entra: b11m_fr5 1046 mas event
  18) **e** `levels_sum_max ≥ ~12`.
- Saúde/taxa: curva de coord ainda crescente entre o fim do t2 e o fim da run
  (b11m_2hep: 1281→1472); deaths/episódio fleet-mean ≤ ~4 (b11m_2hep 3.1;
  b35m já roda em ~12 — aceitável em 35M, não em 11M); sem queda de
  wipe_len_mediana abaixo de ~4–5k nas células fr5 (b11m_fr5 t2: 4479 = farm).
- Âncora externa (autor): em ~50M steps o marco "ginásio" era esperado na
  config dele; se a v2 corrigida não mostrar event_max > 30 (7–8 flags) e
  levels crescendo até ~11M, "converge no mesmo grau" fica em cheque.

**Caveats pra decisão no ticket 03:** (1) thresholds calibrados em runs com a
pinhata P1/P2 ativa — servem como piso da baseline, não como teto do env
corrigido; (2) n=1, seed 0, e as 3 leituras 18h são a mesma trajetória —
recomenda-se revalidar com 2–3 seeds antes de travar; (3) badge excluído dos
thresholds (sinal fraco em autor e baseline); (4) episódios 18h têm resolução
de 1 snapshot/1.31M steps — métricas de trajetória em escala curta devem
preferir o regime 2h.

### Evidência e reprodução

- Scripts: `/tmp/evidence_extract.py`, `/tmp/evidence_analyze.py`,
  `/tmp/evidence_analyze2.py`, `/tmp/evidence_analyze3.py`; saídas em
  `/tmp/evidence/` (`*.csv`, `meta.json`, `analysis.json`). /tmp é volátil —
  os event files no repo são a fonte permanente.
- Código de telemetria: `v2/tensorboard_callback.py` (gating env-0 done; scalars
  `episode/*` por vec-done), `v2/red_gym_env_v2.py:298-322` (campos de
  `agent_stats`), `:444-452` (`check_if_done`), `:128-178` (reset zera
  coord/deaths/event/heal — mundo renovável), `:555-569` (escala event ×4).
- Limitações: sem `agent_stats` por step persistido; b45/b11m/b35m/b2m_fr5 sem
  `episode/*`; anomalia b2m_fr5 (snapshot sem scalares); envs 8 vs 10 confunde
  células 2M (batch/update diferentes) — já mapeado no STUB.
