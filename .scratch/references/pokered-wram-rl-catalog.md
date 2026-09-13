# pret/pokered WRAM catalog (RL)

Source: explorer pass over `~/dev/pokered/` (`pokered.sym`, `ram/wram.asm`, `ram/hram.asm`, `macros/ram.asm`, `constants/*.asm`). Saved 2026-09-13.

Gym-facing MUST/SHOULD/COULD (v3 env + train.py): `v3-obs-ram-catalog.md` and `v3-obs-ram-map.json`. This file is the denser ground-truth dump.

Addresses resolved from `pokered.sym` (built ROM).

**Legend:** MUST / SHOULD / COULD = RL priority for obs and/or reward.

**Encoding notes:** little-endian words; money/coins often BCD; `$50` string terminator; species = internal index (not National Dex #); bag/PC lists are `(item_id, qty)` pairs terminated by `$FF`.

---

## 0. Struct layouts (stride / offsets)

### Party / box mon (`macros/ram.asm`, `constants/pokemon_data_constants.asm`)

| Offset | Field | Size | Notes |
|--------|-------|------|-------|
| `$00` | Species | 1 | Internal ID |
| `$01` | HP | 2 | Current HP |
| `$03` | BoxLevel / PartyPos* | 1 | Box: level; battle_struct: party index |
| `$04` | Status | 1 | SLP 0–7 in bits 0–2; PSN/BRN/FRZ/PAR bits 3–6 (`battle_constants.asm`) |
| `$05` | Type1 | 1 | |
| `$06` | Type2 | 1 | Same as Type1 if mono |
| `$07` | Catch rate | 1 | Overwritten with held item in later gens; Gen1 catch rate |
| `$08` | Moves | 4 | Move IDs |
| `$0C` | OT ID | 2 | |
| `$0E` | Exp | 3 | Big-endian |
| `$11` | HP/Atk/Def/Spd/Spc Exp | 2×5 | EVs |
| `$1B` | DVs | 2 | Atk/Def \| Spd/Spc nybbles |
| `$1D` | PP | 4 | Bits 0–5 remaining; 6–7 PP Ups (`PP_MASK`/`PP_UP_MASK`) |
| **`$21`** | **BOXMON_STRUCT_LENGTH** | | |
| `$21` | Level | 1 | Party only |
| `$22` | MaxHP, Atk, Def, Spd, Spc | 2×5 | Party only |
| **`$2C`** | **PARTYMON_STRUCT_LENGTH** | | |

\*In `battle_struct`, offset `$03` is `PartyPos` (not level); level is at `$0E` after DVs.

### Battle mon (`battle_struct`) — `$1C` bytes used in RAM labels

| Offset | Field |
|--------|-------|
| `$00` Species, `$01` HP(2), `$03` PartyPos, `$04` Status, `$05–6` Types, `$07` CatchRate, `$08–B` Moves, `$0C–D` DVs, `$0E` Level, `$0F–18` Stats (MaxHP…Spc), `$19–1C` PP |

### Party block (`wPartyDataStart` `$D163`)

| Symbol | Addr | Size |
|--------|------|------|
| `wPartyCount` | `$D163` | 1 |
| `wPartySpecies` | `$D164` | 7 (6 + `$FF`) |
| `wPartyMons` / `wPartyMon1`…`6` | `$D16B` | 6 × `$2C` |
| `wPartyMonOT` | `$D273` | 6 × 11 |
| `wPartyMonNicks` | `$D2B5` | 6 × 11 |
| End | `$D2F7` | |

Party mon *n* base = `$D16B + (n-1)*$2C`. Levels: `$D18C,$D1B8,$D1E4,$D210,$D23C,$D268`. HP: `$D16C+…`. MaxHP: `$D18D+…`.

### Current box (`wBoxDataStart` `$DA80`)

| Symbol | Addr | Size |
|--------|------|------|
| `wBoxCount` | `$DA80` | 1 |
| `wBoxSpecies` | `$DA81` | 21 |
| `wBoxMons` | `$DA96` | 20 × `$21` |
| `wBoxMonOT` | `$DD2A` | 20 × 11 |
| `wBoxMonNicks` | `$DE06` | 20 × 11 |
| End | `$DEE2` | |

Only **current** box is in WRAM; other boxes live in SRAM (not WRAM).

### Event flags

`NUM_EVENTS = $A00` (2560) → **320 bytes** at `wEventFlags` `$D747`…`$D886` (next is `wGrassRate` `$D887`).

Bit *n* → byte `n//8`, bit `n%8` (low bit = bit 0).

---

## 1. Player position, map, facing, warps

| Name | Addr | Size / enc | Meaning | RL | Source | Caveats |
|------|------|------------|---------|-----|--------|---------|
| `wCurMap` | `$D35E` | u8 map id | Current map (`map_constants.asm`, `NUM_MAPS`) | **MUST** obs+reward | `wram.asm` | Indoor/outdoor share one byte; use with coords |
| `wYCoord` / `wXCoord` | `$D361` / `$D362` | u8 tile | Player tile coords | **MUST** | `wram.asm` | Not screen pixels |
| `wYBlockCoord` / `wXBlockCoord` | `$D363` / `$D364` | u8 | 2×2-block coords | COULD | | |
| `wPlayerDirection` | `$D52A` | bitfield | Facing/moving dir (`PLAYER_DIR_*`) | **MUST** obs | `sprite_data_constants.asm` | |
| `wPlayerMovingDirection` | `$D528` | u8 | Dir while moving; 0 if still | SHOULD | | Scripts write to force facing |
| `wPlayerLastStopDirection` | `$D529` | u8 | Last stop dir | COULD | | |
| `wSpritePlayerStateData1FacingDirection` | `$C109` | `$00/$04/$08/$0C` | Sprite facing | SHOULD | `SPRITE_FACING_*` | Volatile during anim |
| `wSpritePlayerStateData1YPixels/XPixels` | `$C104`/`$C106` | u8 | Screen pixel pos | COULD | | Animation jitter |
| `wSpritePlayerStateData2MapY/MapX` | `$C204`/`$C205` | u8 | Map grid (offset +4) | COULD | | Redundant w/ wY/XCoord |
| `wLastMap` | `$D365` | u8 | Previous map | SHOULD | | Warp/backtracking |
| `wCurMapTileset` | `$D367` | u8 | Tileset id; bit7 = no previous map | SHOULD | `ram_constants.asm` | Flash darkness via `wMapPalOffset` |
| `wCurMapHeight` / `Width` | `$D368`/`$D369` | u8 | Map size in blocks | SHOULD | | Bound exploration |
| `wCurMapConnections` | `$D370` | bitfield | EAST/WEST/SOUTH/NORTH | SHOULD | `map_data_constants.asm` | |
| `wNorth/South/West/EastConnectionHeader` | `$D371`… | 11 B each | Connected map + strip ptrs | COULD | | Mostly ROM-derived |
| `wNumberOfWarps` | `$D3AE` | u8 ≤32 | Warp count | SHOULD | | |
| `wWarpEntries` | `$D3AF` | 32×(Y,X,warpId,mapId) | Warp table | SHOULD obs / COULD reward | | Map-local; changes on load |
| `wDestinationWarpID` | `$D42F` | u8 | `$FF` = don’t update coords | COULD | | |
| `wWarpedFromWhichWarp` / `Map` | `$D73B`/`$D73C` | u8 | Last warp source | COULD | | |
| `wDestinationMap` | `$D71A` | u8 | Special warp dest (Fly etc.) | COULD | | Transient |
| `wDungeonWarpDestinationMap` / `wWhichDungeonWarp` | `$D71D`/`$D71E` | u8 | Dungeon warp | COULD | Seafoam/Victory | |
| `wStandingOnWarpPadOrHole` | `$CD5B` | 0/1/2 | Pad vs hole | COULD | | |
| `wMovementFlags` | `$D736` | bits | Door/warp/ledge/spin | SHOULD | `BIT_STANDING_ON_WARP` etc. | |
| `wTileInFrontOfPlayer` | `$CFC6` | u8 | BG tile ahead | SHOULD | Collision/Cut/Surf probes | Volatile |
| `wTilePlayerStandingOn` | `$CF0E` | u8 | Current tile | SHOULD | | |
| `wTilesetCollisionPtr` | `$D530` | ptr | Walkable tile list (ROM bank) | COULD meta | Pointer only; table in ROM | |
| `wOverworldMap` | `$C6E8` | 1300 B | Block map buffer | COULD | Heavy; union w/ pic | |
| `wMapPalOffset` | `$D35D` | u8 | 6 when Flash needed (dark) | **MUST** cave/Flash | | |

**Frozen metadata (ROM):** gym maps, connections, collision — key by `wCurMap` from `map_constants.asm` / headers under `data/maps/`.

---

## 2. Badges & high-level progress

| Name | Addr | Enc | Meaning | RL | Source | Caveats |
|------|------|-----|---------|-----|--------|---------|
| `wObtainedBadges` | `$D356` | 8 bits | Boulder…Earth (`BIT_*BADGE`) | **MUST** | `ram_constants.asm` | Monotonic; primary progress |
| `wBeatGymFlags` | `$D72A` | 8 bits | Redundant copy of badges | COULD | Comment: matches badges | Prefer `$D356` |
| `wNumHoFTeams` | `$D5A2` | u8 | Hall of Fame entries | **MUST** endgame | | |

Badge → field HM gate (ROM rules, not a RAM table): Boulder Flash, Cascade Cut, Thunder Fly, Rainbow Strength, Soul Surf.

---

## 3. Event flags (`wEventFlags` `$D747`, 320 B)

| Name | Addr | Enc | Meaning | RL | Source | Caveats |
|------|------|-----|---------|-----|--------|---------|
| `wEventFlags` | `$D747` | 2560 bits | Story, trainers, items, puzzles | **MUST** | `event_constants.asm` | Sparse; many trainer bits farmable once |
| `NUM_EVENTS` | — | `$A00` | Array length | | | |

Your env already scrapes `$D747`…; full range ends at `$D886` (env’s `$D87E` truncates Articuno/late flags).

### Major `EVENT_*` (bit index → `$D747 + bit//8`, bit `bit%8`)

| Event | Bit | Byte.bit | RL role |
|-------|-----|----------|---------|
| `EVENT_HALL_OF_FAME_DEX_RATING` | `$003` | `$D747.3` | Post-HoF |
| `EVENT_GOT_TOWN_MAP` | `$018` | `$D74A.0` | Quest |
| `EVENT_GOT_STARTER` | `$022` | `$D74B.2` | **MUST** |
| `EVENT_BATTLED_RIVAL_IN_OAKS_LAB` | `$023` | `$D74B.3` | |
| `EVENT_GOT_POKEBALLS_FROM_OAK` | `$024` | `$D74B.4` | |
| `EVENT_GOT_POKEDEX` | `$025` | `$D74B.5` | **MUST** |
| `EVENT_VIRIDIAN_GYM_OPEN` | `$028` | `$D74C.0` | Earth Badge gate |
| `EVENT_GOT_OAKS_PARCEL` / `EVENT_OAK_GOT_PARCEL` | `$039`/`$038` | `$D74E` | Parcel quest |
| `EVENT_BEAT_VIRIDIAN_GYM_GIOVANNI` | `$051` | `$D751.1` | 8th gym |
| `EVENT_BOUGHT_MUSEUM_TICKET` | `$068` | `$D754.0` | Missable path |
| `EVENT_GOT_OLD_AMBER` | `$069` | `$D754.1` | Fossil |
| **`EVENT_BEAT_BROCK`** | `$077` | `$D755.7` | **MUST** |
| `EVENT_BEAT_CERULEAN_RIVAL` | `$098` | `$D75A.0` | |
| **`EVENT_BEAT_MISTY`** | `$0BF` | `$D75E.7` | **MUST** |
| `EVENT_GOT_BICYCLE` | `$0C0` | `$D75F.0` | |
| `EVENT_BEAT_POKEMON_TOWER_RIVAL` | `$0F1` | `$D765.1` | |
| `EVENT_BEAT_GHOST_MAROWAK` | `$111` | `$D769.1` | Needs Scope |
| `EVENT_GOT_POKE_FLUTE` | `$12A` | `$D76C.2` | Snorlax |
| `EVENT_GOT_BIKE_VOUCHER` | `$151` | `$D771.1` | |
| **`EVENT_BEAT_LT_SURGE`** | `$167` | `$D773.7` | **MUST** |
| **`EVENT_BEAT_ERIKA`** | `$1A9` | `$D77C.1` | **MUST** |
| `EVENT_FOUND_ROCKET_HIDEOUT` | `$1B9` | `$D77E.1` | |
| `EVENT_GOT_COIN_CASE` | `$1E0` | `$D783.0` | |
| `EVENT_GOT_HM04` (Strength) | `$238` | `$D78E.0` | Safari warden |
| `EVENT_GAVE_GOLD_TEETH` | `$239` | `$D78E.1` | |
| `EVENT_IN_SAFARI_ZONE` / `SAFARI_GAME_OVER` | `$24F`/`$24E` | `$D790` | Episode |
| **`EVENT_BEAT_KOGA`** | `$259` | `$D792.1` | **MUST** |
| `EVENT_MANSION_SWITCH_ON` | `$278` | `$D796.0` | Puzzle |
| **`EVENT_BEAT_BLAINE`** | `$299` | `$D79A.1` | **MUST** |
| `EVENT_GAVE_FOSSIL_TO_LAB` | `$2E0` | `$D7A3.0` | |
| `EVENT_DEFEATED_FIGHTING_DOJO` | `$350` | `$D7B1.0` | Exclusive Hitmon |
| `EVENT_GOT_HITMONLEE/CHAN` | `$356`/`$357` | `$D7B1` | Mutual exclusive |
| **`EVENT_BEAT_SABRINA`** | `$361` | `$D7B3.1` | **MUST** |
| `EVENT_GOT_HM05` (Flash) | `$3D8` | `$D7C2.0` | Route 2 |
| `EVENT_BEAT_ZAPDOS` | `$469` | `$D7D4.1` | Legendary |
| `EVENT_GOT_ITEMFINDER` | `$47F` | `$D7D6.7` | |
| `EVENT_FIGHT/BEAT_ROUTE12_SNORLAX` | `$48E`/`$48F` | `$D7D8` | Flute |
| `EVENT_GOT_EXP_ALL` | `$4B0` | `$D7DD.0` | |
| `EVENT_FIGHT/BEAT_ROUTE16_SNORLAX` | `$4C8`/`$4C9` | `$D7E0` | |
| `EVENT_GOT_HM02` (Fly) | `$4CE` | `$D7E0.6` | |
| `EVENT_RESCUED_MR_FUJI` | `$4CF` | `$D7E0.7` | |
| `EVENT_IN_SEAFOAM_ISLANDS` | `$500` | `$D7E7.0` | |
| Route22 rival 1st/2nd + beat flags | `$520`–`$526` | `$D7EB` | |
| Route23 badge checks | `$530`–`$536` | `$D7ED` | Victory Road gate |
| `EVENT_BEAT_MOLTRES` | `$53E` | `$D7EE.6` | |
| `EVENT_GOT_SS_TICKET` | `$55C` | `$D7F2.4` | Bill |
| `EVENT_GOT_DOME/HELIX_FOSSIL` | `$57E`/`$57F` | `$D7F6` | Exclusive |
| **`EVENT_GOT_HM01` (Cut)** | `$5E0` | `$D803.0` | SS Anne |
| `EVENT_RUBBED_CAPTAINS_BACK` | `$5E1` | `$D803.1` | |
| **`EVENT_SS_ANNE_LEFT`** | `$5E2` | `$D803.2` | **MUST** missable lock |
| `EVENT_ENTERED_ROCKET_HIDEOUT` | `$677` | `$D815.7` | |
| `EVENT_ROCKET_DROPPED_LIFT_KEY` | `$6A6` | `$D81B.6` | Key item via event |
| `EVENT_BEAT_ROCKET_HIDEOUT_GIOVANNI` | `$6A7` | `$D81B.7` | |
| Silph door unlocks / rival / Giovanni | `$6F0`… | `$D82x`–`$D838` | Card Key puzzles |
| `EVENT_GOT_MASTER_BALL` | `$78D` | `$D838.5` | |
| `EVENT_BEAT_SILPH_CO_GIOVANNI` | `$78F` | `$D838.7` | |
| `EVENT_GOT_HM03` (Surf) | `$880` | `$D857.0` | Safari secret |
| `EVENT_BEAT_MEWTWO` | `$8C1` | `$D85F.1` | |
| Elite Four / Lance / Champion | `$8E0`–`$907` | `$D863`–`$D867` | **MUST** endgame |
| `EVENT_BEAT_ARTICUNO` | `$9DA` | `$D882.2` | Needs full flag range |

**Trainer-defeated:** hundreds of `EVENT_BEAT_*_TRAINER_*` — good dense progress if you want; not monotonic vs story if you skip trainers.

**Hidden objects:** `wObtainedHiddenItemsFlags` `$D6F0` (112 bits), `wObtainedHiddenCoinsFlags` `$D6FE` (16 bits) — SHOULD one-shot rewards; farmable only once each.

**Toggleable map objects** (item balls, etc.): `wToggleableObjectFlags` `$D5A6` (256 bits / 32 B) — SHOULD.

---

## 4. Party (obs + reward)

| Name | Addr | Enc | RL | Caveats |
|------|------|-----|-----|---------|
| `wPartyCount` | `$D163` | 0–6 | **MUST** | |
| `wPartySpecies` | `$D164` | IDs + `$FF` | **MUST** | Internal IDs |
| Per-mon species/HP/status/types/moves/PP/level/stats/exp/DVs/catch | `$D16B+` | see §0 | **MUST** | HP farmable via Center |
| Nicks / OT | `$D2B5` / `$D273` | strings | COULD | |
| `wPlayerStarter` / `wRivalStarter` | `$D717` / `$D715` | species | SHOULD | Rival teams |

**Derived (not raw RAM):** type chart from ROM `data/types/type_matchups.asm` (`TypeEffects`); base stats/learnsets from ROM base data — expose as frozen tables keyed by species.

**Field moves known:** scan party `Moves` for Cut `$0F`, Fly `$13`, Surf `$39`, Strength `$46`, Flash `$94` (`move_constants.asm`). Temp menu buffer `wFieldMoves` (union ~`$CD3x`) is **volatile**.

---

## 5. Boxes / PC / Daycare

| Name | Addr | RL | Caveats |
|------|------|-----|---------|
| `wCurrentBoxNum` | `$D5A0` | SHOULD | Bits 0–6 box #; bit7 changed-boxes |
| Current box mons | `$DA80`… | SHOULD | Other boxes = SRAM |
| `wDayCareInUse` | `$DA48` | SHOULD | 0/1 |
| `wDayCareMon*` | `$DA49`… | COULD | Gains levels while stored (ROM/time) |
| `wBoxMonCounts` | union temp | COULD | Transient |

---

## 6. Inventory, money, coins, key items, HM/TM

| Name | Addr | Enc | RL | Caveats |
|------|------|-----|-----|---------|
| `wNumBagItems` | `$D31D` | u8 | **MUST** | |
| `wBagItems` | `$D31E` | ≤20×(id,qty)+`$FF` | **MUST** | Key items qty usually 1 |
| `wPlayerMoney` | `$D347` | 3 BCD | SHOULD | Farmable (Pay Day, trainers) |
| `wNumBoxItems` / `wBoxItems` | `$D53A`/`$D53B` | ≤50 slots | COULD | PC item storage |
| `wPlayerCoins` | `$D5A4` | 2 BCD | COULD | Game Corner |
| `wIsKeyItem` | `$D124` | flag | COULD | Transient check |
| `wBoostExpByExpAll` | `$CC5B` | u8 | SHOULD if Exp.All owned | Union alias `wUnusedFlag` |

**Key item IDs** (`item_constants.asm`) — detect in bag (no Tea in Red; Saffron uses drinks + `BIT_GAVE_SAFFRON_GUARDS_DRINK`):

| Item | ID | Typical gate |
|------|-----|----------------|
| TOWN_MAP | `$05` | Navigation |
| BICYCLE | `$06` | Speed / bike roads |
| POKEDEX | `$09` | (also event) |
| OLD_AMBER / DOME / HELIX | `$1F/$29/$2A` | Fossils |
| SECRET_KEY | `$2B` | Cinnabar Gym |
| BIKE_VOUCHER | `$2D` | → Bicycle |
| CARD_KEY | `$30` | Silph doors |
| S_S_TICKET | `$3F` | SS Anne (**missable after leave**) |
| GOLD_TEETH | `$40` | → HM04 |
| COIN_CASE | `$45` | Slots |
| OAKS_PARCEL | `$46` | Early quest |
| SILPH_SCOPE | `$48` | Tower ghosts |
| POKE_FLUTE | `$49` | Snorlax |
| LIFT_KEY | `$4A` | Hideout elevator |
| EXP_ALL | `$4B` | |
| HM_CUT…FLASH | `$C4`–`$C8` | Ownership ≠ usable |
| TM01–TM50 | `$C9`–`$FA` | |

**HM usable in field** needs: (1) HM in bag OR move on party, (2) correct badge, (3) correct context tile/map. Reward on “can Cut/Surf/…” derived signal beats raw HM bit alone.

---

## 7. Pokédex

| Name | Addr | Size | RL | Caveats |
|------|------|------|-----|---------|
| `wPokedexOwned` | `$D2F7` | 19 B (151 bits) | **MUST**/SHOULD | National order; `NUM_POKEMON=151` |
| `wPokedexSeen` | `$D30A` | 19 B | SHOULD | Seen ≥ Owned usually |

---

## 8. Battle state

| Name | Addr | Enc | RL | Caveats |
|------|------|-----|-----|---------|
| `wIsInBattle` | `$D057` | 0 / 1 wild / 2 trainer / `$FF` lost | **MUST** | |
| `wBattleType` | `$D05A` | 0 normal / 1 old man / 2 safari | SHOULD | |
| `wCurOpponent` | `$D059` | species or trainer+`OPP_ID_OFFSET`(200) | **MUST** | |
| `wTrainerClass` / `wTrainerName` | `$D031` / `$D04A` | | SHOULD | |
| `wGymLeaderNo` | `$D05C` | | SHOULD | Alias `wLoneAttackNo` |
| `wCurEnemyLevel` | `$D127` | | **MUST** | |
| `wEnemyMon`… | `$CFE5` | battle_struct | **MUST** | Battle-only valid |
| `wBattleMon`… | `$D014` | battle_struct | **MUST** | Active player mon |
| `wEnemyMonNick` / `wBattleMonNick` | `$CFDA` / `$D009` | | COULD | |
| `wEnemyPartyCount` / `wEnemyMons` | `$D89C` / `$D8A4` | party_structs | **MUST** trainers | **Union** with wild grass/water data |
| `wDamageMultipliers` | `$D05B` | bits0–6 effectiveness×10; bit7 STAB | **MUST** battle obs | Per last calc; `$0/$5/$A/$14` |
| `wTypeEffectiveness` | `$D11E` | temp | COULD | Overloaded union |
| `wPlayerMove*` / `wEnemyMove*` | `$CFD2` / `$CFCC` | anim,effect,power,type,acc,pp | SHOULD | Selected move data |
| `wPlayerSelectedMove` / Enemy | `$CCDC`/`$CCDD` | move id | SHOULD | |
| `hWhoseTurn` | `$FFF3` | 0 player / 1 enemy | **MUST** | HRAM |
| `wPlayerBattleStatus1–3` | `$D062`–`$D064` | Bide/thrash/flinch/… | SHOULD | `battle_constants.asm` |
| `wEnemyBattleStatus1–3` | `$D067`–`$D069` | | SHOULD | |
| `wBattleResult` | `$CF0B` | 0 win / 1 lose / 2 draw | SHOULD | |
| `wEscapedFromBattle` | `$D078` | | COULD | |
| `wSafariEscapeFactor` / `BaitFactor` | `$CCE8`/`$CCE9` | | SHOULD safari | |
| `wPartyGainExpFlags` | `$D058` | bit per mon | COULD | |
| `wLowHealthAlarm` | `$D083` | | COULD | |
| `wActionResultOrTookBattleTurn` | `$CD6A` | item/switch used | SHOULD | Masks move that turn |
| `wLinkState` | `$D12B` | link mode | COULD / ignore | |
| `wCriticalHitOrOHKO` / `wMoveMissed` | `$D05E`/`$D05F` | | COULD | Momentary |
| `wDamage` | `$D0D7` | u16 | COULD | Last damage |
| `wMonHeader` | `$D0B8` | base stats copy | COULD | Filled on demand |
| `wEngagedTrainerClass/Set` | `$CD2D`/`$CD2E` | overworld engage | SHOULD | Union volatile |

**Type matchups:** ROM only (`data/types/type_matchups.asm`). In-battle effectiveness already in `wDamageMultipliers`.

---

## 9. Overworld vs menu vs battle vs text

| Signal | Addr | How to use | RL |
|--------|------|------------|-----|
| Battle | `wIsInBattle≠0` | Battle mode | **MUST** |
| Text / scripted input | `wJoyIgnore` `$CD6B`, `wSimulatedJoypadStatesIndex` `$CD38`, `BIT_DISABLE_JOYPAD` in `wStatusFlags5` | Soft-lock / forced walks | **MUST** |
| Text box | `wTextBoxID` `$D125`, `wAutoTextBoxDrawingControl` `$CF0C`, `hWY` `$FFB0` | Dialog up if WY moved | SHOULD |
| Menu | `wCurrentMenuItem` `$CC26`, `wMaxMenuItem`, `wListScrollOffset`, `wMenuExitMethod` | UI state | SHOULD |
| Font loaded (overworld paused) | `wFontLoaded` `$CFC4` bit0 | NPCs frozen | SHOULD |
| Start/bag/battle menu cursors | `$CC2B`–`$CC2D` | | COULD |
| `wMiscFlags` | `$CD60` | trainer sight, boulder, PC | SHOULD |
| `wStatusFlags5` bit7 | scripted movement | | SHOULD |
| `wOutOfBattleBlackout` | `$D12D` | party wipe poison etc. | SHOULD |
| `wUpdateSpritesEnabled` | `$CFCB` | | COULD |

---

## 10. Play time

| Name | Addr | RL | Caveats |
|------|------|-----|---------|
| `wPlayTimeHours/Maxed/Minutes/Seconds/Frames` | `$DA41`–`$DA45` | COULD curriculum | Counts when `BIT_GAME_TIMER_COUNTING` (`wStatusFlags6`) |

---

## 11. Gyms / maps (ROM metadata + RAM flags)

| Gym | Map const (id) | Beat event | Badge bit |
|-----|----------------|------------|-----------|
| Brock | `PEWTER_GYM` `$36` | `EVENT_BEAT_BROCK` | Boulder 0 |
| Misty | `CERULEAN_GYM` `$41` | `EVENT_BEAT_MISTY` | Cascade 1 |
| Surge | `VERMILION_GYM` `$5C` | `EVENT_BEAT_LT_SURGE` | Thunder 2 |
| Erika | `CELADON_GYM` `$86` | `EVENT_BEAT_ERIKA` | Rainbow 3 |
| Koga | `FUCHSIA_GYM` `$9D` | `EVENT_BEAT_KOGA` | Soul 4 |
| Sabrina | `SAFFRON_GYM` `$B2` | `EVENT_BEAT_SABRINA` | Marsh 5 |
| Blaine | `CINNABAR_GYM` `$A6` | `EVENT_BEAT_BLAINE` | Volcano 6 |
| Giovanni | `VIRIDIAN_GYM` `$2D` | `EVENT_BEAT_VIRIDIAN_GYM_GIOVANNI` | Earth 7 |

Elite Four maps: Lorelei/Bruno/Agatha/Lance/Champion/HoF (`map_constants.asm` `$76`–`$78` region). Script indices also in `wGameProgressFlags` `$D5F0`…`$D6B7` (per-map `*CurScript`) — COULD for fine story state; easy to misuse.

---

## 12. Quest / key progress (summary)

| Quest | RAM evidence | Missable? |
|-------|--------------|-----------|
| Parcel | bag `OAKS_PARCEL` + events `$038/$039` | No |
| Pokédex | event `$025` + item `$09` | No |
| Town Map | event `$018` / item `$05` | No |
| SS Ticket → Anne → HM01 | events `$55C`, `$5E0`, **`$5E2` left** | **Yes — Anne leaves** |
| Bike voucher → bike | `$151`, `$0C0` | No |
| Silph Scope | bag `$48` (hideout) | No |
| Poké Flute | `$12A` after Fuji | No |
| Snorlax | fight/beat Route12/16 events | Flute required |
| Card Key / Silph | bag `$30` + door events | No |
| Lift Key | event `$6A6` / item `$4A` | No |
| Secret Key | bag `$2B` | No |
| Gold Teeth → Strength | `$239` + HM04 | No |
| Fossils | exclusive dome/helix; amber; lab flags | Choice lock |
| Exp.All | `$4B0` / item `$4B` | No |
| Saffron guards | `wStatusFlags1` bit6 drink | No Tea item |
| Safari HM03 | `$880` | Safari episode |
| Fly HM02 | `$4CE` | |
| Flash HM05 | `$3D8` | |
| Legendaries | Zapdos/Moltres/Articuno/Mewtwo beat events | Optional |
| Champion | `$901` + `wNumHoFTeams` | Terminal |

---

## 13. Fly destinations

| Name | Addr | Enc | RL | Caveats |
|------|------|-----|-----|---------|
| `wTownVisitedFlag` | `$D70B` | bit per city (`NUM_CITY_MAPS=11`) | **MUST** | Unlocks Fly targets |
| `wFlyLocationsList` | union ~`$CD3E` | temp list | COULD | Menu-only volatile |

Cities `$00`–`$0A`: Pallet…Saffron (`map_constants.asm`).

---

## 14. Safari / Seafoam / Mansion / VR / Hideout / Silph

| Name | Addr | RL | Notes |
|------|------|-----|-------|
| `wNumSafariBalls` | `$DA47` | SHOULD | |
| `wSafariSteps` | `$D70D` | u16, starts 502 | SHOULD | Counts down |
| `wSafariZoneGameOver` | `$DA46` | SHOULD | |
| `EVENT_IN_SAFARI_ZONE` | bit `$24F` | | |
| Seafoam boulder-down-hole events | `$9C0`… | SHOULD puzzles | |
| `EVENT_MANSION_SWITCH_ON` | `$278` | SHOULD | |
| VR boulder-on-switch events | `$917`, `$660`… | SHOULD | |
| Hideout / Silph door + Giovanni events | §3 | **MUST** mid/late | |
| `wCardKeyDoorY/X` | `$D73F`/`$D740` | COULD | |
| `wFirst/SecondLockTrashCanIndex` | `$D743` | Vermilion gym | COULD | |
| Cinnabar quiz gates | `EVENT_CINNABAR_GYM_GATE*_UNLOCKED` | SHOULD | |

---

## 15. Status flag bytes (movement / story helpers)

| Name | Addr | Important bits | RL |
|------|------|----------------|-----|
| `wStatusFlags1` | `$D728` | Strength active, Surf allowed, rods, Saffron drink | **MUST**/SHOULD |
| `wStatusFlags2` | `$D72C` | Wild encounter cooldown | COULD |
| `wStatusFlags3` | `$D72D` | dungeon warp, talked to trainer | SHOULD |
| `wStatusFlags4` | `$D72E` | Got Lapras, used Center, got starter, no battles, blackout | **MUST** |
| `wStatusFlags5` | `$D730` | disable joypad, scripted move, no text delay | **MUST** UI |
| `wStatusFlags6` | `$D732` | timer, fly/dungeon/escape warp, always bike | SHOULD |
| `wStatusFlags7` | `$D733` | trainer battle bit, used fly | SHOULD |
| `wElite4Flags` | `$D734` | started E4 | SHOULD |
| `wWalkBikeSurfState` | `$D700` | 0 walk / 1 bike / 2 surf | **MUST** |
| `wRepelRemainingSteps` | `$D0DB` | | SHOULD |
| `wLastBlackoutMap` | `$D719` | Pokémon Center respawn map | **MUST** |
| `wStepCounter` | `$D13B` | | COULD |
| `wNumberOfNoRandomBattleStepsLeft` | `$D13C` | post-battle grace | COULD |
| `wCompletedInGameTradeFlags` | `$D737` | u16 | COULD |

---

## 16. Screen / UI / joypad / RNG / audio

| Name | Addr | RL | Caveats |
|------|------|-----|---------|
| `hJoyHeld/Pressed/Released/Last` | `$FFB4`/`$B3`/`$B2`/`$B1` | COULD debug | Not usually obs |
| `wJoyIgnore` | `$CD6B` | **MUST** | |
| `hRandomAdd` / `hRandomSub` | `$FFD3`/`$FFD4` | **Avoid for reward** | Non-stationary |
| `hFrameCounter` | `$FFD5` | COULD | |
| `wSoundID` / music / channels | `$C001`… | **Skip** | High noise |
| `wTileMap` | `$C3A0` | 20×18 tiles | COULD pixels-alt | Heavy |
| `hSCX/SCY/WY` | `$FFAE`–`$FFB0` | SHOULD mode detect | |

---

## 17. Wild encounter tables (current map)

| Name | Addr | Notes | RL |
|------|------|-------|-----|
| `wGrassRate` / `wGrassMons` | `$D887` / `$D888` | Overwritten; **union** with enemy party | SHOULD overworld only |
| `wWaterRate` / `wWaterMons` | `$D8A4` / `$D8A5` | Same union as `wEnemyMons` | Invalid in trainer battle |

---

## 18. Recommended minimal RL observation set

**MUST:** `wCurMap`, `wXCoord`, `wYCoord`, `wPlayerDirection`, `wObtainedBadges`, `wEventFlags` (full 320 B or curated bits), `wPartyCount` + party species/HP/maxHP/level/status/moves, `wIsInBattle` + battle mons when set, `wWalkBikeSurfState`, `wJoyIgnore`/scripted bits, `wTownVisitedFlag`, `wLastBlackoutMap`, bag key items/HMs, `wPokedexOwned` (or popcount).

**SHOULD:** enemy party in trainers, `wDamageMultipliers`, Safari counters, `wRepelRemainingSteps`, `wStatusFlags1/4/5`, warp count, tileset/Flash offset, Fly destinations, hidden-item flags, SS Anne / Snorlax / Silph / E4 event subset.

**COULD:** money, play time, DVs/EVs, box contents, audio, RNG, full tilemap, connection structs.

**Avoid as reward:** raw money, play time alone, RNG, faint-heal cycles without clamps, trainer rematches (N/A in Red), wild grind without story gates.

---

## 19. Source index

| File | Role |
|------|------|
| `/Users/luizfelipegalvaoramos/dev/pokered/ram/wram.asm` | All WRAM labels |
| `/Users/luizfelipegalvaoramos/dev/pokered/ram/hram.asm` | HRAM |
| `/Users/luizfelipegalvaoramos/dev/pokered/macros/ram.asm` | party/box/battle/sprite/connection structs |
| `/Users/luizfelipegalvaoramos/dev/pokered/constants/pokemon_data_constants.asm` | `PARTYMON_STRUCT_LENGTH=$2C`, offsets |
| `/Users/luizfelipegalvaoramos/dev/pokered/constants/event_constants.asm` | `EVENT_*`, `NUM_EVENTS` |
| `/Users/luizfelipegalvaoramos/dev/pokered/constants/ram_constants.asm` | badge/status/misc bits |
| `/Users/luizfelipegalvaoramos/dev/pokered/constants/battle_constants.asm` | battle enums/status |
| `/Users/luizfelipegalvaoramos/dev/pokered/constants/item_constants.asm` | items/HM/TM |
| `/Users/luizfelipegalvaoramos/dev/pokered/constants/map_constants.asm` | map IDs / gyms |
| `/Users/luizfelipegalvaoramos/dev/pokered/constants/map_data_constants.asm` | warps/connections |
| `/Users/luizfelipegalvaoramos/dev/pokered/constants/move_constants.asm` | Cut/Fly/Surf/… |
| `/Users/luizfelipegalvaoramos/dev/pokered/constants/type_constants.asm` | types |
| `/Users/luizfelipegalvaoramos/dev/pokered/data/types/type_matchups.asm` | ROM matchups |
| `/Users/luizfelipegalvaoramos/dev/pokered/pokered.sym` | resolved addresses |

**Note:** Gen1 Red has **no Tea** item; Saffron uses Fresh Water/Soda Pop/Lemonade + `BIT_GAVE_SAFFRON_GUARDS_DRINK`. Silph Scope / Card Key / Lift Key / Secret Key are primarily **bag items**, with some parallel events (e.g. Lift Key drop).