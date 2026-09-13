# Naming, forget-move, map metadata, breadcrumbs, traps, Exp. All, toss, death

Status: research, 2026-09-13  
Audience: Frozen env snapshot + Editable `train.py`  
Ground truth: `~/dev/pokered/` (`naming_screen.asm`, `learn_move.asm`, `item_effects.asm`, `black_out.asm`, `pokecenter.asm`, `map_constants.asm`). Cross-check: `~/dev/pokemonred_puffer` hooks. Map table: `v3-map-metadata.json`.

Companion catalogs: `v3-obs-ram-catalog.md`, `pokered-wram-rl-catalog.md`.

These are **not all RAM questions**. Naming, forget-move, toss, nurse-heal vs blackout are **PyBoy hooks** (function entry) plus a little RAM. Map tags and breadcrumbs are **Frozen ROM/metadata**. Magikarp / Exp. All / museum ticket are ordinary event/item bits.

---

## 1. Typing screens (player name, rival name, nickname)

**Yes, but not via `wCurMap`.** The naming UI is a full-screen overlay. `wCurMap` stays Oak's Lab / the catch map / Name Rater's house.

### RAM (valid only while `DisplayNamingScreen` is on the call stack)

| Symbol | Addr | Meaning |
|---|---|---|
| `wNamingScreenType` | `0xD07D` | `NAME_PLAYER_SCREEN=0`, `NAME_RIVAL_SCREEN=1`, `NAME_MON_SCREEN=2` (`menu_constants.asm`) |
| `wNamingScreenNameLength` | `0xCEE9` | letters entered |
| `wNamingScreenSubmitName` | `0xCEEA` | nonzero = player hit END |
| `wAlphabetCase` | `0xCEEB` | 0 upper / 1 lower |
| `wStringBuffer` | `0xCF4B` | name being built; `@` (`$50`) terminator |

**Do not poll `0xD07D` as a sticky "we are naming" flag.** It unions with `wPartyMenuTypeOrMessageID` and `wTempTilesetNumTiles`. The `0xCEE9` block unions with evo/HP-bar temps. After the screen exits those bytes are garbage.

### How to expose it (MUST = hook)

Hook `DisplayNamingScreen` (puffer already has the symbol in `pokered.sym`; it does **not** currently hook it). While the hook is live:

- `in_naming_screen = 1`
- `naming_kind = wNamingScreenType` (0/1/2) read **inside** the hook, not later
- optional: `name_length`

Oak intro (`oak_speech2.asm`): the first list row is `"NEW NAME"`. `wCurrentMenuItem == 0` opens the alphabet. **A-mashers always enter the player/rival naming screens.** Defaults (RED/ASH/…) require pressing Down. Nickname prompt after a catch (`AskName`): Yes is also menu item 0, so every caught mon can trap an A-masher on the alphabet.

Name Rater (`DisplayNameRaterScreen`) is the same `NAME_MON_SCREEN` path, optional NPC.

**Reward implication:** do not Score typing. A small *escape* bonus for submitting any name (or picking a default) is reasonable so the policy is not stuck on A/B/left/right forever. Skip-nickname (No on `AskName`) is the faster Any% path.

---

## 2. Move being replaced

**No dedicated WRAM flag.** `LearnMove` (`engine/pokemon/learn_move.asm`) is a blocking yes/no + 4-row menu:

1. Empty slot → write `wMoveNum` into the party struct, done.
2. Four moves → `TryingToLearn` text → yes/no (`TWO_OPTION_MENU`).
3. Yes → `WhichMoveToForgetText` + 4-item list. B cancels. Selecting an HM prints `HMCantDeleteText` and loops (`IsMoveHM`).
4. Replacing writes the new move + PP over the chosen slot. If that mon is the active battler, it also copies into `wBattleMonMoves`.

Detect with a hook on `LearnMove` / `TryingToLearn` / `WhichMoveToForgetText`, and read:

| Symbol | Addr | Use |
|---|---|---|
| `wMoveNum` | (wram; filled before `LearnMove`) | incoming move id |
| `wWhichPokemon` | `0xCF92` | party slot |
| `wLearnMoveMonName` | `0xD036` | nick (volatile) |
| `wCurrentMenuItem` | `0xCC26` | which of the 4 to dump |
| party moves at `wPartyMonN+8` | | before/after delta |

