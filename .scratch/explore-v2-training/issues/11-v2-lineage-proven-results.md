# 11 — O que existe de resultado comprovado da linhagem v2/PufferLib, e a que custo?

Type: research
Status: resolved

## Question

O ticket 01 mostrou que a run de 440M é da linhagem 2022 (v1), não da v2. Antes de
travarmos a rubrica (ticket 03), precisamos saber se "o buraco é mais embaixo":
**quanto recurso a linhagem v2/PufferLib precisa pros mesmos marcos** — se derrotar
Brock na v2 custou 10× mais que 440M, a comparação que motivou este mapa estava
desigual desde o início.

Investigar e tabular evidência **budget → milestone** para:

1. **A run v2 do próprio autor** (a do commit `2f79c5a`, 2025-02-27: *"can go all the
   way from the very start to ss anne"*; README:60 clama Cerulean): existe budget
   publicado? checkpoint? vídeo/post/tweet posterior? Cavar o histórico do clone
   limpo `~/dev/pwhiddy_pre_readonly/` (commits, README, v2/), YouTube/X do autor.
2. **O paper arXiv:2502.19920** (Pleines et al. 2025, Whidden co-autor; env
   PufferLib): extrair os números exatos — steps até cada milestone (Brock, Mt. Moon,
   Cerulean…), comparação com humanos (~11.000 steps até Cerulean, agente ~2×),
   ">3.000 steps por episódio pra derrotar Brock", "~20% do jogo". Em que budget de
   treino total? Com quantos envs / que throughput?
3. **Comunidade PokeRL no Discord**: o operador viu que usam PufferLib. Há resultados
   públicos reproduzindo ou estendendo? Quanto recurso (steps/horas/hardware) pra
   Brock, Mt. Moon, Cerulean? Usar as tools MCP do Discord (listar servidores
   allowlisted, buscar no servidor PokeRL por "puffer", "brock", "cerulean",
   "steps", "whidden") — citar canal/mensagem.
4. Outras reproduções públicas conhecidas (GitHub forks com resultados, blog posts).

Saída: tabela **linhagem × config × budget → milestone alcançado × fonte**, e a
resposta direta: a comparação "440M → Brock/Mt. Moon" é da mesma família da v2 ou
não; qual número é o N3 honesto pra rubrica. Onde não houver dado, dizer
explicitamente "não encontrado" — não estimar sem fonte.

## Answer

**Resposta direta ao operador: não, a v2 não precisa de 10× mais recurso que os 440M
da v1 — precisa de ~17× MENOS.** O checkpoint publicado da run v2 do autor
(`v2/runs/poke_26214400.zip` no commit `2f79c5a`) corresponde a 26.214.400 steps
totais de treino (contagem agregada SB3, mesma métrica dos "440M" da v1) para ir do
`init.state` — do zero, Pallet Town, sem parcel pre-feito — até a S.S. Anne, passando
por Brock, Mt. Moon, Cerulean e Misty. A comparação histórica "440M → Brock/Mt. Moon"
é da família v1 (2022) e é internamente consistente como baseline, mas subestima
muito o que a v2 alcança com menos budget. Ressalvas e números completos abaixo.

### Nota de comparabilidade (verificada)

Todas as linhagens usam `action_freq = 24` (1 decisão de agente a cada 24 frames):
`baselines/red_gym_env.py` (v1), `v2/red_gym_env_v2.py`, `config.yaml` do pokegym, e
Seção II-D do paper ("one decision every 24 frames"). Os "steps" das várias fontes são
comparáveis 1:1 como decisões de agente. Também são todos contadores agregados
multi-env (SB3 `num_timesteps` / CleanRL `total_timesteps` / eixo do paper).

### Tabela linhagem × config × budget → milestone × fonte

| Linhagem | Config | Budget de treino | Milestone comprovado | Fonte |
|---|---|---|---|---|
| v1 (2022, repo Whidden) | 44 envs, PyBoy, KNN-frame explore, init `has_pokedex.state` | 440M steps totais (~10M/env) | Brock + Mt. Moon (não passou disso publicamente) | ticket 01 (não re-verificado) |
| v2 run anterior (out–dez/2024) | 64 envs, reward com level reward, init `has_pokedex_nballs.state` | checkpoint `poke_62914560_steps.zip` = 62.914.560 steps totais | "v2 goes to vermilion" | clone limpo, commits `7eb5d42` (2024-10-19) e `ea30772` (2024-12-24) |
| **v2 run do autor (fev/2025)** | 64 envs, `ep_length` 163.840, batch 64×2.560, event/heal/explore rewards, **sem level reward**, init `init.state` (do zero) | **`poke_26214400.zip` = 26.214.400 steps totais (409.600/env)** | "do very start to ss anne" (Pallet→parcel→forest→Brock→Mt. Moon→Cerulean→Misty→SS Anne); README:60 "Reaches Cerulean" | clone limpo, commit `2f79c5a` (2025-02-27); checkpoint em `v2/runs/`; pwhiddy no Discord PokeRL #general 2026-08-12 ("the original repo does have a 'v2' version which can reach ss anne") e #pokemon-gen1 2026-01-23 ("in my repo i have up to cerulean" + lista de map_ids até Cerulean Gym 65) |
| Paper arXiv:2502.19920 v2 (Pleines et al., 2025-03-11; Whidden co-autor) | env **novo** (não é o v2 do repo): 7 botões, 32 workers × 2.048 = batch 65.536, PPO γ=0.997, sem entropy, Nature CNN 2M params (GRU 4M), episódio com budget dinâmico 10.240+2.048/evento, **começa pós-parcel-quest com Squirtle fixo** | total_timesteps exato **não encontrado**; Fig. 3 vai até 400M steps; ~36h por run; GRU CPU-only 24 dias/run; env medido a 9.403 SPS no AMD Ryzen 7 2700X (~392 SPS efetivos) | **Brock 98–99% / Mt. Moon 97–98% / Cerulean 85–93%** (baseline Squirtle; ablação −level: Brock 95%, Cerulean 79%, única a completar Cerulean: 3%); steps de episódio: Brock 3.753–5.587 (humano 5.403); Cerulean 18.523–25.299 (humano 11.188) — agente ~2× humano confirmado; "defeating Brock takes over 3,000 steps on average" confirmado; Cerulean ≈ 20% do jogo confirmado | PDF extraído: Seções II, III, IV, Tables I–III, Fig. 3 (https://arxiv.org/abs/2502.19920) |
| PokeGym comunidade (PufferAI/pokegym; números do xinpw8, merge 2024-04-02, PufferLib ~0.5–0.7) | PufferLib EnvPool, LSTM default, text speed fast | **Badge 1 (Brock): 9,6M steps; Badge 2 (Misty): 35M; Bill saved: 53M; HM01: 60M; Badge 3 (Lt. Surge): 404M** | Badge 3 = 2 ginásios além de Cerulean, com cut aprendido (86% obtiveram HM01, 68% ensinaram Cut) | README do PufferAI/pokegym (branch `BET_pokegym_badge_3_400m`), https://github.com/PufferAI/pokegym |
| thatguy11325/drubinstein `pokemonred_puffer` (PufferLib) | 288 envs/24 workers, LSTM, init Bulbasaur, `one_epoch: EVENT_BEAT_CHAMPION_RIVAL`, automação total de HM ligada | alvo declarado 10B steps (config atual; 100B "for full games"); **budget do game clear: não encontrado** | release "Beat The Game" 2024-09-30 ("Game crashes once you won") — **zerou o jogo com scaffolding pesado** (auto_teach/auto_use cut/surf/strength/pokeflute, skip_safari_zone, infinite_money confirmados na tag) | https://github.com/drubinstein/pokemonred_puffer/releases/tag/beat-the-game; config.yaml@tag |
| leanke (PufferLib 2.0, 2025) | PufferLib 2.0, reward weights via config | **não encontrado** (sem wandb/steps públicos) | Fuchsia ("where I got stuck"); set/2026: sem scripting, o mais longe = **Celadon a 1B+ steps** (Bulbasaur forçado p/ cut); Brock ainda não consistente ("not frequent enough to rule out monkey on typewriter") | Discord PokeRL #help 2025-08-26 e #general 2026-09-07 |
| alchemy862037 (tooling próprio, **não** PufferLib) | teacher/student, metas byte-accurate, ~3k runs por cenário | total em steps: **não encontrado** | Brock derrotado 2026-08; Misty 2999/3000 | Discord PokeRL #pokemon-gen1, 2026-08-17/20 |
| betadsorption (PufferLib 3.x, 2026) | default puffer net + LSTM | "4M SPS training" (throughput, sem milestone) | — (run ao vivo) | Discord PokeRL #general 2026-03-17 |

Wall-clock da v2 do autor (run 26M): **não encontrado** — o script da v2 tem
`use_wandb_logging = False` e wandb foi desabilitado por default no histórico; não há
post/tweet/vídeo do Whidden detalhando budget além do commit e das mensagens no
Discord (talk de ago/2025, youtu.be/Hju0H3NHxVI, sem números de budget da v2).

### Leituras para a rubrica (ticket 03)

1. **A comparação não estava desigual.** "440M → Brock/Mt. Moon" (v1, 2022) e
   "26,2M → SS Anne" (v2, 2025) usam a mesma métrica (steps SB3 agregados,
   action_freq 24). A v2 é ~17× mais eficiente em steps que a v1, com trajetória
   estritamente maior (começa antes: do zero vs. estado com Pokédex).
2. **N3 honesto para "derrotar Brock" na linhagem v2/PufferLib, com fonte:**
   - Em steps de *treino*: ~9,6M steps até Badge 1 em praticamente todos os envs
     (PokeGym/xinpw8, abr/2024); 26M do zero até SS Anne (v2 do autor).
   - Em steps de *episódio*: 3.753±990 (Fast) a 5.587±1.235 (baseline) no paper,
     vs. 5.403±3.824 humano.
   - Como a nossa reprodução (v2, PyBoy, 64 envs) fica entre o PokeGym e a run do
     autor, um N3 na faixa **10M–26M steps de treino até Brock** é defensável com
     fonte — ordem de grandeza 20–40× abaixo dos 440M da v1.
3. **Cuidados:** (a) a run v2 do autor é um checkpoint sem curva de treino, seed ou
   avaliação estatística publicada — é claim de autor confirmado por ele no Discord;
   (b) o paper é um MDP diferente (começa pós-parcel, Squirtle fixo), então seus
   números de episódio não se transplantam direto pro nosso setup; (c) na linhagem
   PufferLib *sem* scripting, a comunidade reporta barreira bem mais dura: 404M para
   o badge 3 e **1B+ steps para Celadon** — ou seja, além de Cerulean a eficiência
   da v2 do autor não é reproduzida publicamente por ninguém, e o gargalo universal
   é Cut (thatguy11325, Discord #pokemon-gen1 2025-05-22: "you will not get past
   SS Anne" sem engenharia de reward/scripting).

### Lacunas explícitas ("não encontrado")

- total_timesteps exato das runs do paper (só o eixo de 400M da Fig. 3).
- wall-clock e hardware da run v2 do autor.
- budget (steps/horas) do "Beat The Game" do thatguy11325 (set/2024).
- budget em steps das runs Fuchsia (leanke) e das runs do betadsorption.
- dados do wandb do thatguy11325 (`wandb.ai/thatguy11325/pokemon` existe mas exige
  login; o run 2ffnd4xg do xinpw8 idem).
