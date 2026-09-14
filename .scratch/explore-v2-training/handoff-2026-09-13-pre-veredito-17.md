# Handoff — explore-v2-training, pré-veredito do 17 (fase 2 rodando)

Data: 2026-09-13 ~22:15. Repo: `/Users/luizfelipegalvaoramos/dev/PokemonRedExperiments`.
**Substitui** `handoff-2026-09-13-post-ticket-16.md`. Ler junto com `HANDOFF.md`
(raiz — lado AM18, sessão paralela) e `HANDOFF-mac-share.md`.

## O que fazer na próxima sessão (quando as 6 runs fecharem, ~14/09 fim de tarde)

1. **Conferir a fila**: `v2/jobs/*.status` — 6 jobs done (024_t16_acc64_s1 …
   029_t16_g2560_s2), logs em `v2/logs/t16_*_s{1,2}.log`. Fila foi iniciada pelo
   operador ~22:10 de 13/09; ~3,5–4h por run.
2. **Extrair a tabela 3×3** (3 braços × 3 seeds, cortes 2M/5,5M/7,3M/11M):
   - flags = `event ÷ 2`. Ferramentas em `.scratch/explore-v2-training/scripts/`.
   - **Fase 2 NÃO precisa de tb_stitch**: jobs usam `--target-steps` (resume-global,
     commit 696169a) — leg2 sai em `runs_t16_*_s{1,2}/poke_ppo_1` já em steps
     globais. Extração = concatenar leg1 (`runs_t05_*_s{1,2}/poke_ppo_1` ou
     `runs_t15_acc64_s{1,2}/poke_ppo_1`) + leg2, **clipando a leg1 em 1.966.080**
     (legs de B têm overshoot de eventos até 2.129.920 — mesmo bug que o
     tb_stitch aprendeu a tratar; `tb_extract.load_series` lê um dir só, fazer
     merge manual das duas séries).
   - **Seed 0 já está stitchada** (`runs_t16_*_s0/poke_ppo_1`, 0→11M contínuo) —
     usar como está.
3. **Mesma análise das prévias** (template nos comments do ticket 17): tabela de
   cortes, max-along-run, régua Brock-level do operador (pcount ≥ 2, flags ≥ 25,
   dex ≥ 25, levels ≥ 25, maps ≥ 25 — de `runs_eval_peter_3/full_stdout.txt`),
   dose-resposta no último terço, curva de unique_maps, saúde, perf.
   **Julgar em max-along-time** — `env_stats_max` reseta por episódio; valor no
   cutoff é ruidoso (errei uma leitura por causa disso, correção no 17).
4. **Veredito judgement call** (agente no JSON + operador no TB) contra os
   MUST/SHOULD/COULD do Answer do ticket 16, na **mediana das 3 seeds** →
   resolver o 17 (Answer) + atualizar `map.md` (Decisions-so-far).
5. **Depois do 17**: 09 (veredito env-v3, grilling, ~80% no corpo), 08 (runbook —
   destrava quando o 07 for fechado; bench já medido), 19 (ready-for-agent),
   cluster memória 18/20/21.

## Estado persistido (não re-investigar)

- **Seed 0 completa (prévia, não veredito)** — nos comments do ticket 17. Gist:
  acc64 **empatado com A no topo** (flags max 15=15; A destravou antes, 9,2M vs
  10,0M; B estacionou em 13). MUST 1/2/3 ✓ na seed 0. Ninguém passa a régua
  Brock-level (esperado). **mmp 3 travado nos 3 braços desde ~2–3M** — a muralha
  é depth, não breadth (pcount 1, dex 7, ninguém pegou a pokédex); unique_maps
  (eixo fino, decisão do operador) segue tickando: 12–13 mapas.
- **Correção de leitura registrada**: "forma limitada por contagem de updates"
  (ticket 15) **enfraqueceu** — A com 538 updates não estagnou e destravou flags
  primeiro na seed 0. Em 11M os 3 braços convergem pra vizinhança parecida.
- **AM18 benched** (sessão paralela, ticket 07 ainda `open` — medido, falta
  resolver): pick **acc40_p20** (1008 SPS, 21,4 GB); 64 lógicas no fio (swap!),
  80 impossível (travou o WSL — não repetir sem a dieta do 18). Regra: buffer ≈
  105 KB/amostra (lógicas × n_steps) + ~0,6 GB/env físico. `docs/perf/am18.md`.
- **Resume-global** (`--target-steps`/`--base-steps`, commit 696169a): zips das
  legs novas guardam steps globais → extensões futuras não precisam de
  `--base-steps`. Zips Mac t16 (fase 1) guardam steps da perna → estender eles
  exige `--base-steps 10977280`. Ticket 19 (`ready-for-agent`) = sistema completo
  (sidecars, ledger, refs portáveis; "extend run" é o workflow primário).
- **Tower share**: `$POKERED_DATA/pokered/runs/v2/` — checkpoints seed-0 dos 3
  braços publicados (t16_acc64_s0, t16_g20480_s0, t16_g2560_s0) + pais t05/t15.
  Dirs `runs_t05_*` duplicados no share = resíduo cosmético da sessão paralela.
- **Commit e07a141 mal rotulado** (já pushed): carrega o código do ticket 18
  (footprint) sob mensagem "ticket 13". Registrado aqui pra não confundir.
- **Memória** (tickets 18/20/21 abertos): telemetria corrigida (macOS
  phys_footprint, Linux PSS — colunas NÃO comparáveis entre OS; SPS sim).
  acc64 Mac ~17GB footprint/16GB RAM; B bench ~29GB; acc64 AM18 swapa no cap de
  24GB (demanda ~27–28GB). Ticket 21: auditar os ~105 KB/amostra (obs ~21,6 KB).
- **Crons**: nenhuma pendente (as duas one-shots de hoje dispararam e se
  auto-deletaram). Find de background morto ao encerrar.

## Estado do mapa

- Resolvidos: 01–06, 10–16. **17 em execução** (fase 2 na fila).
- Fronteira: 07 (medido, falta resolver), 09, 18, 19 (ready-for-agent), 20, 21.
- Bloqueado: 08 (por 07).
- map.md não lista 19–21 em Decisions (estão abertos; scan de issues/ basta).
- v3 intocável (mapa autoresearcher-gym). Um ticket por sessão.

## Suggested skills

- **wayfinder** (modo work-through-the-map; este handoff é o argumento).
- **grilling** + **domain-modeling** — ticket 09 é HITL de conversa.
