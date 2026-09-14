# Map — explore-v2-training

wayfinder:map

## Destination

Eliminar as incertezas que a v3 não conhecia quando fez o cutout, respondendo:

1. A v2 converge **no mesmo grau** no nosso hardware? (rubrica de conversão definida e
   testada contra as 8 runs existentes + runs curtas novas)
2. Quais propriedades Frozen do env tornam a missão do auto-researcher injusta ou
   impossível? (veredito por propriedade, entregue como input pro mapa da v3)
3. A geometria de update do autor (64 envs × 2.560 steps = 163.840/update) é necessária
   pra conversão, ou variantes de 8 envs bastam? (evidência empírica, não reza)
4. Runbook da run longa (milestone-gated, AM18) pronto pra executar — com go/no-go
   vindo de 1–3. **Orçamento-âncora revisado pelo ticket 11**: o autor da v2 chegou à
   SS Anne em 26M steps (não 440M — esse número é da linhagem v1). O teto da run
   longa sai da rubrica (ticket 03), não mais do 440M.

O produto são **especificações**: refactor da v2 (se necessário), correções pro mapa da
v3, runbook AM18. Não é: rodar a 440M até o fim, refatorar a v2, nem corrigir a v3.

## Notes

- **Override do default plan-only**: este mapa inclui execução de experimentos curtos
  como tickets (runs de 1–12h wall no Mac). O mapa termina quando a reza acabar —
  não com "faz o refactor e torce".
- Contexto denso já investigado: `.scratch/explore-v2-training/STUB.md` (matriz de runs,
  P1/P2, fork vs upstream, tetos de SPS). Referenciar, não repetir.
- Skills: `/grilling` e `/domain-modeling` em tickets HITL; research AFK via subagente.
- **Orçamento de hardware** (do operador, 2026-09-12): Mac 10 cores → teto 8 envs,
  ~720 SPS, runs de 1h / 4h / máx 12h wall. AM18 (16 cores, WSL2) → 8–16 envs (a medir),
  várias runs de 24–48h/semana OU uma de 72–120h/semana. Formatar o AM18 pra Linux está
  fora de escopo. **Cloud (Hetzner) fora de escopo** até prova de valor e necessidade.
- **Ordem das execuções** (operador, 2026-09-12): testes no AM18 só **depois** das
  runs de geometria no Mac — o ticket 07 está bloqueado pelo 05.
- **Config de repro — CORRIGIDA pelo ticket 01 (2026-09-12)**: a run de 440M (Brock,
  Mt. Moon) NÃO usou a config v2. Linhagem original (2022): 44 envs × 16.384 steps/ep
  (≈2h), update = 44 episódios completos (720.896 amostras), gamma 0.999,
  `has_pokedex_nballs.state`, reward antigo (level×100, hp×2000, explore-KNN×160) —
  env v1. Linhagem v2 (2025, nosso fork): 64 × 2.560, 18h/ep, `init.state`,
  gamma 0.997, reward simplificado. Qual linhagem reproduzir é a decisão do
  ticket 10 — trava a geometria do 05 e o runbook do 08.
- **Faint-reset**: fora da repro (o autor não usava). A ausência de faint-reset na v3
  (`--early-stop` é flag morta) é registrada no veredito (ticket 09) como fato Frozen;
  decidir se importa é trabalho do mapa da v3.
- Hipótese central da rubrica: com runs menores conseguimos provar que **aumentar o
  budget continua aumentando o progresso** — e que portanto uma run na janela N3
  (25–35M) reproduziria o Brock do autor. Se descobrirmos que só uma run completa
  prova conversão, é azar nosso e o desenho dessa run vira ticket novo.

## Decisions so far

- [16 — Desenho da run maior de validação do acumulador](issues/16-accumulator-bigger-run-design.md) —
  **célula comparativa de 3 braços em 11M** (A/B/acc64), resume do checkpoint
  exato de 2M (+9.011.200 steps, alvo absoluto 10.977.280 = N2), config verbatim
  t15. Seeds em 2 fases: s0 nos 3 braços primeiro (fila acc64→B→A), s1/s2 depois.
  Critérios MUST (sem underperformance vs A/B, dose-resposta viva no último
  terço, saúde) / SHOULD (forma resolvida = catch-up vs deficit; pisos N2 +
  projeção de ritmo registrados) / COULD (calibração unique_maps/dex_seen,
  b11m_2hep externo, perf). Decidido **não acoplar no runbook (08)** agora.
  Filho: 17 (execução).
