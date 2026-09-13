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
