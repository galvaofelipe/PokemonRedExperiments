# 04 — Viabilidade do acumulador de batches no SB3 (geometria 64×2.560 com 8 envs)

Type: research
Status: resolved

## Question

Como honrar a geometria de update do autor com 8 envs físicos? Investigar e comparar:

1. **Acumulador de batches**: 8 rounds de 8 envs × 2.560 steps, GAE por segmento, um
   update PPO por 64 segmentos = 163.840 amostras/update (geometria exata do autor).
   SB3 não faz out of the box — o que precisa ser hackeado (rollout buffer, GAE,
   `policy.update`)? Há precedente: a v3 já remenda o rollout buffer no resume
   (`v3/train.py:305-309`). Custo de implementação e riscos (bootstrap entre rounds,
   vantagens atravessando boundary de round).
2. **8 × 20.480**: manter 163.840 amostras/update subindo `n_steps` pra 20.480 com 8
   envs — mesmo tamanho de update, mas 8 streams em vez de 64. O que muda (diversidade
   do batch, correlação entre amostras)?
3. **8 × 2.560 (status quo)**: updates 8× menores e 8× mais frequentes por amostra —
   o que a literatura/código sugere sobre o efeito?
4. Nuance importante: o update do autor vê 64 **fragmentos de 2.560 steps** de streams
   independentes, não 64 episódios completos (episódios de 18h = 64 updates cada).
   A pergunta certa é sobre streams e amostras por update, não episódios.

Saída: recomendação técnica com estimativa de esforço pra cada opção, alimentando o
desenho dos experimentos (ticket 05) e a decisão de refactor (ticket 06). O objetivo
do mapa é eliminar a reza: se a diferença entre geometrias for incognoscível sem
experimento, dizer qual experimento distingue.

## Answer

**Resumo executivo.** SB3 instalado: **2.3.2** (`.venv/lib/python3.12/site-packages/stable_baselines3/`).
A opção 2 (`n_steps=20480`, 8×20.480) é uma mudança de configuração de **zero linhas de código**
e, pelos números deste repo (horizonte efetivo do GAE ≈ 19–39 steps vs. chunks de 2.560+),
é estatisticamente quase indistinguível da opção 1. A opção 1 (acumulador) é **viável e de
implementação localizada** (~1–2 dias) porque o GAE por segmento já é o que o SB3 faz nativamente
a cada `collect_rollouts`; o hack é juntar 8 buffers de round num único `train()`. Recomendação:
começar o desenho experimental pela opção 2 (custo zero), e construir o acumulador (opção 1)
como braço de fidelidade à receita do autor, não como pré-requisito.

---

### 0. Como o SB3 2.3.2 monta um update hoje (base de tudo)

Pipeline exato, com linhas:

1. `OnPolicyAlgorithm.learn` (`common/on_policy_algorithm.py:299-313`): loop =
   `collect_rollouts(...)` → `_update_current_progress_remaining` → `_dump_logs` → `train()`.
   **Um update por iteração = um buffer cheio.**
2. `collect_rollouts` (`on_policy_algorithm.py:139-245`): para `n_steps` ticks, cada tick
   stepa `n_envs` envs e chama `rollout_buffer.add` (`:224-231`); no fim chama
   `rollout_buffer.compute_returns_and_advantage(last_values, dones)` **uma vez**
   (`:235-239`). Bootstrap de truncamento de episódio é tratado por-transição em `:211-222`.
3. `RolloutBuffer.compute_returns_and_advantage` (`common/buffers.py:402-437`): recursão
   GAE para trás **por env** (`:425-434`), com bootstrap só no último step do buffer
   (`step == buffer_size - 1`, `:426-428`) usando `last_values = V(s_final)` da política
   corrente. Ou seja: o buffer `(2560, 64)` do autor é, matematicamente, **64 chunks
   independentes de 2.560 com bootstrap em cada fronteira** — a dimensão `n_envs` do buffer
   é só layout de storage; quem define a matemática é onde o bootstrap acontece.
4. `PPO.train` (`ppo/ppo.py:184-304`): `n_epochs` passes; em cada pass, permuta
   `buffer_size*n_envs` índices e fatia em minibatches de `batch_size`
   (`common/buffers.py:482-505`), normalizando vantagem **por minibatch** (`ppo.py:222-223`).
5. Config v3 relevante (`v3/train.py:144-148`): `gamma=0.997`, `gae_lambda=0.95` (default
   SB3, não sobrescrito — `ppo.py:89`), `batch_size=512`, `n_epochs=1`, lr default 3e-4
   constante. Default `--num-envs 64` (`v3/train.py:155`) com
   `train_steps_batch = max_steps // 64` e `max_steps` default `2048*80 = 163.840`
   (`v3/train.py:170, 300`) → n_steps=2.560, exatamente a geometria do autor.
