# v3 observation / reward RAM catalog

Status: research, 2026-09-13
Audience: Frozen env + Editable `train.py` (auto-researcher gym, spec `.scratch/autoresearcher-gym/spec.md`)

Ground truth: pret/pokered clone at `~/dev/pokered/` (`ram/wram.asm`, `constants/event_constants.asm`, `constants/ram_constants.asm`, `pokered.sym`). Cross-checked against v2 (`v2/red_gym_env_v2.py`), [pokerl](https://github.com/drubinstein/pokerl) observations, `~/dev/pokemonred_puffer`, `~/dev/pokegym`, and walkthroughs ([Bulbapedia Red/Blue](https://bulbapedia.bulbagarden.net/wiki/Walkthrough:Pokémon_Red_and_Blue), [GameFAQs zerokid TMs/HMs + key items + badges](https://gamefaqs.gamespot.com/gameboy/367023-pokemon-red-version/faqs/64175/tms-and-hms), [IGN S.S. Anne](https://www.ign.com/wikis/pokemon-red-blue-yellow-version/S.S._Anne)).

Companion machine table: `v3-obs-ram-map.json`. Ground-truth WRAM dump (struct strides, full `EVENT_*` bit indices, HRAM): `pokered-wram-rl-catalog.md`. Naming / forget-move / toss / death / breadcrumbs: `v3-obs-ui-death-breadcrumbs.md`. Map tags: `v3-map-metadata.json`.

---

## How to read this

Two different consumers, one RAM dump:

| Consumer | What it needs |
|---|---|
| **Policy observation** | A compact, learnable view. Putting 2560 event bits + bag + full battle struct in every step is legal; it is not free. |
| **Reward / researcher** | Labeled, address-verified signals so `train.py` can credit-assign *without guessing*. If a bit exists in RAM and is not extracted, the auto researcher cannot invent it. |

**MUST** = Frozen env must extract (or the researcher cannot shape a game-beating reward).  
**SHOULD** = strongly improves credit assignment or battle/menu competence.  
**COULD** = useful, high-dim, farmable, or volatile; expose it, but default Score must not use it.

The Seam that matches spec D2: Frozen **extracts** a labeled snapshot every step; Editable `train.py` **selects** which channels go to the policy and which go into training reward. Frozen Score (D5) stays one-way bits only.

---

## What v2 extracts today (the gap)

Policy obs (`RedGymEnv._get_obs`): screens (72×80×3), HP fraction, Fourier level-sum, 8 badge bits, event bits `0xD747–0xD87D` (stops 8 bytes early), 48×48 explore-map window, last 3 actions.

Also *read but not observed*: coords/map (`0xD362/0xD361/0xD35E`), party species, dex seen, `wIsInBattle` (explore gating only), opponent levels (reward term commented out), play clock unused.

Encoding traps (do not copy into v3):

- Badge obs uses `f"{byte:08b}"` so index 0 is **Earth (MSB)**, index 7 is **Boulder**. pret/DataCrystal bit0 is Boulder. Score popcount is fine; per-badge policy channels are reversed vs every other gym.
- Event-name logging uses the same MSB-first enumerate against `events.json` keys that are pret **LSB=0**. The env even comments `# TODO this currently seems to be broken!`.

**Missing from the policy and from any labeled snapshot:** bag/key items, whether a party mon *knows* Cut/Fly/Surf/Strength/Flash, in-battle enemy species/HP/types/status, facing, walk/bike/surf, Safari steps, blackout map, four story bits that are *not* in `wEventFlags`, toggleable-object / item-ball flags, menu cursor.

That is the whole problem. Event-bit count is a blunt instrument: it cannot tell "got HM01" from "beat a random sailor", and it cannot tell "owns HM01" from "taught Cut" from "has Cascade Badge so Cut works on bushes".

---

## Architectural recommendation

Frozen env should emit, every decision step:

1. **Screen stack** (keep v2).
2. **Labeled RAM bundle** (this catalog), including the four extra-event bits pokerl/puffer had to invent.
3. **Derived convenience flags** computed from RAM (party-knows-HM, bag-has-item, field-move-legal). These are not extra information; they are encodings the researcher will otherwise re-derive badly.
4. **Frozen map metadata** keyed by `wCurMap` (gym? HM? key NPC? legendary?). This is ROM knowledge, not RAM.

`train.py` then chooses a subset. Default v3 baseline can reproduce v2 obs; richer channels are available without a Frozen-set bump.

---

## Priority 0 — MUST extract (policy + reward + Score)

### Mode: overworld vs battle vs lost

| Symbol | Addr | Encoding | Why |
|---|---|---|---|
| `wIsInBattle` | `0xD057` | 0 none, 1 wild, 2 trainer, `$FF` just lost | Every other channel is context-dependent. Explore must ignore battle coords (v2 already does). Battle rewards / type play require this gate. |

### Position and map

| Symbol | Addr | Encoding | Why |
|---|---|---|---|
| `wCurMap` | `0xD35E` | map id | Unique maps (Score D5), splits, Frozen map metadata lookup. |
| `wYCoord` / `wXCoord` | `0xD361` / `0xD362` | tile | Explore, stuck, warp, replay. |
| `wPlayerDirection` | `0xD52A` | facing | pokerl: without this the sprite↔orientation mapping is slow to learn. |
| `wSpritePlayerStateData1FacingDirection` | `0xC109` | sprite facing (`//4` in puffer) | Same signal, sprite-side. |
| `wWalkBikeSurfState` | `0xD700` | 0 walk, 1 bike, 2 surf | Cycling Road + Surf are gated mechanics, not cosmetics. |
| `wLastBlackoutMap` | `0xD719` | map id of last Center | pokerl/puffer expose this; it is the checkpoint. |
| `wTownVisitedFlag` | `0xD70B` | bitfield, `NUM_CITY_MAPS` | Fly destinations / town map dots. |
| `wMapPalOffset` | `0xD35D` | 6 = dark (Flash needed) | Rock Tunnel without Flash is a different game. |

### Badges (Score + field-move legality)

| Symbol | Addr | Encoding | Why |
|---|---|---|---|
| `wObtainedBadges` | `0xD356` | bit0 Boulder … bit7 Earth | Score D5; HM field-use permission (see badge table). Event `EVENT_BEAT_*` fires at battle end; badge bit is the robust monotonic. |

Badge → field move (GameFAQs / engine): Cascade→Cut, Thunder→Fly, Rainbow→Strength, Soul→Surf, Boulder→Flash. Owning the HM, knowing the move, and holding the badge are **three independent bits**. Vermilion Gym is unreachable without Cut *usable* (HM01 + Cascade + a party mon that knows Cut).

### Event flags (full range)

| Symbol | Addr | Size | Why |
|---|---|---|---|
| `wEventFlags` | `0xD747` | 320 bytes, `NUM_EVENTS = $A00` = 2560 bits, ends `0xD886` | Spec D15. v2 stops at `0xD87E` and misses Rock Tunnel 2 trainer 7, Seafoam boulder puzzle, `EVENT_BEAT_ARTICUNO`. |

Named events are in `v2/events.json` / `event_constants.asm`. **Do not reward the raw popcount as the only story signal** — it is what v2 does, and it mixes "beat Brock" with "bought museum ticket" (already excluded) and hundreds of trainer bits. Extract the full bitfield; let `train.py` weight a `REQUIRED_EVENTS` subset (puffer already listed one).

### Story bits that are NOT in `wEventFlags`

pokerl and puffer independently discovered four required flags living elsewhere. Frozen must expose them or the researcher will never see them:

| Signal | Where | Addr / bit | Why |
|---|---|---|---|
| Rival 3 (S.S. Anne) | `wSSAnne2FCurScript == 4` | `0xD665` | No `EVENT_BEAT_SS_ANNE_RIVAL`. Script byte is the only RAM completion signal. |
| Lapras gift | `wStatusFlags4` bit `BIT_GOT_LAPRAS` | `0xD72E` bit 0 | Surf slave; required for Cinnabar without an alternative Water-type. |
| Saffron guards | `wStatusFlags1` bit `BIT_GAVE_SAFFRON_GUARDS_DRINK` | `0xD728` bit 6 | Red/Blue uses Fresh Water / Soda Pop / Lemonade, **not** Tea (Yellow). Not an event flag. |
| Game Corner Rocket | `TOGGLE_GAME_CORNER_ROCKET` in `wToggleableObjectFlags` | `0xD5A6` bit index `$46` | Hideout entrance. Not an event flag. |

Also extract the rest of `wStatusFlags1` (`0xD728`): `BIT_STRENGTH_ACTIVE`, `BIT_SURF_ALLOWED`, rod bits, drink bit.

### Party (overworld + battle)

Struct: `party_struct` at `wPartyMon1` `0xD16B`, stride `$2C` (`PARTYMON_STRUCT_LENGTH`). `wPartyCount` `0xD163`. Species list `wPartySpecies` `0xD164` (6 + `$FF` sentinel). Box mons stop at `$21` (`BOXMON_STRUCT_LENGTH`); only the current box is in WRAM (`wBoxDataStart` `0xDA80`). Other boxes are SRAM.

Per mon (offsets from `wPartyMonN`):

| Field | Off | Size |
|---|---|---|
| Species | +0 | 1 |
| HP | +1 | 2 BE |
| BoxLevel (party unused) | +3 | 1 |
| Status | +4 | 1 (SLP 0–7, PSN/BRN/FRZ/PAR bits) |
| Type1/Type2 | +5/+6 | 1+1 |
| Moves[4] | +8 | 4 |
| PP[4] | +$1D | 4 |
| Level | +$21 (`wPartyMon1Level` = `0xD16B+$21` = `0xD18C`) | 1 |
| MaxHP | +$22 (`0xD18D`) | 2 BE |
| Atk/Def/Spe/Spc | +$24… | 2 BE each |

Do **not** reuse party offsets on `wEnemyMon` / `wBattleMon`. In `battle_struct`, +3 is `PartyPos` and **level is +$0E**.

MUST: species, HP, maxHP, level, status, types, moves, PP.  
Derived MUST: `party_knows_hm[5]` by scanning moves for Cut `$0F`, Fly `$13`, Surf `$39`, Strength `$46`, Flash `$94` (puffer `check_if_party_has_hm`; pokegym `get_hm_move_obs`).

Score already uses level-sum (capped) and dex. Party moves are how you detect "taught Cut" vs "owns HM01".

### Bag / key items / HMs

| Symbol | Addr | Encoding |
|---|---|---|
| `wNumBagItems` | `0xD31D` | count, cap 20 |
| `wBagItems` | `0xD31E` | 20 × (item id, qty), `$FF` terminator |

Key-item IDs (`data/items/key_items.asm`): Town Map `$05`, Bicycle `$06`, Pokédex `$09`, fossils/amber, Secret Key `$2B`, Bike Voucher `$2D`, Card Key `$30`, S.S. Ticket `$3F`, Gold Teeth `$40`, Coin Case `$45`, Oak's Parcel `$46`, Itemfinder `$47`, Silph Scope `$48`, Poké Flute `$49`, Lift Key `$4A`, rods `$4C–$4E`. HMs `$C4–$C8`. (EXP All `$4B` is **not** a key item.)

Puffer `REQUIRED_ITEMS`: Secret Key, Card Key, S.S. Ticket, Gold Teeth, Oak's Parcel, Silph Scope, Poké Flute, Lift Key, HM01, HM03, HM04.

**Many key items have no dedicated event bit** (Silph Scope, Card Key, Secret Key live in the bag). Event flags cover *receiving* some of them (`EVENT_GOT_HM01`, `EVENT_GOT_SS_TICKET`, …) but bag membership is the source of truth after tossing is impossible.

Derived MUST: `bag_has[item_id]` for the required set, plus `bag_has_hm[5]`.

### Pokédex

| Symbol | Addr | Size |
|---|---|---|
| `wPokedexOwned` | `0xD2F7` | 19 bytes (151 bits) |
| `wPokedexSeen` | `0xD30A` | 19 bytes; last bit unused (v2 masks `0xD31C &= 0x7F`) |

Score D5 uses both. Extract both bitfields, not just a count.

### Play clock (splits, not policy)

`wPlayTimeHours` `0xDA41` … frames `0xDA45`, plain binary (not BCD). Spec D16. Telemetry only.

---

## Priority 1 — MUST for battle competence (SHOULD for overworld-only policies)

When `wIsInBattle != 0`, the screen is a fight. Without enemy RAM the policy is reading HP bars off pixels.

Active battle mons (`battle_struct`):

| Symbol | Addr | Why |
|---|---|---|
| `wEnemyMon` species/HP/status/types/level/maxHP/stats/moves/PP | `0xCFE5`… | Current foe. Moves are hidden from a human on turn 1; still the strongest battle-reward signal. pokerl omitted enemy moves on purpose (human-like). Expose them in the RAM bundle; let `train.py` decide. |
| `wBattleMon` same | `0xD014` | Active party slot (may differ from party[0] after switches). |
| `wDamageMultipliers` | `0xD05B` | bits 0–6 effectiveness (`$0` immune, `$5` NVE, `$A` neutral, `$14` SE); bit 7 STAB. Filled after the move resolves — useful for reward, laggy for action selection. |
| `wPlayerBattleStatus1–3` / `wEnemyBattleStatus1–3` | `0xD062–0xD069` | Wrap/trap, Fly/Dig invuln, confuse, substitute, toxic, recharge, seed, reflect, light screen. Wrap is a common "agent looks stuck" failure. |
| `wPlayerMon*Mod` / `wEnemyMon*Mod` | `0xCD23` / `0xCD2E` area | Stat stages (base 7). |
| `wTrainerClass` / `wCurOpponent` / `wGymLeaderNo` | `0xD031` / `0xD059` / `0xD05C` | Gym vs random vs rival. |
| `wBattleType` | `0xD05A` | 0 normal, 1 Old Man, 2 Safari. |
| `wEnemyPartyCount` + `wEnemyMon1–6` | `0xD89C`, `0xD8A4` stride `$2C` | Remaining trainer party (levels at `0xD8C5`, `0xD8F1`, … — v2 already listed these for `max_opponent_level`). **Union** with `wGrassMons`/`wWaterMons` — invalid as a party during overworld. |
| `hWhoseTurn` | `0xFFF3` HRAM | 0 player / 1 enemy. |
| `wCurEnemyLevel` | `0xD127` | Wild/trainer current level. |
| `wPlayerSelectedMove` / `wEnemySelectedMove` | `0xCCDC` / `0xCCDD` | Chosen move ids. |
| `wBattleResult` | `0xCF0B` | 0 win / 1 lose / 2 draw. |
| `wActionResultOrTookBattleTurn` | `0xCD6A` | Whose turn / action result. |
| `wCurrentMenuItem` | `0xCC26` | Fight/bag/mon/run cursor. |
| `wPlayerMonNumber` / `wBattleMonPartyPos` | `0xCC2F` / `0xD017` | Active party slot. |

pokegym already exposes enemy + player battle species/types/moves/PP. v2 exposes none of it.

---

## Priority 2 — SHOULD extract (story density, menus, puzzles)

### Script bytes (`wGameProgressFlags` `0xD5F0–0xD6B7`)

Map-local script indices. Rival 3 is the famous one (`wSSAnne2FCurScript`). Others gate Oak, Pewter gym guy, Bill, etc. Extract the whole 200-byte block; document the few that are known completion signals. Volatile (can bounce); do not put in Frozen Score.

### Toggleable objects / item balls

`wToggleableObjectFlags` `0xD5A6`, 32 bytes (`$100` bits). Bit set = sprite hidden (item taken, NPC gone). This is how item-balls, S.S. Anne objects, Game Corner Rocket, Fuji, fossils-as-sprites, etc. disappear. Complementary to event flags. pokerl/puffer call them missables / HS_*.

### Hidden items

`wObtainedHiddenItemsFlags` `0xD6F0` (`MAX_HIDDEN_ITEMS` 112). Itemfinder targets. COULD for Score (farmable-ish); SHOULD for "did we get TM24's hidden counterpart" audits.

### Safari

| Symbol | Addr |
|---|---|
| `wSafariSteps` | `0xD70D` (dw, starts 502) |
| `wNumSafariBalls` | `0xDA47` |
| `wSafariZoneGameOver` | `0xDA46` |

Without steps remaining, agents stall in Safari (pokerl). HM03 and Gold Teeth live here. Safari bait/escape: `wSafariEscapeFactor` `0xCCE8`, `wSafariBaitFactor` `0xCCE9`.

### Field-move / puzzle state

| Symbol | Addr | Why |
|---|---|---|
| `BIT_STRENGTH_ACTIVE` | `wStatusFlags1` bit 0 | Boulder puzzles (Victory Road, Seafoam, gym). |
| `wTileInFrontOfPlayer` | `0xCFC6` | Cut bush / surf water / strength boulder detection without vision. |
| `wCutTile` | `0xCD4D` | Last cut tile (pokegym: `== 61` means Cut just used). |
| Seafoam / Victory Road boulder events | in `wEventFlags` | Spec D15 gap. |
| Vermilion gym locks | `EVENT_1ST_LOCK_OPENED`, `EVENT_2ND_LOCK_OPENED` | Trash-can puzzle. |
| `wFirstLockTrashCanIndex` / `wSecondLockTrashCanIndex` | `0xD743` / next | Current puzzle solution (changes per entry). |
| Cinnabar gym quiz gates | `EVENT_CINNABAR_GYM_GATE0–6_UNLOCKED` | |
| Silph card-key doors | `EVENT_SILPH_CO_*_UNLOCKED_DOOR*` | Many bits; Card Key in bag is the capability, these are progress. |
| `wCardKeyDoorY/X` | `0xD73F` / `0xD740` | Door being unlocked. |
| `EVENT_MANSION_SWITCH_ON` | bit `$278` → `0xD796.0` | Pokémon Mansion switch. |
| `wLastMap` | `0xD365` | Previous map (warp/backtrack). |
| `wCurMapTileset` | `0xD367` | Tileset; bit 7 = no previous map. |
| `wNumberOfWarps` / `wWarpEntries` | `0xD3AE` / `0xD3AF` | Map-local warp table (changes on load). |
| `wMovementFlags` | `0xD736` | Door / warp pad / ledge / spin. |
| `wTilePlayerStandingOn` | `0xCF0E` | Current BG tile. |
| `wObtainedHiddenCoinsFlags` | `0xD6FE` | Game Corner hidden coins (16 bits). |

### Menu / text (so the policy knows it is not on the map)

| Symbol | Addr | Why |
|---|---|---|
| `wJoyIgnore` | `0xCD6B` | Inputs dropped (scripted movement, text). |
| `wSimulatedJoypadStatesIndex` | `0xCD38` | Forced-walk scripts. |
| `wStatusFlags5` | `0xD730` | `BIT_DISABLE_JOYPAD`, scripted movement. |
| `wStatusFlags4` | `0xD72E` | Lapras, used Center, no-battles, blackout. |
| `wCurrentMenuItem` / `wMaxMenuItem` | `0xCC26` / nearby | Start/bag/party. puffer rewards *seeing* these menus because agents otherwise never open bag to teach Cut. |
| `wFontLoaded` | `0xCFC4` bit 0 | Text box using sprite VRAM (overworld NPCs frozen). |
| `wTextBoxID` / `hWY` | `0xD125` / `0xFFB0` | Dialog up. |
| `wMiscFlags` | `0xCD60` | Trainer sight, boulder, PC. |
| `wOutOfBattleBlackout` | `0xD12D` | Party wipe outside battle. |
| `hJoyHeld` | `0xFFB4` | Actual buttons. |

### Money / balls / healing inventory (reward with a cap, never Score)

`wPlayerMoney` `0xD347` 3-byte BCD. Spec D5 excludes money from Score (farmable). Bag qtys of balls/potions/revives are SHOULD for the policy (catch + survival) and COULD for reward (heal-farming is a documented hack).

### Daycare / boxes / HOF

`wDayCareInUse` `0xDA48`, `wBoxCount` `0xDA80`, `wCurrentBoxNum` `0xD5A0`, `wNumHoFTeams` `0xD5A2`. COULD. HOF team count is a Champion proxy; prefer `EVENT_BEAT_CHAMPION_RIVAL`. `wPlayerStarter` `0xD717` / `wRivalStarter` `0xD715` SHOULD (rival teams). `wBeatGymFlags` `0xD72A` is a redundant copy of badges — prefer `wObtainedBadges`. `wBoostExpByExpAll` `0xCC5B` if Exp. All is owned (`EVENT_GOT_EXP_ALL` / item `$4B`).

### Elite Four

`wElite4Flags` `0xD734`: `BIT_STARTED_ELITE_4`. Plus `EVENT_BEAT_LORELEI/BRUNO/AGATHA/LANCE/CHAMPION_RIVAL` and `EVENT_AUTOWALKED_INTO_*`. Spec D16 already splits Champion; E4 room bits exist if wanted (spec out of scope).

---

## Priority 3 — COULD / do not Score

- DVs, stat exp, catch rate, OT ID (obedience for traded mons; irrelevant if no trades).
- `hRandomAdd`/`hRandomSub` (`0xFFD3`/`0xFFD4`) — never reward RNG.
- Audio, OAM, tilemap backups, link-cable, slot machines.
- `wPlayerCoins` — Game Corner farming.
- Full PC box (20 mons × 12 boxes) — huge, rarely needed for Any%.
- Type-chart ROM table — can be Frozen metadata; not RAM.
- Wild encounter tables for current map (`wGrassRate`/`wWaterRate` union with enemy party — **invalid during trainer battles**).

---

## Story objects the env must make visible

Sources: Bulbapedia parts 1–16, GameFAQs key items / TMs-HMs / missables, IGN S.S. Anne. Ordered roughly Any% glitchless.

### Key-item chain (bag AND/OR event)

| Item | How you get it | RAM |
|---|---|---|
| Oak's Parcel | Viridian Mart | bag `$46` + `EVENT_GOT_OAKS_PARCEL` / `EVENT_OAK_GOT_PARCEL` |
| Pokédex | Oak, after parcel | bag `$09` + `EVENT_GOT_POKEDEX` |
| Town Map | Daisy | bag `$05` + `EVENT_GOT_TOWN_MAP` |
| S.S. Ticket | Bill | bag `$3F` + `EVENT_GOT_SS_TICKET` |
| HM01 Cut | S.S. Anne captain | bag `$C4` + `EVENT_GOT_HM01` / `EVENT_RUBBED_CAPTAINS_BACK` |
| Bike Voucher | Vermilion Fan Club | bag `$2D` + `EVENT_GOT_BIKE_VOUCHER` |
| Bicycle | Cerulean shop | bag `$06` + `EVENT_GOT_BICYCLE` |
| HM05 Flash | Route 2 gate, Oak's aide (10 owned) | bag `$C8` + `EVENT_GOT_HM05` |
| Lift Key | Hideout B4F | bag `$4A` + `EVENT_ROCKET_DROPPED_LIFT_KEY` |
| Silph Scope | Hideout Giovanni | bag `$48` (no GOT event) |
| Poké Flute | Mr. Fuji after Tower | bag `$49` + `EVENT_GOT_POKE_FLUTE` / `EVENT_RESCUED_MR_FUJI` |
| HM02 Fly | Route 16 gate | bag `$C5` + `EVENT_GOT_HM02` |
| Gold Teeth | Safari West | bag `$40` |
| HM03 Surf | Safari Secret House | bag `$C6` + `EVENT_GOT_HM03` |
| HM04 Strength | Warden, after teeth | bag `$C7` + `EVENT_GOT_HM04` / `EVENT_GAVE_GOLD_TEETH` |
| Card Key | Silph 5F | bag `$30` (no GOT event) |
| Secret Key | Mansion B1F | bag `$2B` (no GOT event) |
| Drink for Saffron | Celadon mart roof | bag `$3C/$3D/$3E` + `BIT_GAVE_SAFFRON_GUARDS_DRINK` |

### Any% MUST spine (reward in this order, not as popcount)

Parcel → Dex → Boulder → (fossil xor) → Cascade + SS Ticket → **HM01 before Anne leaves** → Thunder → Scope → Flute → drinks→Saffron → Card Key → Silph Giovanni → Soul + HM03/HM04 → Surf → Secret Key → Volcano → Earth → VR → E4 → HOF.

Teleport/Dig have **no** badge gate (outdoor / Escape-Rope semantics). Softlocks to tag in metadata: no Cut before Anne leaves; no Surf before the Cinnabar sea path; no Secret Key before Blaine.

### One-way / missable (reward these *before* they vanish)

- **S.S. Anne leaves forever** after `EVENT_RUBBED_CAPTAINS_BACK` → `EVENT_SS_ANNE_LEFT`. TM08 Body Slam, TM44 Rest, and every ship trainer/item are gone. IGN: "once you're there, the ship will leave and never come back." Rival 3 must happen *on the ship* (`wSSAnne2FCurScript`).
- Fossil: `EVENT_GOT_DOME_FOSSIL` XOR `EVENT_GOT_HELIX_FOSSIL`.
- Fighting Dojo: Hitmonlee XOR Hitmonchan.
- Museum ticket (`EVENT_BOUGHT_MUSEUM_TICKET`) is the one event v2/spec already exclude from Score — agents farm the guy.
- Old Amber requires Cut to the museum back door.

### HM triple (always three channels)

For each of Cut/Fly/Surf/Strength/Flash:

1. Own the HM item (bag).
2. A party mon knows the move (party moves).
3. The corresponding badge is set (`wObtainedBadges`) — required for *overworld* use, not in-battle use.

A reward that only watches `EVENT_GOT_HM01` will stall in Vermilion Gym bushes.

### TMs that actually change a policy's ceiling

Not required to beat the game; SHOULD as bag bits + "party knows move":

| TM | Move | Where |
|---|---|---|
| TM08 | Body Slam | S.S. Anne (**missable**) |
| TM24 | Thunderbolt | Surge prize |
| TM13 | Ice Beam | Celadon roof |
| TM26 | Earthquake | Silph |
| TM29 | Psychic | Mr. Psychic, Saffron |
| TM06 | Toxic | Koga prize |
| TM38 | Fire Blast | Blaine prize |
| TM01 / TM05 | Mega Punch / Mega Kick | Mt. Moon / Victory Road (also buyable) |
| TM03 | Swords Dance | Silph |
| TM45 | Thunder Wave | Nugget Bridge |

Celadon 2F sells a subset infinitely (Mega Punch, etc.) — bag presence is not a one-way bit.

### Gyms (map id + beat event + badge bit)

| Gym | Map | Badge bit | Beat event |
|---|---|---|---|
| Pewter / Brock | `$36` | 0 | `EVENT_BEAT_BROCK` |
| Cerulean / Misty | `$41` | 1 | `EVENT_BEAT_MISTY` |
| Vermilion / Surge | `$5C` | 2 | `EVENT_BEAT_LT_SURGE` |
| Celadon / Erika | `$86` | 3 | `EVENT_BEAT_ERIKA` |
| Fuchsia / Koga | `$9D` | 4 | `EVENT_BEAT_KOGA` |
| Saffron / Sabrina | `$B2` | 5 | `EVENT_BEAT_SABRINA` |
| Cinnabar / Blaine | `$A6` | 6 | `EVENT_BEAT_BLAINE` |
| Viridian / Giovanni | `$2D` | 7 | `EVENT_BEAT_VIRIDIAN_GYM_GIOVANNI` |

Viridian Gym is locked until `EVENT_VIRIDIAN_GYM_OPEN` (after Cinnabar / Earth-badge path). Do not confuse hideout Giovanni (`EVENT_BEAT_ROCKET_HIDEOUT_GIOVANNI`) or Silph Giovanni (`EVENT_BEAT_SILPH_CO_GIOVANNI`) with the gym.

Route 23 badge checks: `EVENT_PASSED_*BADGE_CHECK` (Cascade through Earth). Earth check is the Victory Road gate.

### Important maps (Frozen metadata keyed by `wCurMap`)

Tag each map with `{gym, hm, key_item, legendary, e4, required_npc, safari, ship, puzzle}`:

- Oak's Lab `$28`, Bill `$58`, SS Anne `$5F–$68` (captain `$65`), Vermilion Dock `$5E`
- Rocket Hideout `$C7–$CB`, Pokémon Tower `$8E–$94`, Silph `$B5,$CF–$D5,$E9–$EC`
- Safari `$9C,$D9–$E1` (Secret House `$DE` = HM03)
- Power Plant `$53` (Zapdos), Seafoam `$C0,$9F–$A2` (Articuno), Mansion `$A5,$D6–$D8` (Moltres is Victory Road 2 `$C2`)
- E4: Lorelei `$F5`, Bruno `$F6`, Agatha `$F7`, Lance `$71`, Champion `$78`, HOF `$76`
- Snorlax: Route 12 `$17`, Route 16 `$1B`

v2 `essential_map_locations` is a 15-id toy list (Pallet→Mt. Moon). Replace with this tagging table.

### Rival fights (script or event)

Lab, Route 22 (twice), Cerulean, SS Anne (script byte), Pokémon Tower, Silph, Champion. Several have `EVENT_BEAT_*`; SS Anne does not.

---

## What other gyms already do (steal these)

**pokerl** (beat the game): screen + visited mask, map id, blackout map, bag ids+qty (20), party 6×11, 2560 events, facing, battle condition, Safari steps, plus the four extra-event bits. Human-like rule: no enemy moves, no DVs. Reward: required items, required events, map-specific exploration gates (don't boost Tower until Silph Scope; don't boost Route 23 until all badges).

**pokemonred_puffer**: same extra bits; `taught_cut`; cut-tile/cut-coord rewards; menu-seen rewards (start/party/stats/bag) because agents never teach HM; `wSSAnne2FCurScript`; missable flags; required-event subset; symbol-based reads (`pyboy.symbol_lookup`).

**pokegym / boey obs**: bag, party types/moves/PP/HP, enemy battle species/types, last-10 maps/coords, last-10 events, HM-in-bag vs HM-known, bag-full, visited Pokécenters, swap-mon menu (`0xD07D`).

v2 is the *least* RAM-rich of the four. The auto researcher cannot outperform puffer/pokerl rewards if the env hides the channels those rewards used.

---

## Suggested Frozen snapshot (concrete)

Expose a Dict (or a struct the Editable file can slice):

```
mode:            wIsInBattle
map_id, x, y, facing, walk_bike_surf
blackout_map, map_pal_offset
badges:          8 bits
events:          2560 bits (0xD747–0xD886)
extra_events:    rival3, lapras, saffron_drink, game_corner_rocket
status_flags1:   strength_active, surf_allowed, rods, drink
party:           6 × {species, hp, maxhp, level, status, type1, type2, moves[4], pp[4]}
party_knows_hm:  5 bits
bag_ids[20], bag_qty[20]
bag_has_required: ~15 bits (parcel, ticket, HMs, keys, flute, scope, teeth, …)
dex_owned[151], dex_seen[151]
battle:          enemy+player battle_struct + statuses + damage_mult + trainer_class  (zeros if not in battle)
safari_steps, safari_balls
toggleable_object_flags[256]
hidden_items_flags
script_bytes[wGameProgressFlags]     # or at least wSSAnne2FCurScript
play_time                            # telemetry
map_tags                             # Frozen ROM table[map_id]
```

Default policy selection can stay v2-shaped. Reward selection should start from puffer's required-events + required-items + taught-HM + extra-events, not from event popcount.

---

## Score vs training reward (do not conflate)

Frozen Score (spec D5) should stay: badges, event *count or curated subset*, dex, unique maps, capped level-sum. Money, healing, exploration, coins, Safari balls, PP — training-only.

If Score is switched from "all event bits" to a curated `REQUIRED_EVENTS` list, version the formula (spec D12). The museum-ticket exclusion stays.

---

## v3 `ram_map.py` snapshot is too high

`v3/frozen/ram_map.py` already freezes Score/telemetry addresses and a dump window `SNAPSHOT_BASE = 0xD163` … `0xDA45` (2275 bytes). That window **does** include party, bag, dex, badges, map/coords, toggleables, script bytes, status flags, events, enemy *party*, play clock.

It **does not** include the battle/UI block the researcher needs for fights and Cut:

| Symbol | Addr | Why it is outside the snapshot |
|---|---|---|
| `wSpritePlayerStateData1FacingDirection` | `0xC109` | facing |
| `wMenuItemToSwap` / `wPlayerMonNumber` | `0xCC35` / `0xCC2F` | party swap / active slot |
| `wCurrentMenuItem` | `0xCC26` | Fight/bag/mon/run |
| `wFieldMoves` | `0xCD3D` | field-move menu |
| `wCutTile` | `0xCD4D` | Cut just used (pokegym: `== 61`) |
| `wActionResultOrTookBattleTurn` | `0xCD6A` | turn result |
| `wJoyIgnore` | `0xCD6B` | scripted lock |
| `wIsInBattle` | `0xD057` | mode (also missing from snapshot!) |
| `wEnemyMon` / `wBattleMon` | `0xCFE5` / `0xD014` | **active** combatants |
| `wDamageMultipliers` | `0xD05B` | type effectiveness after a hit |
| `wPlayerBattleStatus*` | `0xD062` | Wrap / Fly / confuse |
| `hWhoseTurn` | `0xFFF3` | HRAM |

Fix: either lower `SNAPSHOT_BASE` to `0xC100` (or at least `0xCC00`) **and** append HRAM `hWhoseTurn`, or keep the D163 window for Score and add a second Frozen “battle/UI” slice. Do not assume the current 2275-byte blob is a complete researcher surface.

`wIsInBattle` is already a named constant in that file; it is simply not inside `SNAPSHOT_*`.

---

## Signals that are not RAM (hooks)

puffer/pokerl get several high-value rewards from **PyBoy execution hooks**, not WRAM: start/party/stats/bag menus opened, `UsedCut`, Poké Flute success, Surf attempt, warps, signs, hidden objects, NPC text, ball use, healing machine. Those never appear as monotonic bits.

MUST for the Frozen env: either (a) hook the same pret functions and expose counters in the snapshot, or (b) document that `train.py` cannot invent “taught Cut by using it on a tree” without them.

pokegym’s distinctive Cut FSM polls `wTileInFrontOfPlayer` (`0xCFC6`), `wCutTile` (`0xCD4D`), facing `0xC109`, and a few volatile UI bytes. Prefer puffer’s `UsedCut` hook plus `wCutTile`; do not copy pokegym’s `0xCCD5` as “battle turns” — in pokered that address is `wAILayer2Encouragement`.

---

## Reward-shaping ideas to expose as labeled channels

Already proven in puffer/pokegym; Frozen should make the *inputs* available:

- **Named required-event subset** (~60) + four extra-event bits, not raw popcount.
- **Required / useful item bag bits** (puffer `REQUIRED_ITEMS`).
- **Story-gated exploration** (`MAP_ID_COMPLETION_EVENTS`: don’t boost Tower until Silph Scope; don’t boost Route 23 until all badges). This is Frozen map metadata × current flags.
- **Tileset-bucketed explore** (`wCurMapTileset` `0xD367`).
- **HM teach vs use:** `party_knows_hm` + cut/surf/flute *valid vs invalid* coord sets (hooks).
- **Menu discovery** (start/bag/party) — puffer had to reward opening the bag so agents would teach Cut.
- **Visited mask** as a screen-shaped obs channel (pokerl), in addition to v2’s 48×48 crop.
- Weighted event graph (pokegym: gym leader ×5, HM ×5, Snorlax ×10, Fighting Dojo completion **negative**). That weighting belongs in Editable reward, not Frozen Score.

Additional named events to alias: `EVENT_GOT_NUGGET`, `EVENT_GOT_EXP_ALL`, `EVENT_IN_SAFARI_ZONE`, `EVENT_SAFARI_GAME_OVER`.

---

## Open items / questions

1. **Enemy moves in the policy obs?** pokerl said no (human-like). Battle competence almost certainly wants them in the *RAM bundle* even if the default policy omits them.
2. **Curated event mask vs full 2560 bits in the policy.** Full bitfield is what v2/pokerl use; a Frozen named subset (puffer `REQUIRED_EVENTS`) is better for *reward*. Recommend both: full bits in the bundle, named aliases for the ~80 story flags.
3. **PyBoy symbol_lookup** (`wPartyMon1Level`) vs hardcoded addresses. Symbols survive pokered refactors; v2 hardcodes. Frozen ram map should store *both* symbol and `pokered.sym` address.
4. Tea does not exist in Red/Blue. If anyone copies a Yellow walkthrough, they will look for the wrong item.

No blocker: every MUST address above is in `pokered.sym` and `wram.asm`.
