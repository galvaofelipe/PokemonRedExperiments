# 24 — t16_acc64_s0 @ ~19M: Viridian wall (post-Pokédex, no Route 2)

Type: research
Status: ready-for-agent
Blocked by: —

## Question

A campanha AM18 da linhagem `t16_acc64_s0` (Mac ~11M + extend 030 até ~19M, 64
lógicas × 2560, `--physical-envs 16`, dieta t23) ficou presa em Viridian. O
autor / PokeRL claim (ticket 11): Badge 1 ~9,6M (pokegym), SS Anne ~26M (v2 do
autor, ckpt `poke_26214400`). Estamos muito abaixo. O que exatamente a telemetria
e o RAM do jogo mostram neste wall — e o que isso **não** prova ainda?

Escopo deste ticket: evidência superficial (TB local + pret/pokered + um roll
do ckpt). Follow-up no Mac Mini com Discord PokeRL + comparação contra o ckpt /
tfevents do autor.

## Answer (superficial, 2026-09-14, AM18)

### Claims de referência (já no ticket 11 — não re-verificadas aqui)

| fonte | budget | marco |
|---|---|---|
| PokeGym / xinpw8 | ~9,6M | Badge 1 (Brock) |
| v2 do autor (`2f79c5a`, `poke_26214400`) | 26,2M | “do very start to ss anne” |
| N3 rubrica (ticket 03) | 25–35M | Brock |

Nossa `t16_acc64_s0` a ~19M: **0 badges**, `max_map_progress` travado em **3**
(Viridian; 4 = Route 2), mapa explorado = Pallet + Route 1 + Viridian (+ stub
Route 22). Sem Route 2 / Forest / Pewter.

### Telemetria TB (Mac `poke_ppo_1` 0→~11M + AM18 `poke_ppo_0` ~11M→~19M)

Janelas de 2M em `env_stats_max/*`:

| sinal | teto | desde |
|---|---|---|
| `max_map_progress` | **3** | ~6M |
| `unique_maps` | **13** | ~11M |
| `dex_seen` | **7** | ~8–10M |
| `event` (shaped) | **30** | ~9M |
| `badge` | **0** | sempre |

O extend 11M→19M não moveu o teto de progresso — só confirmou SPS/RAM (t23).

Mapa “full explored area” (viz): corte horizontal nítido na saída norte de
Viridian; sem pixels brancos em Route 2.

### `dex_seen` ≠ tem Pokédex (correção)

Em `~/dev/pokered/engine/battle/core.asm` (~6136), todo battle marca
`wPokedexSeen` **sem** `CheckEvent EVENT_GOT_POKEDEX`. `add_mon.asm` também
seta owned+seen ao adicionar mon ao party (starter). Então `dex_seen` 4–7 só
diz “viu/recebeu espécies”, não “Oak entregou a dex”.

Gate norte de Viridian (`scripts/ViridianCity.asm`
`ViridianCityCheckGotPokedexScript`): se `EVENT_GOT_POKEDEX` **clear**, ao
chegar em (x=19,y=9) o old man sonolento empurra o player para baixo. A girl
é só texto (`CheckEvent` troca dialogue) — não bloqueia movimento.

### O que `event=30` significa nesta config

`env_stats/event` = `progress_reward["event"]` =
`reward_scale × raw_event_bits × 4` (`red_gym_env_v2.py`). Com
`reward_scale=0.5` → **30 ⇒ exatamente 15 bits** acima do baseline (`init.state`
começa em 0).

Roll do ckpt mais novo (`runs_t16_acc64_s0/poke_19070976_steps`, 1 env, ~12k
steps de policy): pico shaped **30.0 / raw 15**, bits setados:

| key | name |
|---|---|
| `0xD747-0` | Followed Oak Into Lab |
| `0xD74A-0` | Got Town Map |
| `0xD74A-1` | Entered Blues House |
| `0xD74A-2` | Daisy Walking |
| `0xD74B-0` | Followed Oak Into Lab 2 |
| `0xD74B-1` | Oak Asked To Choose Mon |
| `0xD74B-2` | Got Starter |
| `0xD74B-3` | Battled Rival In Oaks Lab |
| **`0xD74B-5`** | **Got Pokedex** |
| `0xD74B-7` | Oak Appeared In Pallet |
| **`0xD74E-0`** | **Oak Got Parcel** |
| **`0xD74E-1`** | **Got Oaks Parcel** |
| `0xD7BF-0` | Got Potion Sample |
| `0xD7EB-0` | 1St Route22 Rival Battle |
| `0xD7EB-7` | Route22 Rival Wants Battle |

`Got Pokeballs From Oak` (`0xD74B-4`) **não** estava set neste snapshot.
`GotPokedex` + parcel **sim**. Logo o teto de 30 da frota é o pacote
parcel/dex (+ Route 22 rival trigger), **não** “preso no old man sem dex”.

### Conclusão local

Wall **pós-Pokédex**: a policy completa Oak parcel/dex e cutuca Route 22, mas
não entra em Route 2 (`mmp` nunca chega a 4). Isso é falha de exploração /
incentivo / config relativa ao yardstick do autor — **não** o soft-lock do
sleepy old man.

Hipóteses abertas (não testadas aqui; Discord + ckpt do autor no Mac):

1. Diferença de geometria / update (já suspeita no mapa: nosso b35m 8-env vs
   autor 64×2560) — mas **esta** run já é 64×2560 e ainda assim mmp=3.
2. Diff de reward / init / episode length vs a run `poke_26214400` do autor.
3. Seed / stochasticidade: um roll não prova a frota inteira, mas TB
   `env_stats_max` bate o mesmo teto 30 / mmp 3.
4. Bug ou regressão nossa (acumulador, dieta t23, `--extend` clock) — a curva
   Mac pré-extend já saturava mmp=3/~event 30, então o wall **precedece antes**
   da dieta/AM18.

### Artefatos

- Session local: `v2/runs_t16_acc64_s0/` (`poke_ppo_0` AM18, `poke_ppo_1` Mac)
- mem_watch 1ª hora 030: `v2/bench/mem_watch_030_first_hour.csv` +
  `mem_watch_030_verdict.txt` (RAM saudável; não é OOM)
- Share publish: `v2/publish_run.sh t16_acc64_s0` com `POKERED_DATA` montado

### Próximo passo (Mac Mini + Discord)

1. `git pull` deste ticket.
2. Consumir tfevents/ckpt publicados em
   `$POKERED_DATA/pokered/runs/v2/t16_acc64_s0/`.
3. Comparar scalars / mapa com a run do autor e vasculhar PokeRL Discord
   (geometria, reward, “stuck viridian”, “route 2”, “mmp”) — fora do alcance
   deste host.

## Comments

- 2026-09-14 (AM18 / Cursor): pesquisa superficial após job 030; operador
  pediu commit + publish pra continuar no Mac com Discord.