6. Precedente de remendo no repo: `v3/train.py:302-309` muta `model.n_steps`,
   `model.rollout_buffer.buffer_size/n_envs` num resume e dá `reset()`. Confirma que o
   buffer é state barato e recriável, mas **não** é precedente de acumulação — ele só
   redimensiona o buffer de um update comum.

### 1. Opção 1 — acumulador (8 rounds de 8×2.560 → 1 update de 163.840)

**Viabilidade: sim, com subclass de `PPO` (~80–120 linhas novas).** Não é preciso tocar em
GAE, `policy.update`, clipping nem optimizer. O GAE por segmento **já é o comportamento
nativo** (item 3 acima): basta rodar o `collect_rollouts` stock 8 vezes (uma por round,
com a política congelada — ela só muda no `train()`), e cada round sai com GAE correto
e bootstrap próprio. O único trabalho real é fazer o `PPO.train()` (stock, inalterado)
consumir os 8 buffers de round de uma vez.

Dois desenhos concretos:

- **1a — "chained buffer" (recomendado):** override de `learn()` que (i) chama
  `self.collect_rollouts(self.env, callback, self.rollout_buffer, self.n_steps)` 8 vezes
  numa lista de 8 buffers de round (ou 1 buffer coletor + cópia pós-GAE), (ii) monta um
  objeto com a interface mínima que `PPO.train()` usa (`get(batch_size)` iterando os 8
  buffers concatenados; `values`/`returns` concatenados p/ `explained_variance` em
  `ppo.py:288`), (iii) aponta `self.rollout_buffer` pra ele e chama `self.train()` uma vez.
- **1b — mega-buffer:** um `DictRolloutBuffer(buffer_size=20480, n_envs=8)` com
  `compute_returns_and_advantage` anulado (GAE já veio calculado por round); copia-se cada
  slice `[r*2560:(r+1)*2560, :]` após o round r. Mais simples de raciocinar, mas o
  `get()` do SB3 faz `swap_and_flatten` (`buffers.py:494-496`, cópia de ~3,3 GB) com o
  buffer antigo ainda referenciado → pico de RAM ~2×. A variante 1a tem pico menor.

Pontos exatos a replicar no override de `learn()` (é aqui que moram os bugs):
`_setup_learn`, `callback.on_training_start/end`, `_update_current_progress_remaining`
**uma vez por mega-update** (mesma cadência do autor; lr é constante, então sem efeito
prático hoje, mas preserva semântica), `_dump_logs` por update, `_n_updates += 1` via
`train()` stock. Callbacks (`CheckpointCallback`, `WandbCallback`) disparam por round em vez
de por update, mas ambos chaveiam em `num_timesteps` (`on_policy_algorithm.py:197`), que
soma certo — sem efeito. Checkpoint/resume: `PPO.save` não serializa rollout buffer
(`on_policy_algorithm.py:319-321`), então o remendo de `v3/train.py:305-309` continua
válido; só recriar também o objeto chained/mega. Checagem de sanidade `n_steps*n_envs`
vs `batch_size` (`ppo.py:145-162`): com `n_steps=2560` na subclasse não dispara warning.

**Equivalência com o autor (evidência, não especulação):** o update do autor vê um dataset
de 163.840 amostras = 64 chunks i.i.d. de 2.560, todos gerados pela mesma política π,
com GAE bootstrapped por chunk, vantagem normalizada sobre as 163.840, e 320 minibatches
de 512 por epoch (n_epochs=1). O acumulador produz exatamente o mesmo objeto
estatístico — 8 rounds × 8 envs × 2.560, mesma π congelada, mesmo GAE por chunk, mesma
normalização, mesmos 320 minibatches. Diferenças de 2ª ordem (marcar como análise, não
fato medido): (i) chunks de rounds consecutivos do **mesmo** env continuam a cadeia de
Markov do env, então há correlação residual entre chunk(env i, round r) e
chunk(env i, round r+1) que o autor não tem entre envs distintos — com 2.560 steps entre
eles e γ=0.997 (γ^2560 ≈ 4,6e-4), o decaimento torna isso desprezível em teoria;
(ii) o autor tinha 64 streams de RNG de env, o acumulador reutiliza 8 — mesma ordem de
desprezibilidade, pois a estocasticidade vem da política.

