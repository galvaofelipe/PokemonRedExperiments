# 16 — Desenho da run maior de validação do acumulador

Type: grilling
Status: resolved
Blocked by: 15

## Question

Com os resultados da 3ª célula (ticket 15) na mão: qual a run maior que valida
(o condena) o acumulador como geometria padrão? Decidir budget (candidato:
~11M, o degrau N2 da rubrica — mas um meio-termo ou menos seeds podem bastar),
número de seeds, e os critérios em formato MUST/SHOULD/COULD.

Contexto (ticket 06): em 2M nenhuma geometria se separa — a pergunta real é
qual sustenta dose-resposta. O julgamento usa a rubrica do ticket 03 (pisos N2:
mmp ≥ 3, event_flags ≥ 6–7, coord ≥ 1.000, levels ≥ 12 + dose-resposta no eixo
de flags) e a comparação contra as células t05 A/B nas mesmas condições.

Usar /grilling. Saída: desenho da run + critérios MUST/SHOULD/COULD como
Answer.

## Interplay com o ticket 08 (registrado em 2026-09-13)

O desenho desta run maior e o runbook da run longa (ticket 08) se alimentam: a
rubrica (ticket 03) exige **dose-resposta + projeção de ritmo** pra liberar a run
longa, e a run desenhada aqui (candidata ~11M/N2) é exatamente a evidência que
esse go/no-go consome. Trabalhar este ticket sem abrir o 08 corre o risco de
desenhar duas runs longas redundantes. Ao resolver o 16, dar zoom no 08
(`08-long-run-runbook.md`) e considerar se a run N2 do acumulador já entra no
runbook como a perna de dose-resposta — e se os MUST/SHOULD/COULD daqui viram os
gates de liberação de lá.

## Answer

Resolvido em 2026-09-13 (grilling com o operador, 2 rodadas). A run maior vira
uma **célula comparativa de 3 braços em 11M, com resume dos checkpoints de 2M** —
não um braço único do acumulador.

### Desenho

- **3 braços, mesma seed por braço**: A (8×2.560, de `runs_t05_g2560_s*`),
  B (8×20.480, de `runs_t05_g20480_s*`), acc64 (64 lógicas × 8 físicas × 8
  rounds, de `runs_t15_acc64_s*`) — todos **resume do checkpoint exato de 2M**
  (`poke_1966080_steps.zip`, verificado presente nos 9 dirs). Resume validado no
  código: `baseline_fast_v2.py:303-314` escolhe `AccumulatingPPO` por rounds>1,
  `ppo_cls.load` restaura policy; SB3 com `reset_num_timesteps=True` (default)
  roda o `--total-timesteps` como steps **adicionais** (confirmado no fonte do
  venv, `base_class.py:_setup_learn`).
- **Budget: alvo absoluto 10.977.280 steps** (67 mega-updates = degrau N2 da
  rubrica). Resume adiciona **9.011.200** — exato nos 3 braços (55 mega-updates
  de 163.840 em B/acc64; 440 updates de 20.480 em A). ~3,6–4,2h por run no Mac.
- **Config verbatim t15** (`init.state`, nfr, heal ×10, stuck 600, gamma 0,997,
  reward v2 scale 0,5 → flags = `event ÷ 2`, episódios 16.384). Atravessa o
  cutoff 2M já julgado — comparabilidade 1:1 com t05/t15.
- **Seeds em 2 fases** (decisão do operador): fase 1 = **seed 0 nos 3 braços**
  (preview de 1 noite, fila acc64 → B → A); fase 2 = s1/s2 dos 3 braços (6 runs,
  ~24h de fila, quando o operador disser). t15 mostrou as 3 seeds muito
  parecidas; o veredito final é na mediana das 3, seed 0 sozinho é preview.
- **Leitura intermediária em ~5,5M é telemetria, não early-stop** — os jobs
  rodam os 11M.
- **Session-paths novos** `runs_t16_{g2560,g20480,acc64}_s*` com `--checkpoint`
  apontando pro zip de 2M (o SB3 reinicia a contagem em 0; paths novos evitam
  colisão de checkpoints). Extração soma offset +1.966.080.
- **Veredito: judgement call** como no t15 (agente no JSON/estatística, operador
  nos gráficos do TB, decisão junta).
- **Interplay com o 08**: decidido **não acoplar** — mantendo 11M, o runbook não
  entra nesta resolução. O SHOULD abaixo deixa a evidência N2/projeção pronta
  pro 08 quando ele destravar.

### Critérios (aprovados pelo operador)

- **MUST** (decide o destino do acumulador):
  1. **Sem underperformance clara**: acc64 na mediana das 3 seeds não fica fora
     do spread de A/B em flags/coord/levels; terminar claramente abaixo dos dois
     condena.
  2. **Dose-resposta viva**: flags do acc64 ainda tickando no último terço
     (taxa marginal > 0 entre ~7,3M e 11M). acc64 saturado com A/B subindo =
     deficit real confirmado, condena.
  3. **Saúde**: KL/entropy/EV na faixa do t15, 0 wipes anômalos, deaths/ep
     fleet-mean ≤ 4.
- **SHOULD** (responde o que 2M não respondeu; evidência N2 sem gatear runbook):
  1. **Forma resolvida (catch-up vs deficit)**: acc64 alcança/supera o platô que
     A mostrou em 2M e projeta continuar — lido direto das 3 curvas.
  2. **Pisos N2 na mediana da célula** (mmp ≥ 3, flags ≥ 6–7, coord ≥ 1.000,
     levels ≥ 12) e projeção de ritmo na escada mmp registrados no Answer do
     ticket de execução.
- **COULD**: calibração unique_maps/dex_seen (primeira run ≥11M com a telemetria
  do ticket 12); comparação externa com b11m_2hep (escala ÷4); perf sustentado
  (SPS/RAM em ~4h).

### Consequências

- Filho: **17 — Célula comparativa 11M (A/B/acc64, resume de 2M)** (task):
  executar as duas fases, extrair (offset +1.966.080, flags = `event ÷ 2`),
  veredito judgement call contra os MUST/SHOULD/COULD acima.
