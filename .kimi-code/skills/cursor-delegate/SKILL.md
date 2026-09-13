---
name: cursor-delegate
description: Delegar implementação ao Cursor via MCP cursor-delegate neste repo. Use quando o usuário pedir "delega pro Cursor/Composer" ou offload de edição multi-arquivo em código/scripts. NÃO use para edição trivial (1-2 arquivos), conteúdo de wiki/docs, nem bookkeeping GTD (tickets, map.md, TODO.md, commits) — esses são sempre trabalho direto meu.
---

# Delegar ao Cursor neste repo

Decisões fixas (não rediscutir sem pedido do usuário): modelo default `composer-2.5` (barato, throughput); `grok-4.6` quando o usuário pedir "o modelo capaz"; `fast: true` só com pedido explícito (custa mais).

- `workspace`: menor diretório que contém os arquivos da tarefa; piso = raiz do repo.
- Decisões que o usuário enunciar (valores, formatos, textos exatos) vão verbatim no brief, em qualquer idioma.

Ponteiros (vivem na home do usuário, não no repo):
- Workflow de delegação (brief em 4 partes, plan mode, resume, revisão): ler `~/.agents/skills/delegate/SKILL.md` antes do PRIMEIRO `delegate` da sessão. Não ler para decidir SE delega (esta página basta), nem nas delegações seguintes da mesma sessão.
- `~/.agents/skills/delegate/reference.md`: ler SÓ quando uma delegação falhar (tabela reason→ação) ou para usar `effort`/`context`/`contextFiles`. No caminho feliz, não ler.

Pós-delegação (sempre, eu mesmo): `git diff` + verificação independente (`bash -n` em scripts, reler arquivos alterados contra os critérios do brief) — o relatório do Cursor não é evidência. Se algo quebrar no setup: tool `doctor` com `deep: true`.
