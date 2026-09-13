You've come to the right place — the Gen 1 speedrun community mapped all of this out years ago, and there's a public autosplitter you can read the exact addresses from. Here are the three key resources, then the full address table.

## The sources

**1. Maschell/LiveSplit.PokemonRedBlue** — the classic community autosplitter (LiveSplit component, 2014). It hooks the emulator process (VBA 1.7.2, BGB 1.4.3, Gambatte r550, BizHawk) and reads Game Boy WRAM directly. It auto-splits on 17 events: the 8 gym leaders, Mt. Moon, Rival at Nugget Bridge, Bill, HM01, Bike, HM02, Poké Flute, and Hall of Fame .

**2. pret/pokered** — the full disassembly of Red/Blue. This is the authoritative, labeled memory map (`wram.asm` for addresses, `constants/event_constants.asm` for every event flag, `constants/map_constants.asm` for map IDs). The map constants file confirms the IDs the autosplitter uses: Mt. Moon 1F/2F/3F = `$3B/$3C/$3D`, Hall of Fame = `$76` .

**3. DataCrystal RAM map** (TCRF wiki) — community-documented WRAM map. Notably `$D356` = badges byte and `$D35E` = current map .

## How it works

Everything is watched relative to WRAM base `$D000`. The splitter follows an emulator-specific pointer to find the emulated GB memory, then reads the GB address directly; all offsets below are GB addresses (US ROM; the German version adds `+0x05`) .

Gym progress lives in the per-event flag region starting at **`$D600`** (Gen 1 uses one full byte per event, not bitfields like Gen 2+). The splitter edge-triggers each split on a flag transitioning from unset to set.

## The splits → addresses table

| Split | Address | Trigger condition |
|---|---|---|
| **Timer start** | `$D35E` + `$D371` | Was on map `$26` (your bedroom during the intro) and RNG byte `$D371` = 0 |
| **Brock** | `$D755` | bit 7 (`0x80`) 0→1 |
| **Misty** | `$D75E` | bit 7 0→1 |
| **Lt. Surge** | `$D773` | bit 7 0→1 |
| **Erika** | `$D77C` | bit 1 (`0x02`) 0→1 |
| **Koga** | `$D792` | bit 1 0→1 |
| **Sabrina** | `$D7B3` | bit 1 0→1 |
| **Blaine** | `$D79A` | bit 1 0→1 |
| **Giovanni** | `$D751` | bit 1 0→1 |
| **Mt. Moon** | `$D35E` (map ID) | map becomes `$3B/$3C/$3D` |
| **Rival (Nugget Bridge)** | `$D75A` | byte ≠ 0 |
| **Bill** (S.S. Anne ticket) | `$D7F2` | bit 4 (`0x10`) 0→1 |
| **HM01 Cut** | `$D803` | bit 0 (`0x01`) 0→1 |
| **Bike** | `$D75F` | byte ≠ 0 |
| **HM02 Fly** | `$D7E0` | bit 6 (`0x40`) 0→1 |
| **Poké Flute** | `$D76C` | bit 0 (`0x01`) 0→1 |
| **Hall of Fame** | `$D35E` + `$D358` | map = `$76` **and** byte `$D358` = `2` |

The Brock address and its `0x80` mask come straight from the splitter's flag struct and gym-event enum — and note the quirk that Brock/Misty/Surge use bit 7 while the other five gyms use bit 1, because the games store those "leader beaten" flags in different bit positions per gym . The HOF split is the author's own combo: map `$76` plus `$D358` hitting `2` .

Also tracked but not split on by default: Rival at S.S. Anne (`$D665`), Rival at Ghost Tower (`$D764`), Rival at Silph (`$D7EB`), Articuno (`$D782`), Zapdos (`$D7D4`), Moltres (`$D7EE`), Mewtwo (`$D85F`), and both Snorlaxes (`$D7D8`, `$D7E0` bit 1). The splitter also reads the in-game clock at `$DA41` (h/m/s/frames) for game-time display and the battle-state byte `$D057` to count encounters .

## Practical notes

- **Simpler alternative for gyms:** instead of event flags you can just watch `$D356` (badges byte) for bit transitions — bit 0 = Boulder through bit 7 = Earth, in the trainer-card order. Since any% glitchless gets every badge from a gym, it's equivalent and one address instead of eight.
- **Verifying/extending this yourself:** the fastest workflow is BGB's debugger — set a write breakpoint on a flag address, beat the leader, watch the exact instruction that sets it. Cross-reference with `wram.asm` / `event_constants.asm` in pret/pokered, which give every address its real label (e.g. `wCurMap`, `wEventFlags`).
- **Modern tooling:** if the 2014 C# component feels dated, there's a newer open-source Lua script covering Gens 1–5 that does RNG/splitting work in-emulator , and the Pokémon Speedruns community (speedrun.com forums / r/pokemonrng) keeps these tools circulating.

Want me to dig into any specific split's trigger logic (e.g., exactly when the Brock flag byte gets written relative to the end-of-battle text)?