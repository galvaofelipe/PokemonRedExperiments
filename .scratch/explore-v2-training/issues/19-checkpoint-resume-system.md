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