- [15 — Run da 3ª célula: acumulador 8-rounds](issues/15-accumulator-cell-run.md) —
  **ADOTA**: acumulador vira a geometria padrão das runs de referência. 3 seeds ×
  2M exato (12 mega-updates, zero overshoot, ~48 min/seed, pico RSS 6–8 GB,
  avg_sps 669–708 — mais rápido que A/B). Nenhuma separação estatística vs A/B em
  2M (tabela no Answer). Descoberta qualitativa: a **forma** da trajetória é
  limitada pela contagem de updates — A (98 updates) é côncava e estagna cedo;
  B/acc64 (12 mega-updates) ficam chapados até ~1,2–1,5M e sobem no final
  (ratio valor@1M ÷ valor@2M: A ~0,95, B/acc ~0,03–0,5). Catch-up vs deficit real
  não se distingue em 2M — é a pergunta central do ticket 16. Acumulador ≡ B em
  forma: a diferença A↔B/acc é de cadência, não de mecanismo.
- [06 — Decisão: acumulador na v2, sim/não (+ spec)](issues/06-accumulator-decision.md) —
  **SIM**. Motivos: A/B não separam em 2M e as trajetórias divergem; o acumulador
  é o único braço com a estrutura de correlação exata do autor; o desacoplamento
  geometria↔hardware se paga sozinho (auto-researcher pede streams lógicas, o
  launcher resolve no hardware). Spec: variante 1a chained buffer, `--num-envs`
  = lógicas + `V2_PHYSICAL_ENVS`/`--physical-envs` = teto físico (rounds =
  lógico ÷ físico, retrocompatível), `v2/accumulator_ppo.py` + wiring mínimo,
  validação em 3 camadas (teste GAE pytest, smoke 64-lógicas, guarda do
  default). 3ª célula = validação (não gate): 2M × 3 seeds, veredito judgement
  call. Filhos: 14 (implementar) → 15 (run) → 16 (run maior, MUST/SHOULD/COULD).
- [05 — Runs curtas de geometria](issues/05-geometry-experiments.md) — 8×2.560 e
  8×20.480 **não se separam em 2M** (flags 8 vs 7, coord 368 vs 449, levels 7 vs 6;
  ruído de seed). Ambas passam os pisos N1 de flags/coord; B tropeça no piso de
  levels. Saúde perfeita (0 wipes). **3ª célula = acumulador 8-rounds (ticket 06,
  motivado)**. Referência de teto calibrada: checkpoint do autor congelado
  (`eval_pretrained.py`, runs_eval_peter{,_2,_3}) — flags 20 @2h, badge em 33–75%
  dos episódios de 4–8h; pisos N1 ficam 4–8× abaixo do teto, como calibrados.
- [04 — Acumulador de batches no SB3](issues/04-batch-accumulator-sb3.md) — viável
  (~80–120 linhas, sem tocar em GAE/optimizer, ~1–2 dias), mas 8×20.480 é quase
  equivalente e custo zero (horizonte GAE ≈ 19 steps ≪ 2.560); literatura favorece
  batch maior. Experimento decisivo: 8×2.560 vs 8×20.480 por env-step.
- [01 — Claims originais do autor](issues/01-author-original-claims.md) — a run de
  440M (Brock, Mt. Moon) é da **linhagem 2022**: 44 envs × 16.384 (≈2h/ep), update =
  44 episódios completos, gamma 0.999, `has_pokedex_nballs.state`, reward antigo —
  não a config v2. Sem telemetria pública: só checkpoint final + curvas estáticas no
  notebook. SS Anne nunca foi claim da 440M; Cerulean é claim da linhagem v2, sem
  budget publicado.
- [02 — Evidência pra rubrica de conversão](issues/02-conversion-rubric-evidence.md) —
  trajetórias das 8 runs extraídas; dose-resposta nfr 18h: coord_max 507→1173→1566
  com taxa caindo ~3×, mmp/event saturam ~3/~30 em 9M. **Descoberta estrutural:
  b45/b11m/b35m são a MESMA trajetória** (seed 0 + determinismo) — a "dose-resposta"
  é 1 curva, não 3 amostras. Rascunho N1/N2 calibrado pronto pro ticket 03.
- [10 — Qual linhagem reproduzir](issues/10-which-lineage.md) — híbrido com centro na
  v2: alvo principal é a linhagem v2 (stack que a v3 congelou); a 440M da v1 é cheque
  externo de plausibilidade. **Conclusão aceitável desde já: "a v3 como pensada é
  inviável"** — se a v2 custar ordens de magnitude mais pros mesmos marcos, o mapa
  da v3 precisa ser repensado.
