# 08 — Runbook da run longa (milestone-gated, teto ~35M, AM18)

Type: task
Status: open
Blocked by: 03, 07, 10

## Question

Produzir o runbook executável da run longa no AM18:

- **Config**: verbatim do autor (init.state, 18h/ep, nfr, heal ×10, stuck 600, seed 0)
  com a geometria decidida no ticket 06; qualquer desvio justificado.
- **Budget**: teto ~35M steps (janela N3 travada no ticket 03: Brock em 25–35M; o
  440M era da linhagem v1 e está aposentado); estimativa de wall-time a partir do
  SPS medido no ticket 07; enquadramento no orçamento semanal do AM18 (72–120h
  contínuas ou segmentos com resume).
- **Gates**: milestone-gated, não 440M cega — checkpoints de avaliação a cada ~50M
  (ou o que a rubrica do 03 ditar): para cedo se colapsar em farm (anti-padrão P1)
  ou se os milestones do autor caírem antes (Brock, Mt. Moon). Critérios explícitos
  de go/no-go por gate.
- **Operação**: comando de launch, resume, backup, observação (watch_progress /
  tensorboard), e o que fazer em crash.

Saída: o runbook completo como Answer. Executar a run é trabalho depois do handoff
(Out of scope do mapa).