**Memória:** obs/sample ≈ 20 KB (screens 72×80×3 = 17.280 B + mapa 48×48 = 2.304 B +
campos pequenos — `v3/frozen/env/red_gym_env.py:97,104-118`). Buffer de round (status quo)
≈ **0,4 GB**; os 163.840 do acumulador ≈ **3,3 GB** extras (variante 1a; 1b pica ~6,6 GB
transitório). Em 16 GB com 8 subprocessos PyBoy (estimativa não medida: ~1,5–3 GB no
total), é apertado mas viável; mitigação barata é a variante 1a ou `np.memmap` nas obs
(+complexidade, não recomendado de início).

**Esforço/risco:** implementação **M — 1–2 dias** incluindo teste unitário que recalcula
GAE à mão num buffer pequeno e compara com o do acumulador, mais um smoke run curto.
Risco **baixo-médio**: superfície de hack pequena e totalmente acima do SB3 (nenhum
monkey-patch interno), mas exige cuidado com os pontos de cadência listados. Risco
científico: baixo — é a reprodução fiel.

### 2. Opção 2 — 8 × 20.480 (mesmo total por update, zero código)

Mudar `n_steps` de 2.560 para 20.480 (`v3/train.py:300-317` usa `train_steps_batch` em
ambos os ramos; uma linha). 163.840/update, política congelada durante 20.480 ticks/env,
um `collect_rollouts` com bootstrap único em t=20.480 — em vez de 8 bootstraps por env
espalhados no tempo (opção 1) ou 64 bootstraps paralelos (autor).

O que muda de fato vs. opção 1, quantificado:
- **Horizonte do GAE:** γλ = 0,997 × 0,95 = 0,947 → horizonte efetivo da vantagem ≈
  1/(1−γλ) ≈ **19 steps**; a cauda do TD(λ) além de ~1.000 steps pesa < γ^1000 ≈ 5e-2
  e além de 2.560 pesa ≈ 4,6e-4. Como 2.560 e 20.480 são **ambos muito maiores** que o
  horizonte, bootstrap em 2.560 vs. 20.480 muda as vantagens em bem menos de 1% em escala
  — efeito teoricamente desprezível *neste* repo (seria diferente com γ=0.9999 ou
  gae_lambda→1).
- **Estrutura de correlação no batch:** 8 chunks de 20.480 em vez de 64 de 2.560. Um
  minibatch aleatório de 512 desenhado de 8 chunks puxa ~64 steps do mesmo chunk
  (correlacionados); de 64 chunks, ~8. Variância do gradiente por minibatch é maior na
  opção 2; sobre 320 minibatches o efeito parcialmente se dilui, mas o tamanho efetivo de
  amostra do update é menor. É **a única diferença estatística real** entre 1 e 2.
- **Literatura:** Andrychowicz et al. 2020 ("What Matters in On-Policy RL?", arXiv:2006.05990,
  Seção 3.5): aumentar `num_envs` com iteration size fixo (chunks *mais curtos* +
  bootstrap *mais cedo*) **derruba** performance em vários ambientes; aumentar o batch
  total **não prejudicou** sample efficiency; o "number of transitions per iteration"
  importa e deve ser tunado. Ou seja: a direção conhecida favorece chunks longos (opção 2)
  ≥ chunks curtos (opção 1) para sample efficiency — mas o estudo é controle contínuo com
  horizontes de segundos; transferência para γ=0.997/episódios de 18h é plausível, não
  garantida (marcar como extrapolação). O blog "37 Implementation Details of PPO"
  (ICLR Blog Track) relata o mesmo achado no formato N×M.
- **Memória:** buffer stock vira (20.480, 8) = 3,3 GB + pico `swap_and_flatten` ~2×
  (mesmo patamar da variante 1b do acumulador). Em 16 GB, monitorar; mitigar com o mesmo
  truque de armazenar achatado se necessário.
- **Nuance do ticket (streams vs. episódios):** atendida — em todas as opções o update vê
  fragmentos de streams, nunca episódios completos (episódio de 163.840 steps = 8 updates
  nas opções 1–2, 64 no status quo, com bootstrap de truncamento tratado por transição em
  `on_policy_algorithm.py:211-222` independentemente da geometria).

**Esforço/risco:** esforço **zero** (config); risco **baixo** (só RAM/pico e o possível —
teoricamente pequeno — efeito de correlação). É o braço mais barato a rodar e o candidato
natural a default se os experimentos não distinguirem.

### 3. Opção 3 — status quo 8 × 2.560 (20.480/update)