- [11 — Resultados comprovados da linhagem v2/PufferLib](issues/11-v2-lineage-proven-results.md) —
  a v2 precisa de **~17× MENOS** recurso que a v1, não 10× mais: o autor chegou à
  SS Anne do zero em **26M steps** (checkpoint no commit `2f79c5a`); pokegym/PufferLib:
  Badge 1 em **9,6M**, Badge 2 em 35M, Badge 3 em 404M. Steps comparáveis 1:1 entre
  linhagens (action_freq=24 em todas). N3 honesto pro ticket 03: **10–26M até Brock**.
  Tensão crítica: nosso b35m (35M, 8 envs) está preso em mmp 3 — muito abaixo do
  autor a 26M; a diferença (geometria? config?) é o mistério central dos tickets 03/05.
- [03 — Travar a rubrica de conversão](issues/03-lock-conversion-rubric.md) — rubrica
  travada: eixo primário = contagem de event flags (monótono, denso, já existe na
  telemetria = `event ÷ 4`); unique_maps/dex_seen viram telemetria nova (ticket 12);
  N1 (~2M, 3 seeds, mediana) e N2 (~11M, ≥2 seeds) como pisos de corte; liberação
  da run longa exige dose-resposta + projeção de ritmo (mmp ≥ 7 projetado);
  **N3 = Brock em 25–35M — o 440M está aposentado**.
- [12 — Telemetria v2: logar unique_maps e dex_seen](issues/12-telemetry-unique-maps-dex-seen.md) —
  campos em `agent_stats` (commit `62e198c`, só `red_gym_env_v2.py`; o callback
  agrega `agent_stats` sem edição); smoke run confirma os 4 tags
  `env_stats{,_max}/{unique_maps,dex_seen}` (unique_maps 2→4, dex_seen 0 em
  episódios curtos pré-pokédex). Eixos secundários da rubrica saem em qualquer
  run a partir deste commit — desbloqueia o 05.

- **13 — Linha de progresso no watch** ([issues/13-interactive-progress-line.md](issues/13-interactive-progress-line.md)):
  `debug` no `env_config` do interactive não é lido; `print_rewards` existe mas a
  chamada está comentada e ainda dumpa jpeg. Ticket: uma `\r` line de
  `agent_stats` (step/map/mmp/badge/…) no stdout do watch do `poke_26214400`.
  Motivação: o watch de 2026-09-12 só confirmou Brock/Mt. Moon via trainer card.
- [24 — t16_acc64_s0 @ ~19M: parede pós-Pokédex em Viridian](issues/24-t16-acc64-s0-viridian-wall.md) —
  campanha 64×2560 (Mac+AM18) satura `mmp=3` / `event=30` / 0 badges; `dex_seen`
  **não** implica Pokédex (pret marca seen em todo battle); os 15 bits de
  `event=30` **incluem** Got Pokedex + parcel. Wall = não entra Route 2. Follow-up
  Discord/ckpt do autor no Mac.
- [25 — acc64 @ 35M from has_pokedex_nballs](issues/25-acc64-from-pokedex-nballs-35m.md) —
  ablação overnight: mesma geometria autor (64×2560, p16), init com dex+balls,
  um job até 35M (`039_…`). Testa se a parede é pós-dex.

## Not yet specified

- ~~Quais runs/baselines a v3 ganha como referência~~ — matéria-prima agora existe:
  células t05 (runs_t05_g*) + evals congelados do checkpoint do autor
  (runs_eval_peter{,_2,_3}). A seleção final é parte do veredito (ticket 09).
- Port do acumulador de batches pra v3 (se o ticket 06 decidir por ele na v2) — vive
  como nota no veredito, ticket próprio só se a v3 adotar a mesma geometria.
- Desenho da run longa de fallback, caso a rubrica só seja provável em escala completa.

## Out of scope

- Executar a run longa 440M até o fim — o mapa entrega o runbook e os gates; rodar é
  trabalho depois do handoff.
- Refatorar a v2 **além** da subclass do acumulador — a spec do ticket 06 e sua implementação delimitada (tickets 14–15) entram neste mapa; qualquer refactor maior é outro mapa.
- Corrigir/editar o mapa ou código da v3 — o veredito (ticket 09) é entregue como input;
  a decisão de mudar o Frozen é do esforço autoresearcher-gym.
- Formatar o AM18 pra Linux; qualquer gasto com cloud.
- Faint-reset como variável de reprodução (nfr é a config do autor).
