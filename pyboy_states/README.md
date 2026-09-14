# pyboy_states

Expanded PyBoy save-state inventory for eval milestones and research.

## Relationship to root states

The four early-game states at the **repo root** stay put — training jobs and
defaults still use `../init.state` (etc.). Do not remove them.

Those four files are byte-identical to the copies here:

| Root (stable path for runs) | Also in this directory |
|---|---|
| `init.state` | `pyboy_states/init.state` |
| `fast_text_start.state` | `pyboy_states/fast_text_start.state` |
| `has_pokedex.state` | `pyboy_states/has_pokedex.state` |
| `has_pokedex_nballs.state` | `pyboy_states/has_pokedex_nballs.state` |

## Provenance

Copied from [thatguy11325/pokemonred_puffer](https://github.com/thatguy11325/pokemonred_puffer)
`pyboy_states/` (byte-identical at import). Later milestone files (`mtmoon`,
`cut`, `surf`, `victory_road_*`, …) are the human-expanded eval pool (spec D6).

## Frozen

Everything under `pyboy_states/` is Frozen (hash-manifested), as are the four
root early-game states. Add or replace a state only by explicit human decision,
then rehash:

```bash
git add pyboy_states/ && git commit --no-verify   # Frozen paths only
python v3/bin/rehash_frozen_manifest.py
git add v3/frozen_manifest.sha256 && git commit --no-verify
```


PS: 
- Squirtle.state has pokedex and 5 pokeball
- Bulbasaur.state has pokedex and 5 pokeball
- Charmander.state has pokedex and 5 pokeball