`IsMoveHM` blocks deleting Cut/Fly/Surf/Strength/Flash. An agent can still **refuse** the new move (`AbandonLearning`). That is often correct (don't overwrite Surf with Tackle).

**Reward implication:** Frozen should emit `learn_move_pending`, `incoming_move_id`, `slot_moves[4]`, `is_hm[4]`. Editable reward can credit *keeping HMs* and *accepting coverage TMs*; do not blindly reward "pressed A on the list."

---

## 3. `wCurMap` metadata (ROM, not RAM)

`wCurMap` `0xD35E` is a 1-byte id. Everything else is Frozen tables keyed by that id.

Parsed from pret into `v3-map-metadata.json` (248 maps):

| Field | Source |
|---|---|
| const name, id, width, height | `constants/map_constants.asm` |
| town / route / indoor | `FIRST_ROUTE_MAP` / `FIRST_INDOOR_MAP` |
| tileset (`OVERWORLD`, `GYM`, `POKECENTER`, `CAVERN`, …) | `data/maps/headers/*.asm` (`map_header`) |
| N/S/W/E connections | `connection` macros |
| warp count, object count, `has_trainer` | `data/maps/objects/*.asm` (`OPP_*`) |
| story tags | overlay (gym, HM, ship, silph, safari, …) |

Also in RAM while on a map (already in the RAM catalog): `wCurMapTileset` `0xD367`, `wNumberOfWarps`/`wWarpEntries`, `wMapPalOffset` (Flash), `wCurMapConnections`.

Online walkthroughs (Bulbapedia parts, GameFAQs) are how the **tags** were chosen; they should not be scraped at train time. puffer's `MAP_ID_COMPLETION_EVENTS` is the pattern: don't boost Tower until Silph Scope, don't boost Route 23 until Earth, gym maps complete on `EVENT_BEAT_*`.

`wCurMap == 0xFF` is a transition sentinel (v2 already special-cases `< 248`).

---

## 4. Breadcrumbs (3–5 precursors per badge / key beat)

Reward the **sequence**, not only the terminal bit. Each row is a Frozen named channel the researcher can weight. Order is the usual glitchless spine; some pairs are parallel (Misty ↔ Bill).

### Badges

| Terminal | Breadcrumbs (reward earlier) |
|---|---|
| **Boulder / Brock** | `EVENT_GOT_STARTER` → parcel pickup → `EVENT_OAK_GOT_PARCEL` + `EVENT_GOT_POKEDEX` → Viridian Forest / Pewter maps → Pewter Gym (`$36`) |
| **Cascade / Misty** | Mt Moon exit Super Nerd → fossil xor → Cerulean map → (Nugget Bridge / Bill in parallel) → Cerulean Gym `$41` |
| **Thunder / Surge** | `EVENT_GOT_SS_TICKET` → dock/Anne maps → `EVENT_GOT_HM01` **before** `EVENT_SS_ANNE_LEFT` → Cut taught + Cascade → gym locks `EVENT_1ST/2ND_LOCK_OPENED` → Surge |
| **Rainbow / Erika** | Cut usable → Celadon → Cut into gym `$86` → Erika (can be before or after hideout) |
| **Soul / Koga** | Flute or Surf path into Fuchsia → Fuchsia map → (Safari parallel) → gym `$9D` |
| **Marsh / Sabrina** | drinks + `BIT_GAVE_SAFFRON_GUARDS_DRINK` → Saffron map → Card Key → Silph Giovanni → Sabrina `$B2` (gym is enterable once in the city) |
| **Volcano / Blaine** | Surf + Soul → Cinnabar → Secret Key in bag → gym `$A6` quiz gates → Blaine |
| **Earth / Giovanni** | `wObtainedBadges == ~(1<<Earth)` sets `EVENT_VIRIDIAN_GYM_OPEN` (`ViridianCity.asm`) → gym `$2D` → Giovanni. Do not confuse hideout/Silph Giovanni. |

### Key items / story events

| Terminal | Breadcrumbs |
|---|---|
| Oak's Parcel | Viridian Mart `$2A` → bag `$46` → deliver |
| Pokédex | parcel delivered → Oak's Lab |
| Town Map | Daisy, Blues' House (optional) |
| SS Ticket | Cerulean → Route 25 → `EVENT_USED_CELL_SEPARATOR_ON_BILL` → ticket |
| HM01 Cut | ticket → Anne 2F rival script → captain `$65` |
| Bike Voucher | Vermilion Fan Club `$5A` |
| Bicycle | voucher → Cerulean Bike Shop `$42` |
| HM05 Flash | Cut → Route 2 gate aide (10 owned) |
| Coin Case | Celadon hidden / Game Corner |
| Lift Key | hideout entered → B4F drop event |
| Silph Scope | Lift Key → hideout Giovanni (bag `$48`, no GOT event) |
| Poké Flute | Scope → Tower ghosts/Marowak → Fuji |
| HM02 Fly | Flute → Snorlax R16/R12 → R16 house; Thunder to *use* |
| Gold Teeth | Safari West |
| HM04 Strength | teeth → Warden; Rainbow to *use* |
| HM03 Surf | Safari Secret House `$DE`; Soul to *use* |
| Card Key | Saffron + Silph 5F (bag `$30`) |
| Master Ball / Silph Giovanni | Card Key door bits → 11F |
| Secret Key | Mansion B1F (bag `$2B`) |
| Lapras | Silph 7F, `BIT_GOT_LAPRAS` (not an event flag) |
| Champion / HOF | Route 23 badge checks → VR Strength → E4 rooms → `EVENT_BEAT_CHAMPION_RIVAL` |

Softlock breadcrumbs (tag, don't Score as success): Anne left without HM01; Cinnabar sea without Surf; Blaine door without Secret Key.

---

## 5. Magikarp salesman and other time/money sinks

### Magikarp (clear RAM bit)

Mt Moon Pokémon Center `$44`, `scripts/MtMoonPokecenter.asm`:

- Cost ₽500 BCD (`hMoney+1 = $5`)
- `GivePokemon` Magikarp **level 5**
- Sets `EVENT_BOUGHT_MAGIKARP` (one-time; afterwards "no refunds")
- Already in the RAM catalog as COULD

This is a **named waste**. Detecting the event is enough; no hook required. Do not put it in Frozen Score. Training reward can **penalize** the bit (or ignore it). Buying it is not required for Any%.

**Score leak:** spec D5 has `0.1 · min(level_sum, 100)`. A Lv5 Magikarp is **+5** on that sum (+0.5 Score if still under the cap). Catching anything else does the same. If Editable `train.py` uses *uncapped* level-sum, the salesman is a free reward. Subtract those 5 while `EVENT_BOUGHT_MAGIKARP` is set and a Lv5 Magikarp is in the party, or Score only the highest 3–4 mons — don't let `GivePokemon` look like progress.

### Other wasteful / farmable interactions (detectable)

| Thing | Signal | Notes |
|---|---|---|
| Museum ticket | `EVENT_BOUGHT_MUSEUM_TICKET` `0xD754.0` | Already **excluded from Score**. ₽50 loop. |
| Game Corner slots | `wPlayerCoins` delta, map `$87` | Farmable; keep out of Score. |
| Celadon drinks | bag `$3C/$3D/$3E` | **One drink is required** for Saffron. Extra drinks are mart spam. |
| Vending / mart spam | money down + potion/ball qty up | Only punish unbounded farming, not "bought 5 balls." |
| Name Rater | naming-screen hook + map | Optional.
| Daycare | `wDayCareInUse` | Mixed (levels while walking). |
| Fighting Dojo "done" | `EVENT_DEFEATED_FIGHTING_DOJO` | pokegym weights this **negative** (wrong Hitmon / skip). |
| Nugget Bridge nugget | `EVENT_GOT_NUGGET` | **Good** (money up), not a waste. |
| Bike shop without voucher | map `$42` + no voucher | Can't buy; time sink talking. |

Hooks help for "opened slots" / "talked to salesman"; the Magikarp **purchase** is the event bit.

---

## 6. Exp. All / exp sharing

| Signal | Addr / id | Notes |
|---|---|---|
| Item | `EXP_ALL` `$4B` | **Not a key item** (`key_items.asm` `dbit FALSE`) → **can be tossed** |
| Got it | `EVENT_GOT_EXP_ALL` | Route 15 gate 2F `$B9`, Oak's aide |
| In-battle | `wBoostExpByExpAll` `0xCC5B` | Set `TRUE` on the second `GainExperience` pass when the item is in the bag (`engine/battle/core.asm`) |
| Use from bag | `UnusableItem` | Passive; "using" it does nothing |

Gen 1 behavior (must not invent Gen 2 Equal Exp): if Exp. All is **in the bag**, fighters get half, then the other half is split across the whole party. Removing it from the bag disables it. Tossing it is possible and bad.

**Reward:** `EVENT_GOT_EXP_ALL` is a fine SHOULD breadcrumb (aide requires 50 owned). Do not Score "exp gained with Exp. All on" (grind). Observing `wBoostExpByExpAll` is enough to know it fired this KO.

---

## 7. Tossing useful vs useless items

Toss path: Start → Item → `USE_TOSS_MENU` → `TossItem_` (`item_effects.asm`).

Blocked (carry set, `TooImportantToTossText`):

- Any HM (`IsItemHM`: id in `[HM01, TM01)`)
- Key-item flag table (`IsKeyItem_`) — Parcel, tickets, keys, Scope, Flute, rods, Town Map, Bike, fossils, Coin Case, … **not** Exp. All, **not** TMs, **not** Nugget, **not** drinks

There is **no RAM bit "just tossed X."** Detect:

1. Hook `TossItem_` success (carry clear) and read `wCurItem` + `wItemQuantity`, or
2. Bag snapshot delta **without** a matching UseItem / PC deposit / in-battle item.

Frozen should classify `wCurItem` with a static table:

| Class | Examples | Suggested training signal |
|---|---|---|
| Impossible | HMs, key items | never happens |
| Unique / missable | TM08 Body Slam, TM13 Ice Beam, TM26, TM29, drinks **before** Saffron, last balls | **penalize toss** |
| Optional unique | Exp. All, fossils after revive, leftover voucher | mild penalty |
| Filler | extra potions, Repels, Nuggets (sell better), bought TMs from Celadon 2F | allow / small bonus if bag was full (`wNumBagItems==20`) |
| PC deposit | not a toss | different hook (`players_pc.asm`) |

Bag-full (`wNumBagItems == 20`) is the legitimate reason to toss. Reward "made space then picked up Card Key" rather than "threw away a Potion."

---

## 8. Death / blackout vs Center heal

Three different heals. Rewarding "HP went up" hits all of them.

| Kind | How | Money | Map | Distinct signal |
|---|---|---|---|---|
| **Blackout (wipe)** | `HandleBlackOut` → `ResetStatusAndHalveMoneyOnBlackout` → `HealParty` → warp | **halved** | to `wLastBlackoutMap` (last Center; Safari rest houses ignored) | hook `HandleBlackOut`; or `wIsInBattle==$FF` then warp; or `wOutOfBattleBlackout` for poison wipe |
| **Nurse heal** | `DisplayPokemonCenterDialogue_` → `HealParty` → **`AnimateHealingMachine`** | unchanged | same Center; also `SetLastBlackoutMap` | hook `AnimateHealingMachine` (puffer already does; sets `pokecenter_heal=1`) |
| **Other HealParty** | Mom's house, Tower 5F shrine, Oak's Lab, Silph 9F | unchanged | same map | hook `HealParty` minus the two above |

`BIT_USED_POKECENTER` (`wStatusFlags4` bit 2) is **not** a per-visit flag. It is set on first Center talk ever and only skips the "Shall we heal?" line afterwards.

`wLastBlackoutMap` is the checkpoint even if you never fainted — nurse sets it on a successful heal.

**Reward policy (do not Score HP):**

- Count blackouts (puffer `blackout_count`). A small **penalty** is OK; a large one teaches "never fight."
- Do **not** reward HP restoration or nurse visits (heal-farming, the documented hack).
- Optional: reward *winning* (`wBattleResult==0` on exit) or "survived a trainer" without touching HP.
- Poison overworld wipe is the same `HandleBlackOut` path — one counter covers both.

puffer's `blackout_check` reward term is **commented out**. They still **observe** `blackout_map_id`. Copy that split: observe death, don't pay for healing.

Need-based heals (good vs bad) are §10. Undamaged wins (`wBattleResult==0` and party HP unchanged / no faint) stay a clean positive.

---

## 9. Fight / run / capture

Same idea as naming: **hooks for the action**, Frozen tables for whether it was smart. You cannot read "should have run" out of a single RAM byte.

### Battle menu (each turn)

`DisplayBattleMenu` (`engine/battle/core.asm`). English layout after an in-function ID swap:

| `wCurrentMenuItem` (saved in `wBattleAndStartSavedMenuItem` `0xCC2D`) | Normal | Safari (`wBattleType==2`) |
|---|---|---|
| 0 | **FIGHT** (also zeros `wNumRunAttempts`) | BALL |
| 1 | PKMN | ROCK |
| 2 | ITEM | BAIT |
| 3 | RUN | RUN |

Trainer battles: `TryRunningFromBattle.trainerBattle` prints `NoRunningText` and **never** sets carry. Wild: speed formula + 30 per extra attempt in `wNumRunAttempts` `0xD120`. Ghost Marowak and Safari always allow escape. Failed run still **consumes the turn** (`wActionResultOrTookBattleTurn=1`).

Successful run sets `wBattleResult = 2` (draw). Win = 0, lose = 1 (`end_of_battle.asm`).

### Capture

Balls only in wild (`wIsInBattle==1`). Trainers → `ThrowBallAtTrainerMon`. Ghost / Tower Marowak uncatchable. Master Ball always works.

Hook points (puffer already counts `ItemUseBall.loop`):

| Hook | Meaning |
|---|---|
| `ItemUseBall.loop` | ball thrown |
| `ItemUseBall.captured` | success; `wCapturedMonSpecies` `0xD11C` |
| `ItemUseBall.failedToCapture` | broke out |
| `ItemUseBall.sendToBox` | party full |
| `GivePokemon` / `_AddPartyMon` | *any* new party member (catch **or** salesman **or** Lapras) |

Dex bit in `wPokedexOwned` flipping is the Score-relevant catch. Party-level-sum is not.

### Frozen species policy (not RAM)

Wild tables: `data/wild/maps/*.asm` (Route 1 is only Pidgey/Rattata). Tag species once:

| Tag | Examples | Default advice |
|---|---|---|
| `must_fight` | any `wIsInBattle==2`, gym, rival, Marowak, Snorlax | FIGHT (run is illegal or the fight *is* the breadcrumb) |
| `worth_catch` | first of a dex slot; Nidoran♂; Spearow/Pidgey if no Flyer; Abra; gift Lapras already covers Surf; legendaries optional | ball if unseen or HM-slave gap |
| `worth_ko` | wilds when party is under the next gym's level band | FIGHT for XP, then leave |
| `worth_run` | Zubat corridors, high-level water with a living Surf slave, dupes after the dex bit | RUN |
| `trap` | Magikarp salesman, safari filler if not HM03/teeth | don't buy / don't grind |

Safari has **no FIGHT** — BALL/BAIT/ROCK/RUN only.

The researcher gets `(wild vs trainer, species, level, already_owned, party_has_cut/fly/surf, hp_frac)` plus the action taken. Extremes are easy: run from Brock is terrible; run from the 12th Zubat is good; first Pidgey catch is good; 6th Rattata is not.

---

## 10. Need-based healing (nurse, potions, status)

The engine already distinguishes some bad item heals:

- Potion / Super / Hyper / Max / drinks on **full HP** → `.healingItemNoEffect` (no consume).
- Revive on a living mon → no effect. Potion on a fainted mon → no effect.
- Full Restore on full HP **with** status still cures (treated as Full Heal).
- Status items (Antidote, …) no-op if that status is absent.

**Nurse does not no-op.** `HealParty` always runs, even at full HP. That is the time-waste: talking to the nurse when nobody needs it.

Expose, per heal event:

| Field | Source |
|---|---|
| `kind` | nurse hook vs `ItemUseMedicine` vs Mom/Tower/Oak |
| `item_id` | `wCurItem` (0 for nurse) |
| `slot` | `wWhichPokemon` |
| `hp_before / max` | party struct before the hook returns |
| `status_before` | slot status |
| `effect` | success vs `.healingItemNoEffect` vs cancelled |

Very good: nurse or potion when `min(hp/max) < ~0.4`, anyone fainted, or a status before a gym/trainer.  
Very bad: nurse with all HP full and no status; using a potion that the engine rejects (already free — don't reward the attempt).  
Middle (don't bother encoding): topping off from 85% on a route.

Do **not** pay for HP going up as a dense per-step term. Pay the **decision**: `heal_needed ∧ healed` vs `heal_unneeded ∧ nurse`. Undamaged trainer wins remain the complementary positive (fought and didn't need a heal).

---

## 11. Mart buy / sell (mechanics)

`DisplayPokemartDialogue_` (`engine/events/pokemart.asm`). Not a map change; `wCurMap` stays the MART tileset map.

Loop: `BUY_SELL_QUIT_MENU` → `wChosenMenuItem` 0 buy / 1 sell / 2 quit (`wMenuExitMethod==CANCELLED_MENU` also quits).

**Buy**

1. List comes from `wItemList` / `wItemListPointer` (that mart's ROM inventory, `data/items/marts.asm` + each mart script).
2. `DisplayChooseQuantityMenu` writes `wItemQuantity` (cap 99).
3. `HasEnoughMoney` / `.isThereEnoughMoney`; fail → `.notEnoughMoney`.
4. `AddItemToInventory` on `wNumBagItems`; fail → `.bagFull`.
5. `SubtractAmountPaidFromMoney`.
6. `wBoughtOrSoldItemInMart` `0xCF0A` ← 1 (sticky for the rest of this talk).
7. `SFX_PURCHASE`.

**Sell**

1. Bag list (`ITEMLISTMENU`). Empty bag → `.bagEmpty`.
2. `IsKeyItem` or `IsItemHM` → `.unsellableItem` (same set as toss-blocked, minus TMs which *are* sellable).
3. `hHalveItemPrices` set → sell price is half the buy price (`DisplayChooseQuantityMenu`).
4. Yes/no → `AddAmountSoldToMoney` + `RemoveItemFromInventory`.

RAM to snapshot **inside** the buy/sell success path (unions afterwards): `wCurItem`, `wItemQuantity`, `wPlayerMoney` before/after, `wBoughtOrSoldItemInMart`.

Hooks: `DisplayPokemartDialogue_.buyMenu` (entered shop UI), the success fall-through after `SubtractAmountPaidFromMoney`, sell success after `AddAmountSoldToMoney`. Bike shop is a different script (voucher → Bicycle, cannot buy with cash).

Strategy stays Editable: balls/potions when bag isn't stuffed, one drink for Saffron, don't dump TMs. Frozen only needs "bought id×qty for ₽X" and "sold id×qty for ₽Y."

---

## Frozen extraction checklist (new)

Hooks (same style as puffer Cut/Flute/blackout):

- `DisplayNamingScreen` → `in_naming`, `naming_kind`
- `LearnMove` / forget-menu → `learn_move_pending`, `wMoveNum`, slot
- `TossItem_` (success) → `tossed_item_id`, qty
- `HandleBlackOut` → `blackout_count++`
- `AnimateHealingMachine` → nurse heal + **HP/status before** (need-based, not a free HP drip)
- `DisplayBattleMenu` → fight / pkmn / item / run (Safari: ball / rock / bait / run)
- `TryRunningFromBattle` → escaped / failed / trainer-blocked
- `ItemUseBall.captured` / `.failedToCapture` → `wCapturedMonSpecies` vs breakout
- `ItemUseMedicine` → success vs `.healingItemNoEffect` + HP before
- `DisplayPokemartDialogue_` buy/sell success → `wCurItem`, qty, money delta
- already wanted: Cut / Surf / Flute / start menu / ball throw (`ItemUseBall.loop`)

RAM / events already catalogued, now known to matter here:

- `EVENT_BOUGHT_MAGIKARP`, `EVENT_BOUGHT_MUSEUM_TICKET`, `EVENT_GOT_EXP_ALL`
- bag `EXP_ALL` `$4B`, `wBoostExpByExpAll`
- `wIsInBattle==$FF`, `wOutOfBattleBlackout`, `wLastBlackoutMap`, `wBattleResult` (0 win / 1 lose / 2 ran)
- `wNumRunAttempts`, `wCapturedMonSpecies`, `wBoughtOrSoldItemInMart`
- `wNumBagItems==20`

Metadata:

- `v3-map-metadata.json` keyed by `wCurMap`
- breadcrumb lists above as named aliases on the event/item/map bundle
- item class table for toss (key / HM / unique TM / filler)
- species tags: `must_fight` / `worth_catch` / `worth_ko` / `worth_run` / `trap`
- mart inventories from `data/items/marts.asm`

Default policy can ignore all of this. The auto-researcher cannot invent "got stuck on the nickname screen" or "wiped and the nurse healed me" without the hooks.
