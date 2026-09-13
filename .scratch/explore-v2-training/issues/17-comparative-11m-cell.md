# 17 — Célula comparativa 11M: A/B/acc64 com resume de 2M

Type: task
Status: open
Blocked by: 16

## Question

Executar a run maior desenhada no ticket 16: 3 braços (A = 8×2.560, B =
8×20.480, acc64 = 64 lógicas × 8 físicas × 8 rounds) com **resume do checkpoint
exato de 2M** (`poke_1966080_steps.zip` das células t05/t15), alvo absoluto
10.977.280 steps (resume adiciona 9.011.200 = 55 mega-updates / 440 updates-A,
exato). Config verbatim t15.

- **Fase 1**: seed 0 nos 3 braços, fila acc64 → B → A (jobs 022–024, preparados
  pelo agente; operador roda `cd v2 && ./run_queue.sh`, ~4h cada, ~12h total).
- **Fase 2**: s1/s2 dos 3 braços (6 runs, ~24h), quando o operador disser —
  jobs a preparar na hora (mesmo modelo, `--seed` e paths de s1/s2).
- **Extração**: `tb_extract.py` + `cell_table.py` com **offset +1.966.080** (o
  SB3 reinicia a contagem no resume; os TB logs da fase t16 começam em 0).
  flags = `event ÷ 2`. Mesma tabela do ticket 05/15, cortes em 5,5M e 11M
  absolutos. Comparável 1:1 com t05/t15 no cutoff 2M.
- **Veredito: judgement call** (agente no JSON/estatística, operador no TB,
  decisão junta) contra os MUST/SHOULD/COULD do Answer do ticket 16.

Saída: tabela 3 braços × 3 seeds × métricas nos cortes + veredito registrado
(adota/condena o acumulador; catch-up vs deficit respondido; evidência N2 e
projeção de ritmo registradas pro ticket 08).

## Notas operacionais

- acc64 precisa de `--num-envs 64 --physical-envs 8` explícito (a fila não
  exporta `V2_PHYSICAL_ENVS`).
- Session-paths novos `runs_t16_*`; `--checkpoint` recebe o path **sem** o
  sufixo `.zip` (ex.: `runs_t15_acc64_s0/poke_1966080_steps`).
- Checkpoints de 2M verificados presentes nos 9 dirs de origem (2026-09-13).
- Estimativa: ~3,6–4,2h/run (~600–710 SPS); pico RSS esperado 6–8 GB (acc64).

## Comments

**2026-09-13 — jobs da fase 1 preparados e validados (agente).**
`v2/jobs/022_t16_acc64_s0.json`, `023_t16_g20480_s0.json`, `024_t16_g2560_s0.json`
(ordem de fila = ordem alfabética = acc64 → B → A, como decidido no 16). Args =
modelo t05/t15 + `--checkpoint runs_*/poke_1966080_steps` (sem `.zip`) +
`--total-timesteps 9011200` (steps **adicionais** — SB3 resume com
`reset_num_timesteps=True`, confirmado no `base_class.py` do venv). Validados
replayando cada args[] pelo parser real de `baseline_fast_v2.py`: acc64
logical=64 physical=8 rounds=8 update=163.840; alvo absoluto
1.966.080 + 9.011.200 = **10.977.280 exato nos 3 braços** (55 mega-updates em
B/acc64, 440 updates de 20.480 em A); checkpoints de 2M existem nos 3 paths.
Fila estava vazia (só .status antigos). Falta: operador rodar
`cd v2 && ./run_queue.sh` (~4h cada, preview das 3 ~12h depois do start), depois
fase 2 (s1/s2) e extração com offset +1.966.080.

