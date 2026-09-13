# 01 — Claims originais do autor: o que foi reportado e o que é verificável

Type: research
Status: resolved

## Question

O que exatamente o autor (pwhiddy) reportou como resultado da run original, e o que
desses dados é verificável localmente? Extrair:

1. **Claims públicas**: README, writeup/vídeo, qualquer paper — o que é afirmado sobre
   a run de ~440M steps (Brock, Mt. Moon, SS Anne?), curvas de progresso ao longo do
   treino, e a config usada (já confirmado no código: `ep_length = 2048×80` ≈ 18,3h,
   64 envs, n_steps 2.560, batch 512, epochs 1, gamma 0.997, ent_coef 0.01, lr 3e-4,
   `init.state`).
2. **Dados locais da run do autor**: o diretório
   `~/dev/pwhiddy_pre_readonly/baselines/session_4da05e87_main_good/` (e o equivalente
   neste repo em `baselines/session_4da05e87_main_good/`) — que checkpoints, agent_stats
   ou tensorboard logs existem? Dá pra extrair trajetória de progresso (coordenadas,
   eventos, levels, mapas) vs steps pra usar como curva de referência?
3. **Critério de sucesso implícito**: o que o autor apresenta como "sucesso" (derrotar
   Brock? chegar em Mt. Moon? quantos steps até cada)?

Fontes: clone limpo `~/dev/pwhiddy_pre_readonly/` (evita escavar o histórico deste
repo), web (README, vídeo, writeups). Responder com evidência (arquivo:linha ou URL).

## Answer

Investigado em 2026-09-12 usando o clone limpo `~/dev/pwhiddy_pre_readonly/`, os
arquivos locais deste repo e fontes web (README, vídeo, TechCrunch, arXiv 2502.19920).

### 1. Claims públicas do autor

**Run original (~440M steps, fev/2022).**

