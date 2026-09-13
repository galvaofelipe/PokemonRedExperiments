# 07 — Benchmark do AM18 (WSL2): teto de envs e SPS

Type: task
Status: open
Blocked by: —

## Question

Eliminar a incerteza de hardware do AM18 **sem formatá-lo**: clonar este repo lá,
configurar WSL2 + deps, e medir. Checklist pro operador (HITL — o acesso físico e o
Windows são do humano; o agente prepara os comandos):

1. WSL2 + Python + deps do projeto (PyBoy, stable-baselines3) funcionando.
2. Smoke run de ~30 min da v2 com 8 envs — SPS agregado?
3. Escalar envs (10, 12, 16) — onde o SPS agregado satura? (No Mac: 8→10 envs rendeu
   só +2–8%; head serial + time-slicing, ver STUB § Fork vs upstream.)
4. Estabilidade: run de algumas horas sem crash; uso de RAM por env.

Timebox de decisão (combinado, Q4): se WSL2+deps+smoke não estiverem ok em ~1 dia de
trabalho, registrar o bloqueio — cloud continua fora de escopo, então o plano B é
repensar o orçamento de runs no Mac.

Saída: SPS medido por config, teto prático de envs, e o que isso faz com o orçamento
"várias runs 24–48h ou uma 72–120h por semana".

## Medições (2026-09-13, AM18 WSL2)

Checklist: (1) WSL2+deps ✓ (venv uv, torch 2.5.0+cpu); (2) smoke SPS ✓; (3) saturação
de envs ✓; (4) estabilidade de horas — **pendente** (só bursts de 2–10 min; falta a
validação steady-state de 30–60 min na geometria escolhida).

Harness: `v2/bench_sps.sh` (sweep físico) + `v2/bench_geometry.sh` (geometrias Mac).
Telemetria corrigida nesta sessão (`v2/resource_callback.py`): no Linux footprint =
**PSS** (smaps_rollup; RSS somado double-conta páginas de fork) e cpu_pct = **intervalo**
(deltas de /proc stat; ps %cpu é média lifetime). Colunas mem/cpu **não** são
comparáveis com os números do Mac — comparar só SPS.

**Sweep físico** (stock n_steps 2560): SPS total 1→188, 2→303, 4→495, 8→744, 9→745,
10→749, 11→788, 12→825, 16→909, 20→1033, 24→1047, **28→1094 (pico)**, 32→1025 (queda
com RSS somado 25,4 GB > cap 24 GB → pressão de memória). Platô duro em 9–10 envs (=
núcleos físicos). Dados: `v2/bench/bench_results.csv`.

**Bench de geometrias** (2 mega-updates por célula; `v2/bench/bench_geometry.csv`):

| célula | lóg/fís | avg SPS | pico footprint (PSS) | pico CPU |
|---|---|---|---|---|
| g2560 (A) | 8/8 | 740 | 5,9 GB | 769% |
| g20480 (B) | 8/8 | 526 | 22,9 GB | 777% |
| acc64_p8 | 64/8 | 715 | 22,9 GB | 770% |
| acc64_p16 | 64/16 | 863 | 22,9 GB | 781% |
| acc40_p8 | 40/8 | 738 | 19,0 GB | 772% |
| acc40_p20 | 40/20 | **1008** | 21,4 GB | 821% |
| acc48_p16 | 48/16 | 896 | 22,8 GB | 780% |
| acc80_p16 | 80/16 | **DNF** | — | ver abaixo |

**acc80 não cabe no cap de 24 GB**: buffer de 204.800 amostras (~21 GB) + 16 envs
estourou RAM **e** o swap de 16 GB aos 98,5% da 2ª mega-update — WSL inteiro travou
(sps=0, CPU caindo pra ~50%, thrash por 7+ min até `wsl --shutdown`). acc80_p20 nem
foi rodada (mesmo buffer + 4 envs). Falha de modo duro: sem OOM-kill rápido, o WSL2
entra em espiral de swap. Não repetir sem a dieta do ticket 18.

Regra de bolso calibrada pelas células: **buffer ≈ 105 KB/amostra** (lógicas × n_steps)
**+ ~0,6 GB por env físico**. No cap de 24 GB: 64 lógicas é o teto prático (no fio);
80 lógicas é impossível — nem subindo `.wslconfig` pra 27 GB fecha (21,5 GB de buffer
+ envs). Se 40–80 lógicas virar norma, 40–48 roda hoje, 64 no fio, 80 só com memmap.

Leituras: o buffer de 163.840 amostras custa **~17 GB** aqui (não ~11 GB da telemetria
Mac); B é dominada (a mais lenta E no teto de RAM — segura o buffer gigante durante o
rollout); acc40_p20 é a mais rápida do bench e ainda fica ~2,5 GB abaixo do cap;
A e acc40_p8 são as únicas com folga larga de RAM. Pico CPU ~7,7–8,2 núcleos de 16
em todas as células — teto do head serial, não da geometria.

**Recomendação provisória**: **acc40_p20** é o sweet spot de throughput com margem
(1008 SPS, 21,4 GB). Se a geometria de 64 streams for exigida: acc64_p16 com uma de —
subir `.wslconfig` pra 26–27 GB (caixa tem 30), dieta do acumulador (ticket 18), ou
cair pra 40–48 lógicas. 80 lógicas só com a dieta de memmap. Maratona de uma semana
exige validação steady-state antes; soak térmico deve derrubar o SPS absoluto em
~10–20%.

**Validação externa** (system-wide, fora do processo, `scripts/mem_watch.py`): PSS
externo bate com o in-process (22,79 vs 22,82 GB de pico, 0,2%), mas revelou que
acc64_p8 **já swapava** no cap de 24 GB — MemAvailable mínimo de 218 MB e swap
0,4→5,3 GB no pico do train; demanda real da árvore ~27–28 GB (PSS só conta
residente). Pra 64 streams a mitigação (RAM ou dieta) é **obrigatória**, não
opcional. Detalhes em `docs/perf/am18.md` § External validation.
