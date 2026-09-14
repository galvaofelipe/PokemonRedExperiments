# 19 — Sistema de checkpoints/resume (aposentar os gimmicks)

Type: task
Status: ready-for-agent
Blocked by: —

## Desenho congelado (2026-09-14, grill com operador)

Decisões travadas em sessão de grill; os termos **Lineage / Leg / Branch /
Lineage ledger** já estão no CONTEXT.md. ADR sai só no final (sem ajustes
pendentes), escopo restrito à v2. **Esta seção é a spec de implementação** — o
restante do ticket é contexto histórico.

1. **Linhagem = um dir de sessão = uma curva TB.** Todas as pernas escrevem no
   dir de nascimento da linhagem (o modo `--target-steps` já garante numeração
   contínua de checkpoints e TB no dir novo — `v2/baseline_fast_v2.py:353-374`).
   Fixos na linhagem: reward, env_config, geometria lógica (streams × n_steps).
   Physical envs é da máquina — resolução: `--physical-envs` explícito >
   `V2_PHYSICAL_ENVS` > default-por-host (mapa no código: AM18→16, mac-mini→8).
   Mudança além de step-budget/máquina = branch (fora de escopo aqui; basta o
   sidecar/ledger terem campo `parent` pra quando acontecer).
2. **Sidecar por checkpoint**: `poke_<N>_steps.json` ao lado de cada zip —
   lineage, global_step (absoluto da linhagem), geometria lógica (num_envs
   lógico, n_steps, accumulation_rounds), seed, env_config, parent
   (lineage+step ou null), hostname, saved_at. Escrito no save; publicado junto
   ao zip.
3. **Extend**: `--extend <linhagem> [--from-step N] --target-steps <abs>` no
   `baseline_fast_v2.py`:
   - resolve o checkpoint no dir local da linhagem; se ausente/incompleto,
     busca em `$POKERED_DATA/pokered/runs/v2/<linhagem>/` e copia zip+sidecar+
     tfevents pro dir local (convenção de consume do HANDOFF-mac-share.md);
   - seleção: maior sidecar ≤ from-step (default: o mais recente);
   - **hard-fail** se nada resolver — aposenta o silent-fresh-start de
     `baseline_fast_v2.py:338-339`;
   - relógio global vem do sidecar (`--base-steps` vira deprecated warning);
   - geometria lógica/seed/env_config vêm do sidecar; flag explícita
     contraditória = erro claro (silêncio já mordeu);
   - TB apontado pro dir da linhagem; fixups do acumulador (hoje manuais em
     `:327-336`) aplicados automaticamente a partir do sidecar.
4. **Lineage ledger**: `v2/lineage.jsonl` (git, append-only), uma linha JSON por
   run: run/job name, lineage, parent (lineage+step ou null), target_steps,
   seed, hostname, start/end, status. Escrito pelo runner — inclusive em run do
   zero (parent null).
5. **Fila inalterada**: specs `{name, args[]}` declarativos. Campanha t16 s0
   19M→27M→35M = 9 specs numerados 030–038, gerados como parte da entrega mas
   NÃO enfileirados.
6. **Publish sob demanda**: `v2/publish_run.sh <linhagem>` copia zips+sidecars+
   tfevents (+ resource_summary/log, run.json) pro share; vídeos/states fora.
   Nada de rede no caminho do treino.
7. **Migração one-time = FORA DE ESCOPO desta implementação** (passo separado,
   só após ok do operador): consolidação dos dirs t05/t15+t16, backfill de
   sidecars legacy, remoção do `--base-steps`, arquivamento do tb_stitch.
8. **Aposentados nesta entrega**: silent-fresh-start; `--resume` por mtime e
   `--base-steps` marcados deprecated (warning); offset manual no tb_extract
   (documentar como desnecessário daqui pra frente).

### Notas de implementação (fatos verificados no código)

- Resume path `v2/baseline_fast_v2.py:280-374`; seleção de checkpoint
  `:147-164`; escolha PPO vs AccumulatingPPO `:325`; backup_run `:176-214`
  (run.json: cli_args/seed/start/end/num_timesteps/hostname/completed).
- `run_queue.sh`: glob `jobs/*.json`, ordem LC_ALL=C, cwd=`v2/`,
  stdin=/dev/null, exit≠0 → `jobs/failed/` e segue a fila.
- SB3 2.3.2: sem truncamento de budget (overshoot de até 1 mega-update);
  CheckpointCallback nomeia por `model.num_timesteps`; `tensorboard_log` é
  persistido no zip (por isso `:371` reatribui no modo target-steps).
- Mesmo session-path em pernas sequenciais é seguro no modo relógio-global;
  resource_log.csv appenda, resource_summary.txt é sobrescrito (aceitável),
  histogram x-axis reinicia por processo (aceitável neste escopo).
- Nada em `v2/` conhece o share hoje; `POKERED_DATA` vem de
  `scripts/ensure_tower.sh`.