**2026-09-13 ~14:30 — prévia seed 0 acc64 (agente; run terminou 14:03, 3h33m wall, 712 sps).**
TB remendado com `tb_stitch.py` (curva contínua 0→10.977.280 em
`runs_t16_acc64_s0/poke_ppo_1`). Sanidade: valores @2M batem exato com t15 s0.
Cortes (flags = `event ÷ 2`): @2M flags 7/coord 306/levels 6/mmp 2 → @5,5M 8/613/13/3 →
@7,3M 9/672/7/3 → @11M **15/1383/8/3**. Max-along-run: flags 15, coord 1.383,
levels 14, maps 13, dex 7, mmp 3, pcount 1, badge 0. Seed 0 sozinha passa os 4
pisos N2 (mmp 3 ✓, flags 15 ≥ 6–7 ✓, coord 1.383 ✓, levels_max 14 ≥ 12 ✓).
Régua "Brock level" do operador (eval_peter_3): falha nas 5 (flags 15<25,
levels 14<25, maps 13<25, dex 7<25, pcount 1<2) — esperado, sem badge.
Dose-resposta viva (MUST 2 ✓): flags 9→15 no último terço, acelerando após
~9,8M; forma NÃO estagnou — o "deficit" do 2M está descartado pra seed 0.
Saúde ✓: KL med 0,0075 (faixa t15), EV med 0,98, 0 wipes, deaths/ep med 5
(max 12). **Watchpoint**: mmp travado em 3 desde ~2,3M (8,7M steps) — mesma
muralha do b35m; flags/maps/dex sobem dentro do early game mas Pewter (mmp 6)
não aparece. env_stats_max reseta por episódio → valores no cutoff ruidosos,
usar max-along-time. Falta: B (023, ETA ~17:45) e A (024, ETA ~21:15) pro
MUST 1; depois stitch das duas (offset 1966080) + tabela comparativa +
veredito judgement call com o operador.

**2026-09-13 ~18:20 — prévia seed 0 braço B (agente; run terminou 17:51, 3h48m wall, 667 sps).**
Bug encontrado e corrigido no `tb_stitch.py`: leg1 do B teve overshoot pra
2.129.920 (job original pedia 2.000.000, SB3 parou na fronteira de update);
leg1 agora é clipada no offset (steps > offset descartados — o resume re-feita
esses steps). Stitch validado: 0→10.977.280 contínuo, sem duplicatas.

Cortes B (flags = event÷2): @2M 7/477/6/6/2 → @5,5M 8/800/7/10/3 → @7,3M
8/744/9/10/3 → @11M **9/840/7/10/3** (flags/coord/levels/maps/mmp). Max-along-run:
flags 13, coord 1.171, levels 13, maps 12, dex 7, pcount 1, badge 0. Régua
Brock-level: falha nas 5 (esperado). Saúde ✓ (KL med 0,0074, EV 0,987, 0 wipes,
deaths/ep med 4).

**B vs acc64 (seed 0) — separação emergindo no último terço**:
dose-resposta de flags 7,3M→11M: **B Δ+1 (8→9, saturando) vs acc64 Δ+6 (9→15,
acelerando)**. @11M: flags 9 vs 15, coord 840 vs 1.383, maps 10 vs 13, dex 7=7,
levels 7≈8. Curva de unique_maps acumulado: idênticas até ~7M (B levemente à
frente cedo: 9 mapas @4,1M vs 7), depois acc64 abre (13 vs 12). MUST 1: acc64
não está abaixo de B — está **acima** em flags/coord/maps. mmp travado em 3 nos
dois (granularidade baixa; operador: usar unique_maps como eixo fino — breadth
> depth no early game, rewards de depth esparsas). Os dois com pcount 1 (nunca
capturou 2º pokémon) e dex 7 — nenhum pegou a pokédex; a muralha mmp 3 ↔
ausência de depth é o gargalo visível. Braço B rodou já com a telemetria de
footprint nova: pico reportado ~29GB (8 envs stock) — dado pro ticket 18
(footprint inclui retenção de malloc; comparar com medição externa).
Falta: A (024, ETA ~21:20) + fase 2 (s1/s2) pro veredito na mediana.