Zero mudanças. Diferença: **8× mais updates por amostra**, batch 8× menor, dados 8×
mais frescos por gradiente, 40 minibatches (não 320) por update. PPO lida bem com isso
(normalização de vantagem por minibatch segue válida — `ppo.py:140-143` só exige
batch_size>1). O que a literatura sugere: batch total maior não piorou sample efficiency
(Andrychowicz, Fig. 57) — o que não é a mesma coisa que dizer que update maior é melhor;
"frescor" dos dados e frequência de update não foram o eixo do estudo. É o braço
**controle obrigatório** de qualquer A/B: qualquer diferença entre 2/3 atribui-se à
geometria de update; e a comparação 2↔3 é trivial de configurar.

**Esforço/risco:** zero/zero.

### 4. Qual experimento distingue (pro ticket 05)

Teoria não decide entre 1 e 2 (efeito previsto < 1% em vantagem; variância do gradiente
não observável diretamente) e a literatura é de outro domínio. Experimento mínimo, em
wall-clock comparável (as três opções coletam a mesma taxa de env-steps; GPU/CPU do
forward batch-8 é igual nas três):

- **Braço A (2 vs. 3 — o decisivo e custo-zero):** mesma seed, mesmos 8 envs, recompensa
  e checkpoints; única diferença `n_steps ∈ {2.560, 20.480}`. Comparar **progresso de
  jogo por env-step** (event flags, seen_coords, levels, badges — as métricas que o
  TensorboardCallback já loga) em checkpoints alinhados por timesteps, mais
  `train/approx_kl`, `clip_fraction`, `entropy`, `explained_variance`. Se
  indistinguíveis → adotar 8×20.480 (opção 2 domina: zero código) e o acumulador vira
  desnecessário, salvo fidelidade arqueológica. Se 20.480 piorar → frequência de update
  importa, e aí o status quo (ou um meio-termo 8×5.120/8×10.240) ganha.
- **Braço B (1 vs. 2 — só se A mostrar que geometria importa, ou para fidelidade ao
  autor):** acumulador vs. `n_steps=20480`, mesmo total/update, mesma seed — isola
  comprimento de chunk (2.560 vs. 20.480) com tudo mais fixo. É o braço que reproduz a
  receita do autor com hardware de 8 envs.
- Duração: o sinal em Pokémon Red costuma ser lento; usar os mesmos marcos de checkpoint
  do v3 (`--save-freq`, max_steps/2) e comparar curvas em env-steps (não em updates).

**Tabela esforço/risco**

| Opção | Código | Esforço | Risco técnico | Risco científico |
|---|---|---|---|---|
| 1. Acumulador | ~80–120 linhas, subclass PPO, nada interno ao SB3 | M (1–2 dias + testes) | Baixo-médio (cadência de callbacks/anneal; RAM 3,3–6,6 GB) | Baixo — reprodução fiel do autor |
| 2. 8×20.480 | 1 linha de config | Zero | Baixo (pico RAM ~2× do buffer) | Baixo-médio (chunks longos → minibatches mais correlacionados) |
| 3. 8×2.560 status quo | nenhuma | Zero | Zero | Baixo — é a baseline |

**Recomendação:** ticket 05 roda primeiro o braço A (2 vs. 3). Enquanto ele roda,
implementa-se o acumulador (opção 1) em paralelo como braço B de fidelidade — ele também
destrava o ticket 06 (refactor) caso o autor precise ser replicido exatamente. Se A for
nulo, o ticket 06 pode simplesmente fixar `n_steps=20480` e arquivar o acumulador.

**Fontes:** código SB3 2.3.2 local (linhas citadas acima); Andrychowicz et al. 2020,
[What Matters In On-Policy RL?](https://arxiv.org/abs/2006.05990) (Seção 3.5, Figs. 52/55/57);
[The 37 Implementation Details of PPO, ICLR Blog Track](https://iclr-blog-track.github.io/2022/03/25/ppo-implementation-details/).
Itens marcados como análise/extrapolação: correlação entre chunks de rounds consecutivos,
estimativa de RAM dos subprocessos PyBoy, transferência do achado de chunk length de
controle contínuo para este domínio.


## Comments

- 2026-09-12 (via ticket 01): a geometria-alvo pode não ser 64×2.560 — a run de 440M
  usou 44 envs × 16.384 (episódios completos por update, 720.896 amostras). Ver
  ticket 10. A análise SB3 acima (horizonte GAE ≈ 19 steps, batch maior não prejudica)
  independe do alvo, mas as opções de acumulador mudam de forma se o alvo for
  44×16.384 (n_steps = episódio inteiro muda o papel do bootstrap).
