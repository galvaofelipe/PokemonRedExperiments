# 18 — Memória: re-baselinar picos (footprint) e decidir dieta do acumulador

Type: task
Status: open
Blocked by: —

## Question

A telemetria de memória até 2026-09-13 media `ps rss` somado na árvore, que no
macOS fica ~4,5× abaixo do **phys_footprint** (o número do Activity Monitor) e
só amostrava em `_on_step` — cego à fase de `train()`, onde o buffer encadeado
do acumulador (163.840 amostras ≈ 11GB) faz o pico. Medição ao vivo na run
t16_acc64_s0: **footprint da árvore 16,8–17,6GB / resident 3,9GB** num Mac de
16GB — ou seja, macOS está comprimindo/swappando pra caber, e o "pico RSS
6–8GB, dentro do orçamento" do ticket 15 é a mesma métrica furada.

Com a telemetria corrigida (commit pendente: `v2/resource_callback.py` mede
footprint via `proc_pid_rusage` e amostra por thread cobrindo o train;
`watch_progress.py` exibe footprint + residente):

1. **Re-baselinar**: picos reais de footprint de A/B/acc64 nas runs t16 (a fase
   1 já roda com a métrica velha — picos de footprint dela saem por medição
   externa ou ficam pra fase 2). Revisitar a conclusão de orçamento do t15.
2. **Decidir dieta do acumulador** (se o pico incomodar): `del` do buffer de
   cada round após o concat, fallback `np.memmap` das obs (já registrado no
   ticket 06, não implementado), ou aceitar — SPS não pareceu sofrer (avg ~680
   com footprint de 17GB).
3. **Alimentar o sizing**: ticket 07 (benchmark AM18) e o runbook (08) devem
   usar footprint, não rss — 64 lógicas no AM18 com 16 físicas pode estourar a
   RAM se o pico por mega-update escalar com rounds.

Caveat conhecido: somar footprint na árvore pode double-countar páginas
compartilhadas pai↔filho (fork/COW). Bom o bastante pra teto; não é contabilidade
exata.

Saída: picos reais por geometria + decisão (dieta sim/não/qual) registrados como
Answer; números de footprint referenciados nos tickets 07/08.
