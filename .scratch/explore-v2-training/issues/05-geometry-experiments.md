# 05 — Runs curtas de geometria (8×2.560 vs variantes)

Type: task
Status: resolved
Blocked by: 03, 04, 10, 12

## Question

Rodar as runs curtas que distinguem as geometrias candidatas, no Mac (8 envs, runs de
1–12h wall), e julgá-las **pela rubrica travada no ticket 03**. O desenho exato sai
dos tickets 03+04, mas a intuição do operador: tickets a cada ~2 dias com experimento
no meio; candidatos incluem 8×2.560 (status quo), 8×20.480, e acumulador 8-rounds se
o ticket 04 o viabilizar. Config verbatim do autor (Notes do mapa), só a geometria
varia.

Saída: resultados por célula contra a rubrica + a leitura "qual geometria sustenta
dose-resposta de progresso". Se nenhuma variante de 8 envs passar na rubrica, isso
**é** a evidência de que o refactor (64 streams via acumulador) é necessário.

## Answer

Resolvido em 2026-09-13. 6 runs (jobs 013–018): 2 células × seeds 0/1/2, config
verbatim do autor v2 (`init.state`, nfr, heal ×10, stuck, gamma 0.997, reward v2,
reward_scale 0.5), episódios 16.384 steps (2h de jogo), budget 2M/run. Avaliadas em
**steps casados** ≤2M (A rodou 2.007.040; B 2.129.920). **flags = `event ÷ 2`**
(reward_scale 0,5; na escala das 8 runs antigas seria ÷4). Fontes: `v2/runs_t05_g*`,
backups `v2/baselines/t05_*`, extração com `tb_extract.py`.

### Tabela (valores no cutoff 2M)

| run | flags_max | coord_max | levels_max | maps_max | dex_max | mmp | deaths_max | wipes |
|---|---|---|---|---|---|---|---|---|
| g2560 s0 | 7 | 359 | 6 | 6 | 4 | 2 | 5 | 0 |
| g2560 s1 | 8 | 368 | 7 | 6 | 4 | 2 | 5 | 0 |
| g2560 s2 | 8 | 374 | 7 | 7 | 4 | 3 | 7 | 0 |
| g20480 s0 | 7 | 477 | 6 | 6 | 4 | 2 | 3 | 0 |
| g20480 s1 | 7 | 304 | 7 | 6 | 4 | 2 | 4 | 0 |
| g20480 s2 | 7 | 449 | 6 | 6 | 4 | 3 | 3 | 0 |

Máximo-ao-longo-do-tempo (robustez contra flags resetarem por episódio):
A 7/8/8 flags, 413/599/487 coords · B 7/7/7 flags, 477/388/449 coords. Mesma foto.

### Contra a rubrica N1 (mediana das 3 seeds)

- **8×2.560 (A)**: flags 8 ✓ (≥4), coord 368 ✓ (≥350), levels 7 ✓ (≥7, no fio),
  deaths 5 ✓ (≤7). **Passa N1.**
- **8×20.480 (B)**: flags 7 ✓, coord 449 ✓, levels 6 ✗ (<7, falha marginal),
  deaths 3 ✓. Passa nos eixos primário/secundário, tropeça no piso de levels.
- Watch item: coord fleet-mean não é monótona na A (oscila ±15–30% entre terços:
  359→286→304, 270→382→305, 286→351→288). Não é o anti-padrão P1 (zero wipes, sem
  tendência de queda), mas não é "crescente sustentado" também. B cresce de base
  baixa (28→50→350) — 12 updates no budget vs 98 da A; curva tardia que fecha igual.

### Leitura: qual geometria sustenta dose-resposta

**Nenhuma se separa em 2M.** Eixo primário empata (mediana 8 vs 7, spreads
disjuntos por seed mas sobrepostos); coord pende pra B, levels pra A — tudo dentro
do ruído. Flags por episódio estagnam em ~7–8 nas duas (Peter congelado faz 20 em
2h — ver abaixo). A geometria de update do autor (163.840 amostras/update) emula-
da por horizonte (B) **não** compra dose-resposta extra nessa escala.

Consequência (decisão do ticket 04): como as duas não separaram, entra a **3ª
célula: acumulador 8-rounds** — é o ticket 06, agora com motivação empírica
concreta (não é mais "se").

### Referência de teto (calibragem nova — checkpoint do autor, política congelada)

`v2/eval_pretrained.py` (novo; só `model.predict`, zero updates) sobre
`runs/poke_26214400`, 8 envs × 3 episódios, 3 horizontes
(`v2/runs_eval_peter{,_2,_3}/eval_summary.json`):

| horizonte | badges | flags med/máx | levels med/máx | coords med/máx | maps med/máx | dex med/máx |
|---|---|---|---|---|---|---|
| 4h jogo | 8/24 | 20/48 | 14/41 | 3.170/5.289 | 22/37 | 14/32 |
| 8h jogo | 18/24 | 48/96 | 32/44 | 5.523/9.120 | 36/73 | 32/49 |
| 16h jogo | 16/24 | 37/105 | 31/62 | 4.968/9.889 | 31/76 | 27/50 |

Corte @2h (comparável ao episódio N1): flags média 17,5 / máx 20, levels 12/14,
coords 2.656/3.015. Zero wipes em 72 episódios; map máx 197 (além de Mt. Moon);
badge cai ~2:10–2:20 de jogo. **Os pisos N1 ficam 4–8× abaixo do teto observado**
— são portão de "aprendeu algo", como calibrados. From-scratch a 2M chega a ~40%
das flags de 2h da política competente. unique_maps/dex_seen calibrados: N1 from-
scratch máx 6–8 / 4 vs teto 22–37 / 14–32 @4h — sem threshold próprio, como
previsto no ticket 03.

Desbloqueia **06** (3ª célula = acumulador, motivada) e **07** (AM18).
