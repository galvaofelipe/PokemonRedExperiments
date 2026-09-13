# 03 — Travar a rubrica de conversão

Type: grilling
Status: resolved
Blocked by: 01, 02, 10, 11

## Question

Decidir, com a evidência dos tickets 01 e 02 na mesa, a **rubrica de conversão**:
o que conta como "a v2 converge no mesmo grau no nosso hardware". Forma proposta
(a refinar na conversa):

- **N1 (curta, ~2–35M steps)**: sinais de dinâmica saudável — exploração/eventos/
  levels crescendo de forma sustentada, sem o anti-padrão P1 (wipes encurtando,
  coord_count caindo). Thresholds numéricos a fixar.
- **N2 (média)**: progressão real de jogo na telemetria — qual conjunto de eventos/
  mapas/progress conta como "o jogo andando" (ex.: sair de Pallet, Viridian, pokédex,
  progress ≥ 2 sustentado)?
- **N3 (longa, 440M)**: o artefato do autor — Brock, Mt. Moon — usado só como gate da
  run longa.

E a formulação-chave do operador: a rubrica deve poder ser avaliada como **dose-
resposta** — "aumentar o budget continua aumentando o progresso" — de modo que runs
curtas deem sinal suficiente pra liberar (ou não) uma run longa.

Saída: thresholds fixados + como medi-los (qual telemetria, qual janela), registrados
como Answer. Usar `/grilling` e `/domain-modeling`.

## Answer

Resolvido em 2026-09-12 (grilling com o operador, 2 rodadas + investigação das
métricas da v3). Rubrica travada:

### Estrutura (híbrida)

N1 e N2 são **pisos de corte rápido** (config que falha N1 não gasta 4h); a decisão
de liberar a run longa vem da **forma da curva dose-resposta** + **projeção de
ritmo** até N3. "Converge no mesmo grau" = as flags de história continuam tickando
quando o budget aumenta, num ritmo que projeta Brock dentro da janela N3.

### Hierarquia de métricas

- **Eixo primário (carrega a dose-resposta)**: `event_flags` — contagem crua de
  flags de história (nas 8 runs existentes = `env_stats/event ÷ 4`). Monótono
  (bits set-once), denso (centenas de bits em jogo saudável), zero recompensa por
  passear. É o componente `events` do Score v3 (`v3/frozen/scorer/core.py`), que a
  v2 já mede com faixa um pouco mais estreita.
- **Eixos secundários**: `unique_maps` (telemetria NOVA — ticket 12; set cumulativo
  de map ids, teto 248), `coord_count` (rebaixado: crescer sozinho não conta como
  progresso), `levels_sum`, `dex_seen` (telemetria NOVA — ticket 12; auxiliar de
  engajamento em batalha; ruído de sorte se cancela em horizonte longo).
- **Portões** (passou/não passou): `mmp` (escada de 15 mapas; Brock = mmp ≥ 7),
  `badge` bit 0.
- **Saúde** (nunca progresso): deaths/ep, wipe_rate/wipe_len (fr5), hp médio.

Escada mmp (verificada contra pokered `map_constants.asm`): 0 Oak's Lab, 1 Pallet,
2 Rota 1, 3 Viridian City, 4 Rota 2, 5 Viridian Forest, 6 Pewter City, 7 **Pewter
Gym (Brock)**, 8 Rota 3, 9–11 Mt. Moon, 12 Rota 4, 13 Cerulean, 14 Cerulean Gym.
Nosso melhor (b35m) = mmp 3; o autor a 26M passou do 14.

### Níveis e thresholds

- **N1 (~2M steps, ~45 min, 3 seeds, julgado na mediana)** — pisos:
  `event_flags ≥ 4` (= event_max ≥ 16 na escala antiga), `coord_max ≥ 350`,
  `levels_sum ≥ 7`. Saúde: deaths/ep máx ≤ 7. Reprovação imediata: levels ≈ 0;
  mmp 1 com event ≤ 2; coord fleet-mean caindo entre terços.
- **N2 (~11M steps, ~4h, ≥2 seeds)** — pisos: `mmp ≥ 3`, `event_flags ≥ 6–7`
  (event_max ~26), `coord_max ≥ 1.000`, `levels_sum_max ≥ 12`. Dose-resposta:
  `event_flags` ainda tickando entre o fim do t2 e o fim da run (taxa marginal > 0)
  e coord ainda crescente. Saúde: deaths/ep fleet-mean ≤ 4.
- **Projeção de ritmo (obrigatória pra liberar a run longa)**: o progresso na
  escada mmp vs budget deve projetar **mmp ≥ 7 dentro de 25–35M**. Config parada
  em mmp 3 sem movimento desde ~9M falha a projeção — o b35m atual falharia.
- **N3 (run longa)**: Brock (badge bit 0 / mmp ≥ 7) dentro de **25–35M steps
  totais**. O 440M está aposentado como número-guia (linhagem v1: outra config,
  outro reward, outro init state).

### Multi-seed

N1 sempre 3 seeds (3×45 min), julgado na mediana; N2 e liberação da run longa
exigem ≥2 seeds. A "dose-resposta" das 8 runs antigas é **1 curva** (seed 0 +
determinismo, bit-a-bit) — vale como calibração dos pisos, não como prova.

### Regime e telemetria

Rubrica **agnóstica de regime** (definida em steps globais). Episódios de 18h foram
erro de dimensionamento das 3 primeiras runs, não um regime a preservar — tamanho
de episódio é decisão de config (tickets 05/06), e a resolução de telemetria vem de
episódios bem dimensionados. `unique_maps` e `dex_seen` não existem nas 8 runs
antigas: entram sem threshold próprio por ora, calibrados nas primeiras runs novas
(depende do ticket 12).

### Caveats

Thresholds calibrados no **piso da baseline doente** (n=1, seed 0, pinhata P1/P2
ativa) — são pisos de corte, não o teto do env. Badge excluído dos thresholds
curtos (sinal fraco no autor e na baseline nessa escala).
