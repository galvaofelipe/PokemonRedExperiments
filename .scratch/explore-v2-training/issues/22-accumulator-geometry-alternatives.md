# 22 — Alternativas ao 64 lógico: geometrias de acumulador que performam melhor no AM18

Type: research
Status: open
Blocked by: 21

## Question

O default de 64 streams lógicas (ticket 15/16) foi herdado do Mac, mas no AM18 o
pico medido de throughput é acc40_p20 (1008 SPS vs 863 do acc64_p16 sob o cap
antigo de 24 GB — ver `docs/perf/am18.md`). Com o `.wslconfig` agora em 27 GB /
32 GB swap, o acc64_p16 cabe sem thrash, mas a pergunta de fundo continua aberta:
**qual geometria de acumulador maximiza SPS sustentado nesta máquina sem ficar na
borda da RAM?**

Candidatas a benchear (mesma harness do ticket 07, `v2/bench_geometry.sh`):

- **acc60_p20** — buffer ~154k amostras (~16 GB), 20 físicas (pico do sweep raw).
- **acc54_p18** — buffer ~138k amostras (~14,5 GB), split 3:1.
- **acc48_p20** — buffer ~123k, split menor, mais margem.
- Re-bench do acc40_p20 e acc64_p16 sob a nova config como baselines.

Premissa a validar primeiro: o bench antigo mostrou SPS caindo com mais streams
lógicas a n_steps fixo — serial head da mega-update (concat + train) cresce com o
buffer enquanto o rollout já está no platô de CPU (~9–10 núcleos). Se isso se
confirmar, o ótimo desta máquina pode ser < 64 lógicas, e o "64" vira default só
do Mac.

Critério de aceite: tabela SPS × geometria sob a config nova (27 GB/32 GB swap),
incluindo validação steady-state de 30–60 min da vencedora, e recomendação de
default de produção registrada no `docs/perf/am18.md`.

Nota: saída do ticket 21 (auditoria de RAM) pode mudar o custo por amostra e
reescrever a tabela de candidatas — por isso este ticket está bloqueado por ele.
Se a dieta do ticket 18 cair antes, incluir uma célula de revalidação.

Relacionado: 21 (auditoria de RAM, bloqueador), 18 (dieta memmap), 07 (bench
AM18), 15/16 (default 64 e desenho da run grande).

## Comments
