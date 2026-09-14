# 0001 — v2: uma linhagem = um diretório = uma curva de TensorBoard

Status: accepted (2026-09-14). Escopo: **v2 apenas** — não restringe o design do
runner/jobs da v3 (que tem modelo host-side próprio, ver CONTEXT.md).

Continuar uma run na v2 dependia de gimmicks que já haviam mordido: o resume do
SB3 zerava o relógio do TensorBoard (a série contínua só existia via
`tb_stitch.py`, 280 linhas de cirurgia de TFRecord), a seleção de checkpoint por
mtime pegava zips de overshoot, o resume do acumulador exigia fixups manuais de
geometria, jobs referenciavam checkpoints por path local de uma máquina, e nada
registrava "run X saiu do checkpoint Y da run Z". Com duas máquinas (Mac, AM18)
e runs multi-perna (2M → 11M → 19M → 27M → 35M), comparar geometrias ou reward
functions no TB virava malabarismo de offsets e pastas.

**Decisão:** uma **linhagem** tem um único diretório de sessão e uma única curva
de TB, estendida perna a perna com relógio global (`reset_num_timesteps=False`,
base vinda de sidecar — nunca do `num_timesteps` interno do zip, que pode ser
leg-local). Todo checkpoint ganha um sidecar JSON auto-descritivo (step global
da linhagem, geometria lógica, seed, env_config, parent). `--extend <linhagem>`
resolve o checkpoint (dir local → share via `POKERED_DATA`), restaura o relógio,
aplica os fixups do acumulador a partir do sidecar e **falha duro** quando nada
resolve — o silent-fresh-start é aposentado. Reward, env_config e geometria
lógica (streams × n_steps) são fixos dentro da linhagem; mudá-los cria um
**branch** com pai registrado. Physical envs é propriedade da máquina
(flag > `V2_PHYSICAL_ENVS` > default-por-host). Proveniência fica no lineage
ledger (`v2/lineage.jsonl`, append-only, escrito pelo runner).

**Considered options:** (a) perna-por-diretório com eixo-x global e concatenação
na extração — rejeitado: N entradas de TB por linhagem é exatamente o
malabarismo que se queria eliminar; (b) dirs separados + merge automatizado de
event files — rejeitado: mantém um passo extra para sempre e duplica dados;
(c) flags `--base-steps`/offsets manuais — rejeitado: já mordeu; o sidecar é a
única fonte de verdade.

**Consequences:** tfevents passam a viajar com a linhagem no share (convenção de
publish atualizada no HANDOFF-mac-share.md). Runs históricas: a curva completa
de s0 (stitchada) vive nos dirs `t16_*_s0`, que viram os dirs de linhagem de
fato; os dirs leg1 (`t05_*`, `t15_*`) permanecem como arquivos de checkpoints
anteriores a 2M. O maior zip das legs t16 é 8.978.432 leg-local
(= 10.944.512 global) — extensões resumem dali, não do alvo teórico 10.977.280
(não há save final na fronteira). `tb_stitch.py` fica arquivado em `.scratch`
como ferramenta histórica; `--resume` e `--base-steps` seguem funcionando com
deprecation warning até ninguém mais os usar.
