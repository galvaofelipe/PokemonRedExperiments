# Pokémon Red/Blue splits: `.lss` parsing + reference split tables

Scope: **Any% Glitchless (Classic)** `.lss` files (pokeguy, Headbob) and the **124 Glitchless Classic**
world-record split table. (Glitched categories intentionally omitted.)

## 1. How `.lss` files work

LiveSplit splits = plain XML. Per segment you get:

```
<Segment>
  <Name>Brock</Name>
  <SplitTimes>                     ← CUMULATIVE clock times at this split
    <SplitTime name="Personal Best"><RealTime>00:11:44.42</RealTime></SplitTime>
    <SplitTime name="WR">          ← runner-made comparison columns; names vary
      <RealTime>00:11:31</RealTime></SplitTime>
  </SplitTimes>
  <BestSegmentTime>                ← "gold": fastest SEGMENT DURATION ever
    <RealTime>00:04:07.60</RealTime></BestSegmentTime>
  <SegmentHistory>…</SegmentHistory>  ← this segment's time in every attempt
</Segment>
```

Gotchas:
- `SplitTimes` = cumulative from timer start; `BestSegmentTime` = duration. Subtract
  consecutive PBs (or read the gold) for segment lengths.
- Comparison columns beyond "Personal Best" are **runner-invented** ("WR", "Target", …)
  and are frozen snapshots — they go stale after every record.
- `<AutoSplitterSettings>` records which RAM triggers were armed (gym flags at $D6xx,
  map IDs at $D35E, HOF, …) — splits and addresses line up.
- `AttemptHistory` / `SegmentHistory` contain every attempt: you can compute averages,
  consistency, gold-sum, etc.

Python extraction:

```python
import xml.etree.ElementTree as ET
r = ET.parse('file.lss').getroot()
for s in r.findall('./Segments/Segment'):
    name = s.findtext('Name')
    pb   = s.find("./SplitTimes/SplitTime[@name='Personal Best']/RealTime")
    gold = s.find('./BestSegmentTime/RealTime')
    print(name, pb.text if pb is not None else '-', gold.text if gold is not None else '-')
```

## 2. Any% Glitchless (Classic) — from the `.lss` files

Classic = glitchless, no RNG/luck manipulation. WR ≈ 1:56 scale. Do not mix with
manips-allowed Any% Glitchless (≈1:44) or glitched Catch 'Em All (~1:30).

### pokeguy — PB 1:55:56.24 (561 attempts) — columns: **PB** (runner's PB) and **WR** (WR-pace snapshot)

| Split | PB (cumulative) | WR pace |
|---|---|---|
| Nidoran | 00:06:58.89 | 00:07:01 |
| Brock | 00:11:44.42 | 00:11:31 |
| Route 3 | 00:19:04.44 | 00:18:41 |
| Mt Moon | 00:26:41.39 | 00:27:12 |
| Nugget Bridge | 00:33:56.14 | 00:34:22 |
| Misty | 00:39:22.16 | 00:39:28 |
| Surge | 00:48:21.18 | 00:49:10 |
| HM02 | 00:59:06.50 | 00:59:39 |
| Giovanni 1 | 01:05:48.07 | 01:06:34 |
| Poke Flute | 01:13:08.99 | 01:13:51 |
| Koga | 01:26:41.69 | 01:27:15 |
| Blaine | 01:32:46.30 | — |
| Sabrina | 01:34:28.62 | — |
| Erika | 01:36:24.07 | — |
| Giovanni 3 | 01:39:45.44 | 01:40:44 |
| Lorelei | 01:47:51.13 | 01:48:35 |
| Bruno | 01:49:05.93 | 01:50:02 |
| Agatha | 01:50:56.31 | 01:51:47 |
| Lance | 01:52:51.89 | 01:53:27 |
| Champion | 01:54:42.28 | 01:55:08 |
| Hall of Fame | 01:55:56.24 | 01:56:29 |

### Headbob — PB 1:59:38.05 (207 attempts, 2018-era) — columns: **PB** and **Target** (personal goal pace)