### Critério de aceite (supersede o da seção Question)

1. Prova em run descartável: leg1 curta + leg2 via `--extend` → TB contínuo
   0→total no dir da linhagem, sem stitch/offset; sidecars corretos; ledger com
   2 linhas; checkpoints na numeração global.
2. Extend com checkpoint presente só no share → copia zip+sidecar+tfevents e
   roda.
3. Extend sem checkpoint resolvível → hard-fail imediato, exit≠0.
4. Flag contraditória com o sidecar (ex.: `--n-steps` diverso) → erro claro.
5. Testes automatizados do que der (resolução/seleção/parse) seguindo
   `v2/tests/`; os testes NÃO tocam os dirs das runs de 11M.
6. 9 specs da campanha (030–038) gerados em `v2/jobs/` e validados pelo parser
   real de `baseline_fast_v2.py`.

## Question (contexto histórico)

Continuar uma run hoje depende de gambiarras que já morderam e vão morder de novo
(quanto mais máquinas e runs paralelas, pior):

- **TB quebrado no resume**: SB3 `learn()` com default `reset_num_timesteps=True`
  loga a perna continuada do step 0. A extração exige offset manual (+1.966.080,
  registrado no handoff pós-16) e a série contínua só existe via
  `.scratch/explore-v2-training/scripts/tb_stitch.py` — 280 linhas de cirurgia de
  TFRecord com re-encode de scalars.
- **Seleção frágil de checkpoint**: `--resume` pega o zip mais novo — errado quando o
  dir tem overshoot (`runs_t05_g20480_s0` tem `poke_2097152_steps` além do
  `poke_1966080_steps` correto). Os jobs 022–024 contornam hardcodando o path exato.
- **Fixups manuais no load**: resume do acumulador exige reatribuir `n_steps`,
  `n_envs`, buffer size e `accumulation_rounds` na mão (`baseline_fast_v2.py:303-314`).
  Esquecer um vira bug silencioso de geometria.
- **Sem linhagem registrada**: nada persiste "run X saiu do checkpoint Y da run Z" —
  a célula 11M (ticket 17) depende disso por convenção verbal em handoff.
- **Referência não-portável**: jobs apontam paths locais de uma máquina
  (`runs_t05_*/...` só existe no Mac) e falham instantâneo na outra.

Desenhar e implementar o mínimo que aposenta os gimmicks:

1. **Checkpoint auto-descritivo**: sidecar `.json` junto ao zip com geometria
   (n_steps, logical/physical, accumulation_rounds), seed, env_config e **step global
   absoluto** da linhagem.
2. **Resume que restaura o relógio**: `reset_num_timesteps=False` ou offset explícito
   lido do sidecar → TB e nomes de checkpoint continuam a numeração global;
   `tb_stitch.py` aposentado.
3. **Ledger de linhagem**: arquivo pequeno em git (convenção dos job specs) mapeando
   run → checkpoint de origem → runs filhas.
4. **Referências portáveis**: jobs referenciam checkpoints por nome lógico resolvido
   via `POKERED_DATA` (layout em `HANDOFF-mac-share.md`), nunca por path de máquina.

Critério de aceite: rodar a fila 022–024 (ou equivalente) no AM18 com checkpoints
vindos do share — sem tb_stitch, sem offset manual na extração, sem fixup de
acumulador no código chamador, e TB contínuo 0→11M na extração.

**Workflow primário: "continuar run por mais N steps".** O caso de uso que este
ticket destrava é estender uma run viva: novo job referencia o checkpoint por nome
lógico + novo `total_timesteps` absoluto da linhagem, e o runner deriva todo o
resto (geometria, seed, env_config, relógio) do sidecar. Estender = 1 job spec
curto, zero edição de código, zero mending de TB.

## Comments

**2026-09-13 — evidência do mending da célula 11M (ticket 17, prévia 18:20).**
O remendo que o `tb_stitch.py` precisou fazer hoje mostra as duas falhas
concretas que este ticket aposenta:

1. **Overshoot da perna anterior**: SB3 só para na fronteira de update, então a
   leg1 logou steps além do checkpoint de resume (`runs_t05_g20480_s0`: eventos
   TB até ~2,13M com resume feito do zip `poke_1966080_steps`). O resume re-executa
   esse delta → sem clip no offset, a série fica com steps duplicados leg1/leg2.
   → Seleção de checkpoint deve ser "maior zip ≤ ponto de resume pretendido" e o
   relógio restaurado torna o delta re-executado invisível (steps globais únicos).
2. **Relógio zerado na perna continuada**: `reset_num_timesteps=True` (default)
   logou a leg2 do step 0 → shift manual de +1.966.080 na extração.
   → Item 2 acima aposenta.

Com o relógio restaurado + sidecar de step absoluto, overshoot deixa de ser
problema: o delta re-executado simplesmente sobrescreve/continua a numeração
global e o TB sai contínuo sem cirurgia.

