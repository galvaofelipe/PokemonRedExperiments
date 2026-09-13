# 20 — Manifesto de performance do mac-mini (docs/perf/mac-mini.md)

Type: task
Status: open
Blocked by: —

## Question

**Rodar no Mac.** O AM18 publicou `docs/perf/am18.md` (convenção em
`docs/perf/README.md`); falta o manifesto do mac-mini pra fechar o par. Conteúdo:

- Hardware/config: chip, RAM, macOS, versão do torch, estado do venv.
- Método: quais harness rodaram (`v2/bench_sps.sh`, `v2/bench_geometry.sh` — ambos
  assumem `../.venv/bin/python` a partir de `v2/`), tamanho dos bursts, data.
- Tabelas: SPS por contagem de envs (sweep físico) e SPS/pico de footprint por
  geometria (g2560 / g20480 / acc64). Reusar números já medidos onde sólidos —
  ex.: footprint 16,8–17,6 GB do acc64 medido ao vivo no t16 (ticket 18) — marcando
  o método de cada número (phys_footprint via proc_pid_rusage = Activity Monitor).
- Geometrias recomendadas pro Mac + folgas de RAM (caixa de 16 GB rodou acc64 com
  footprint ~17 GB → compressão/swap ativo; registrar o custo disso em SPS se houver).
- Caveats: bursts vs soak; cpu_pct no Mac é média lifetime (subestima picos).

Regra da convenção: **não** comparar colunas de mem/cpu com o manifesto do AM18
(PSS + CPU de intervalo) — só SPS é comparável entre máquinas. RAM se dimensiona
por máquina.

Saída: `docs/perf/mac-mini.md` commitado, linkado de `HANDOFF-mac-share.md`.

## Comments