- A única "writeup" da run original é o vídeo do YouTube
  ["Training AI to Play Pokemon with Reinforcement Learning"](https://youtu.be/DcYLT37ImBY)
  (out/2023, 33 min). Índice de seções (obtido da descrição): `Gym Battle` (10:45),
  `Route 3` (12:43), `Mt Moon` (14:44), `Map Visualizations` (15:54),
  `RNG manipulation` (18:53). O README aponta para o vídeo mas não afirma marcos
  quantitativos (`~/dev/pwhiddy_pre_readonly/README.md:9-18`).
- Citação direta do autor à TechCrunch (2023-10-18):
  > "In the video, the farthest that [the AI] reaches is Mt. Moon, between the first
  > and second gym"
  > "the AI has played more than 50,000 hours of the game"
  
  Fonte: [TechCrunch](https://techcrunch.com/2023/10/18/after-50000-hours-this-ai-can-play-pokemon-red/).
  A mesma matéria relata que, após o vídeo, Whidden ajustou rewards/trocou algoritmo e
  o AI "managed to exit the cave and arrive in Cerulean City" — base da claim da V2.
- **Não existe claim de SS Anne em lugar nenhum** para a run original (SS Anne fica em
  Vermilion, muito além do que foi reportado). Atingir Cerulean é claim da versão
  posterior (V2), não da run de 440M steps.
- Números de horas variam entre fontes secundárias: TechCrunch "50,000 hours";
  [TechEBlog](https://www.techeblog.com/peter-whidden-training-ai-play-pokemon-red/)
  "40,000+ hours". O número do checkpoint (439.746.560) × `action_freq` 24 frames/step
  ÷ 60 fps ≈ **48.900 horas**, consistente com "~50.000 horas".
- **Paper** [arXiv:2502.19920v2](https://arxiv.org/abs/2502.19920) (Pleines et al. 2025,
  com Peter Whidden) descreve experimentos NOVOS (2025, env PufferLib), não a run
  original: baseline chega a Cerulean City (~20% do jogo); "The first milestone is
  reaching Mt. Moon after defeating Brock"; humanos ~11.000 steps até Cerulean vs
  agente ~2×; derrotar Brock leva >3.000 steps por episódio. Cita o vídeo de 2023 com
  ">7.5M views" como inspiração (ref. [4]).
- **Curvas de progresso publicadas**: só as renderizações do mapa/vídeo e o GIF do
  README (`assets/poke_map.gif`). Nenhuma curva quantitativa (levels/eventos vs steps)
  foi publicada pelo autor em formato de dados.

**Config da run original — difere da config citada no ticket.** O script no commit do
próprio checkpoint (`git show 5330c5d:baselines/run_baseline_parallel.py`, fev/2022):
`ep_length = 2048*8 = 16384`, `action_freq: 24`, `init_state: '../has_pokedex_nballs.state'`,
`num_cpu = 44`, PPO `n_steps=ep_length`, `batch_size=512`, `n_epochs=1`, `gamma=0.999`.
A config do ticket (`2048×80`, 64 envs, `n_steps 2560`, `gamma 0.997`, `init.state`)
não bate nem com esse script original, nem com o `run_baseline_parallel_fast.py` atual
(2048×10, 16 envs, `batch 128`, `epochs 3`, `gamma 0.998`) — vale confirmar de qual
script ela veio (possivelmente `v2/`). A aritmética abaixo confirma que a run original
foi 44 envs × 16384 steps/episódio.

### 2. Dados locais da run do autor

**`session_4da05e87_main_good/` (idem nos dois clones — mesmo sha256
`198ed77d…69d78`):** contém APENAS `poke_439746560_steps.zip` (6,4 MB). Conteúdo:
`data` (pickle de metadados SB3), `pytorch_variables.pth` (431 B), `policy.pth`
(1,9 MB, pesos da CNN), `policy.optimizer.pth` (3,8 MB), `_stable_baselines3_version`
= `1.4.0`, `system_info.txt` (Linux, Python 3.7.11, SB3 1.4.0, PyTorch 1.10.0,
Gym 0.19.0, GPU). **Não há agent_stats, eventos de tensorboard nem trajetórias.**
Tentativa de `PPO.load` com o venv atual (SB3 2.3.2/gymnasium) falha no pickle do
`gym` 0.19 — o checkpoint exige o stack antigo do `system_info.txt`.

**Checkpoints intermediários que existiram no git e foram apagados** (deletados em
`e1f5e48` 2023-10-22, não restaurados — recuperáveis dos objetos git):
`session_bfdca25a/poke_23789568_gym_well1.zip`, `…/poke_24510464_gym_well2.zip`,
`session_b30478f4/poke_49741824_past_gym1.zip`,
`session_e1b6d2dc_post_train_more_steps/poke_25952256_steps.zip`. Os nomes são
evidência de progresso: "gym_well" ~24M steps, "past_gym1" ~49,7M steps.
O zip de 439M foi commitado em `5330c5d` (2023-02-23 → na verdade 2022-02-23:
"add a couple good checkpoints right in the ol repo"; data interna do zip 2022-02-05),
deletado em `e1f5e48` e restaurado em `1d9de8f` (2023-10-23).

**`baselines/saves_to_record.txt`** (63 linhas): lista checkpoints de
`session_4da05e87` de `init` até 296.288.256 steps, cadência 720.896 steps
(= 16384 × 44 envs), depois 7.208.960. Nunca atualizado após 296M (commit 2022-04-20).

**`baselines/Visualizations_over_time.ipynb`** (idem nos dois clones) — a análise que o
próprio autor rodou sobre os agent_stats da run. Evidências embutidas nos outputs:
- `run_dir = Path('session_4da05e87')`, comentário: "original session_e41c9eff, main
  session_4da05e87, extra session_e1b6d2dc".
- 44 CSVs gz (um por env, `num_cpu=44`), cada um com 610 rollouts × 16385 linhas
  (16384 steps + cabeçalho); colunas: `step, x, y, map, pcount, levels, ptypes, hp,
  frames, deaths, badge, event, healr`. Shape impresso: `(610, 44, 16385, 7)`.
- **610 × 16384 × 44 = 439.746.560** — exatamente o step count do checkpoint final:
  o notebook cobre a run original INTEIRA.
- Outputs numéricos/gráficos preservados: total de Pokémon capturados (excl. Squirtle)
  = **66.816**; stackplot da composição do party ao longo das 610 iterações (early:
  só Squirtle/Rattata/Pidgey; após ~iter 300: Wartortle, Magikarp, Geodude, Zubat,
  Paras…); plot das médias por stats no último step de cada rollout: `total_levels`
  sobe de ~20 para ~35-40, `event` ~8-10, `deaths` ~4, `healr` ~9, **`badge` ≈ 0 em
  toda a curva** (média sobre 44 envs no último step — não dá para distinguir "nunca
  pegou o badge" de "eventual/tarde"; o peso do badge no reward era só ×2, ver §3).
- Output de `du` da máquina do autor: `session_4da05e87_main_good` 3,8G,
  `session_e41c9eff_start_maybe` 2,2G, `session_b30478f4_mt_moon` 1,2G,
  `mini_agent_stats` 288M — ou seja, os dados brutos existiram na máquina dele mas
  **nunca entraram no repo**.

**Tensorboard:** `tensorboard_callback.py` existe e o README diz que os logs ficam no
diretório da sessão, mas **nenhum event file foi commitado** — zero em ambos os clones.

**Resposta direta: NÃO é possível extrair trajetória (coordenadas/eventos/levels vs
steps) da run do autor a partir dos dados locais.** O que existe localmente: (a) o
checkpoint final (pesos + normalização), carregável apenas com o stack antigo
(gym 0.19/SB3 1.4/torch 1.10) — para inferência/rollout, não contém histórico; (b) as
curvas estáticas embutidas no notebook; (c) a cadência de checkpoints e os nomes dos
checkpoints com marcos. Uma curva de referência exigiria rodar o policy e coletar
stats novamente.

### 3. Critério de sucesso implícito

- **Na narrativa pública**: sucesso = derrotar o 1º ginásio (Brock) e chegar a Mt. Moon
  (citação da TechCrunch acima), depois de ~50.000 horas / ~440M steps; a versão com
  rewards ajustados "chega a Cerulean" (README:60-64, seção V2). Nenhum número de
  steps por marco foi publicado para a run original — exceto os nomes dos checkpoints
  (gym_well ~24M, past_gym1 ~49,7M, final 439,7M em Mt. Moon).
- **No código da época** (`git show 5330c5d:baselines/red_gym_env.py:449-457`):
  reward = `level×100`, `hp_frac×2000`, `explore(KNN)×160`, `event` (max event reward),
  `badge×2`, `heal`, `dead −0.1`, `op_lvl`. Stats logados por step: `pcount, levels,
  ptypes, hp, frames, deaths, badge, event, healr` — o progresso é medido sobretudo por
  levels + exploração + event flags; o badge de Brock é sinal fraco (×2 vs ×100-×2000).
- **Vocabulário de eventos local** (`baselines/events.json`, 2558 flags mapeadas):
  "Beat Brock" = flag `0xD755-7`; também mapeados "Beat Pewter Gym Trainer 0",
  "Beat Cerulean Rival", "Beat Cerulean Rocket Thief" etc. — a nomenclatura de marcos
  usada pelo `event` reward.
- **No paper de 2025** o critério fica explícito: milestones = Viridian Forest →
  derrotar Brock → Mt. Moon → Cerulean → Misty → Bill → Vermilion; baseline completa
  ~20% do jogo (até Cerulean).