**2026-09-14 — implementação entregue (agente, AM18; commit pendente de review
do operador).** Itens 2, 3, 4, 5, 6 e 8 implementados; item 7 (migração)
fora de escopo, como combinado.

- `v2/lineage.py` (novo): sidecars (`write_sidecar`/`read_sidecars`), seleção
  (maior sidecar ≤ from-step), resolução de extend com fallback pro share
  (`resolve_extend` — copia zip+sidecar+tfevents pra baixo; hard-fail com
  mensagem clara se nada resolve), checagem de contradição flag×sidecar,
  `resolve_physical_cap` (flag > `V2_PHYSICAL_ENVS` > mapa de host
  AM18/win-p2kh1a2oie9→16, mac-mini→8 > min(lógico, cpu_count), nunca > lógico),
  `append_ledger` (O_APPEND, escrita única por linha).
- `v2/baseline_fast_v2.py`: `--extend <linhagem> [--from-step N]` (exige
  `--target-steps`; recusa `--checkpoint/--resume/--base-steps/--total-timesteps/
  --minutes`); `LineageCheckpointCallback` escreve `poke_<N>_steps.json` em todo
  save (run fresca ou extendida); relógio vem do `global_step` do sidecar (não
  do num_timesteps interno do zip); fixups do acumulador automáticos a partir da
  geometria do sidecar; `--resume`/`--base-steps` emitem warning de depreciação
  no stderr; silent-fresh-start aposentado (checkpoint explícito ausente =
  exit 1); ledger append no `finally` (status completed/failed).
  **Mapeamento de dir**: linhagem `<nome>` (nome no share e no `--backup`) =
  dir de sessão local `v2/runs_<nome>/`; `normalize_lineage` aceita as duas
  formas.
- `v2/publish_run.sh <linhagem>` (novo): copia zips+sidecars+tfevents
  (+resource_summary/log, run.json — este último buscado em
  `baselines/<linhagem>/` quando ausente no dir de sessão) pro share; recusa
  sem `POKERED_DATA`; nunca deleta; vídeos/states fora.
- `v2/jobs/030..038_*.json`: campanha t16 s0 19M/27M/35M, declarativos
  (`--extend <linhagem> --target-steps <abs> --no-stream --save-final-state
  --backup <linhagem>`), ordem LC_ALL=C = ordem de execução, alvos
  19.005.440 / 27.033.600 / 35.061.760 (múltiplos de 163.840 e 20.480).
  NÃO enfileirados. Sem `--physical-envs`: resolve por host (16 no AM18).
- `v2/jobs/sidecars_t16_s0/<linhagem>/poke_10977280_steps.json`: backfill
  mínimo dos 3 checkpoints t16 s0 11M (parent t05/t15 @ 1.966.080, seed 0,
  geometria por braço; `saved_at` aproximado 2026-09-13, marcado
  `backfilled`). **Staged — operador copia pro share após revisar.**
- Decisões além da letra da spec: (1) `accumulation_rounds` do sidecar é
  informativo/validação — a perna nova RECOMPUTA rounds = lógico ÷ físico da
  máquina (rounds 8 no Mac → 4 no AM18, mega-update 163.840 preservado);
  (2) `parent` do sidecar = ponto de branch da linhagem (herdado entre
  pernas), enquanto `parent` do ledger = checkpoint efetivamente retomado
  (mesma linhagem @ step, para pernas); (3) ledger aceita override
  `V2_LINEAGE_LEDGER` (testes/scratch); (4) `v2/lineage.jsonl` não casava
  nenhum pattern do .gitignore, mas ganhou negação explícita `!v2/lineage.jsonl`.

Evidência de teste (AM18, `.venv` py3.12):
- `pytest v2/tests/` → 17 passed (13 novos em `test_lineage.py`: round-trip,
  seleção/from-step/overshoot, fallback de share com `POKERED_DATA` fake,
  hard-fail, contradição, physical cap, ledger, parse dos 9 specs pelo
  argparse real).
- E2E real com linhagem descartável `scratch_lg19` (2 envs × n_steps 128):
  leg1 fresca 0→2.048 → sidecars + ledger linha 1 (parent null); zips locais
  apagados, checkpoint só no share fake → leg2 `--extend --target-steps 4096`
  copiou zip+sidecar+tfevents e treinou → checkpoints continuam
  (`poke_3072_steps`, `poke_4096_steps`), TB contínuo (`train/approx_kl`
  512→4.096, 0 steps duplicados, sem stitch/offset), ledger 2 linhas
  (leg2 parent {scratch_lg19, 2048}); `--from-step 3072` escolheu o zip 3.072
  (não o mais novo); extend sem nada resolvível → exit 1 imediato;
  `--n-steps 256` contra sidecar 128 → exit 1 com mensagem clara; `--base-steps`
  → warning de depreciação. Artefatos grandes do scratch limpos (sidecars,
  tfevents e summaries mantidos em `v2/runs_scratch_lg19/`).

