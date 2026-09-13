# 09 — Veredito: o env Frozen da v3 dá condições de convergir? (por propriedade)

Type: grilling
Status: open

## Question

Responder por propriedade do env, com evidência, numa tabela:
**propriedade × contornável via `train.py`? × veredito (OK / contornável / mudar o
Frozen antes de travar)**. Já investigado (subagente 2026-09-12, evidências com
arquivo:linha):

- **Reward é 100% Editable**: env recebe `config["reward"]` por injeção
  (`v3/frozen/env/red_gym_env.py:48`); implementação em `v3/train.py:33-141`
  (`DefaultReward`). O agente pode reescrever o reward inteiro respeitando o
  protocolo `reset/update/update_heal/group_rewards`.
- **Zeramento dividido no reset**: `DefaultReward.reset()` (Editable,
  `train.py:38-55`) zera event/heal/level maxima → agente *pode* torná-los
  não-renováveis. Mas `explore_map` e `seen_coords` são zerados **no env Frozen**
  (`red_gym_env.py:147,163-164`) → explore farm é estrutural, não contornável.
- **Faint-reset ausente**: `--early-stop` é flag morta na v3 (`train.py:180`; a
  lógica foi removida no split). Fora de escopo pra repro (autor não usava), mas o
  mapa da v3 precisa decidir conscientemente se importa.
- **Heal ×10 / morte sem penalidade / level reward inerte**: todos no `train.py`
  (Editable) — contornáveis pelo agente.
- **Score imune a hacking por construção** (scorer frozen, bits one-way) — o risco
  nunca foi o Score; é o treino não convergir.

A pergunta HITL: para cada linha estrutural (explore zeroing, faint-reset, e o que
mais a conversa levantar), **mudar o Frozen agora** (antes de travar) ou deixar e
documentar? A saída é input pro mapa do autoresearcher-gym — a decisão de aplicar é
de lá. Usar `/grilling` e `/domain-modeling`.