| Split | PB (cumulative) | Target |
|---|---|---|
| Nidoran | 00:06:31.07 | 00:07:10 |
| Brock | 00:11:24.96 | 00:12:00 |
| Route 3 | 00:19:20.57 | 00:19:50 |
| Mt. Moon | 00:26:58.31 | 00:28:00 |
| Bridge | 00:34:23.62 | 00:35:30 |
| Misty | 00:39:45.33 | 00:40:53 |
| Surge | 00:49:00.44 | 00:50:33 |
| Fly | 01:00:15.27 | 01:01:08 |
| Giovanni 1 | 01:07:23.38 | 01:08:03 |
| Flute | 01:15:04.08 | 01:15:33 |
| Koga | 01:29:27.10 | 01:29:48 |
| Blaine | 01:35:37.22 | 01:35:48 |
| Sabrina | 01:37:21.63 | 01:37:31.50 |
| Erika | 01:39:18.61 | 01:39:28 |
| Giovanni 3 | 01:42:43.60 | 01:42:53 |
| Lorelei | 01:51:15.60 | 01:50:58 |
| Bruno | 01:52:31.53 | 01:52:14 |
| Agatha | 01:54:25.59 | 01:54:02 |
| Lance | 01:56:25.27 | 01:55:55 |
| Hall of Fame | 01:59:38.05 | 01:59:00 |

Note: same category, same split points, but Headbob's 2018 targets are ~3–4 min slower
than modern Classic — era matters as much as the category.

## 3. 124 Glitchless Classic — current WR: Shenanagans 6:29:56.77 (speedrun.com/pkmnrbext)

No `.lss` circulates; table reconstructed from WR-run timer screenshots. Column **Time** =
the run's own cumulative splits; **Δ vs old PB** = live delta against the previous 6:36:47 PB
(shown where visible in the crops). Split names carry the live Pokédex count.

| Split | Time | Δ vs old PB | | Split | Time | Δ vs old PB |
|---|---|---|---|---|---|---|
| Brock (3) | 12:45 | +52.8 | | Power Plant (48) | 2:55:03 | −15:47 |
| Enter (7) | 22:49 | +47.2 | | Route 21 (52) | 3:04:50 | −14:26 |
| Exit (10) | 33:24 | −28.9 | | Mansion (60) | 3:24:02 | −6:43 |
| Misty (10) | 36:33 | −43.3 | | Blaine (64) | 3:39:11 | −8:46 |
| Trio (13) | 1:00:13 | −1:08 | | Sabrina (74) | 3:54:49 | −6:47 |
| Surge (14) | 1:03:23 | −1:23 | | Giovanni (75) | 4:03:52 | −7:40 |
| Fly (14) | 1:24:10 | −59.3 | | Fishing round 2 (79) | 4:20:23 | −3:17 |
| Flute (18) | 1:35:58 | −2:52 | | Vroad (85) | 4:31:21 | −6:15 |
| Szone Round 1 (33) | 2:00:19 | −19:00 | | Round 1 (85) | 4:46:34 | −9:12 |
| Gamble 1 (36) | 2:00:19–2:18:46 | — | | Seafoam (94) | 4:59:54 | −10:19 |
| Silph (37) | 2:23:16 | −19:37 | | Cerulean Cave (107) | 5:24:06 | −11:17 |
| Koga (37) | 2:29:34 | −20:32 | | Cleanup (115) | 5:38:49 | −7:51 |
| Safari Round 2 (37) | 2:36:30 | −16:13 | | GOMBLE (116) | 5:49:38 | −8:00 |
| Fishing 1 (44) | 2:48:23 | −15:11 | | Rapidash (122) | 6:01:16 | −8:53 |
| | | | | Persian (123) | 6:10:48 | −12:24 |
| | | | | **Round 2! (124)** | **6:29:56.77** | **−6:50** |

Gamble 1 is the only split not directly observable (passed between screenshots; old PB
2:10:50). Fill from the WR video if chapters exist.

**Name glossary:** Enter/Exit = Mt. Moon entry/exit · Trio = Cerulean catch/evolution block ·
Szone = Safari Zone (two visits) · Gamble/GOMBLE = high-variance catch attempts (renamed
between runs) · Fishing 1/2 = rod-catch blocks · Vroad = Victory Road · Round 1 = first
Elite Four pass · Cleanup = late-route pickups · Round 2! = finish (final catches + E4 round 2).

**Pace notes:** early game mirrors a glitchless any% route until Szone Round 1 (33) at ~1:41–2:00.
Mid-game is tight (Silph→Koga 6:18). The run is decided late: Cleanup→finish is ~51 min for
9 catches; Persian→Round 2! alone is 19:08.59 (split PB 13:34.15, gold 12:33.42 — even the WR
lost ~6 min to endgame variance).
