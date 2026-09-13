# 10 — Qual linhagem reproduzir: o artefato 440M (2022) ou a config v2 (2025)?

Type: grilling
Status: resolved

## Question

O ticket 01 revelou que a run de 440M steps (Brock, Mt. Moon) **não** usou a config
que chamamos de "v2":

- **Linhagem original (2022)** — a do artefato: 44 envs × 16.384 steps/episódio
  (≈2h in-game), `n_steps = ep_length` (um update = 44 episódios completos =
  720.896 amostras), batch 512, epochs 1, gamma 0.999, `has_pokedex_nballs.state`
  (começa com pokédex + pokéballs), reward antigo: level×100, hp×2000,
  explore-KNN×160, badge×2, dead −0.1 — env v1 (`baselines/red_gym_env.py`).
  Evidência: `git show 5330c5d:baselines/run_baseline_parallel.py` +
  `Visualizations_over_time.ipynb` (610 × 16.384 × 44 = 439.746.560 exatos).
- **Linhagem v2 (2025)** — o que nosso fork e a v3 congelaram: 64 envs × 2.560
  (163.840 amostras/update em fragmentos), 18h/episódio, `init.state` (do zero),
  gamma 0.997, reward simplificado (level off, heal ×10, stuck 600). Claim pública:
  Cerulean (README:60) e "from the very start to ss anne" (commit `2f79c5a`) —
  **sem budget publicado, sem checkpoint, sem telemetria**.

A tensão: o único "senso de sucesso" com budget conhecido (440M → Brock/Mt. Moon)
pertence à linhagem v1, mas o veredito de env que importa pra v3 é sobre a linhagem
v2 (é o que ela congelou). Decidir:

- (a) **Reproduzir a v1 verbatim** — âncora externa forte (resultado e budget
  conhecidos), mas valida um stack que a v3 não usa.
- (b) **Reproduzir a v2 verbatim** — evidência direta pro veredito da v3 e nossas
  8 runs já são dessa linhagem, mas sem âncora quantitativa externa (Cerulean em
  quantos steps? ninguém publicou).
- (c) **Híbrido** — alvo principal v2; v1 como cheque de plausibilidade ("o jogo é
  aprendível até Brock em ≤440M com reward denso antigo").

A resposta trava: a geometria dos experimentos do ticket 05, a rubrica N3 do
ticket 03, e a config do runbook do ticket 08.


## Answer

Decidido com o operador em 2026-09-12: **(c) híbrido com centro de gravidade em (b)**.

- Alvo principal da reprodução: a **linhagem v2** (2025) — é o stack que a v3
  congelou, e nossas 8 runs já são dela. O veredito de env pro auto-researcher diz
  respeito a essa linhagem.
- A run de 440M da linhagem v1 (2022) serve como **cheque externo de
  plausibilidade**: "o jogo é aprendível até Brock em ≤440M com o reward denso
  antigo" — não como alvo.
- Ressalva explícita do operador: uma conclusão possível e **aceitável** deste mapa
  é que **a v3 como pensada originalmente é inviável** — se a linhagem v2 exigir
  ordens de magnitude mais recurso pros mesmos marcos, a comparação 440M↔v2 estava
  errada desde o início e o mapa da v3 precisa ser repensado.
- Antes de travar a rubrica (ticket 03), verificar o que existe de resultado
  comprovado da linhagem v2/PufferLib e a que custo (ticket 11) — inclusive no
  Discord PokeRL, onde a comunidade usa PufferLib.
