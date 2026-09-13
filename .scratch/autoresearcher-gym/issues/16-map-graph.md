# 16 — Map graph (warps into Frozen metadata)

**What to build:** The Frozen Map graph: maps as nodes, overworld `connection`s
plus `warp_event` destinations as edges. `.scratch/references/v3-map-metadata.json`
already has 248 maps (id, const, kind, size, tileset, tags) and the 36-map
overworld ring (78 reciprocal connections). It only has `warp_count`. Parse
`warp_event` from the same pret source (`~/dev/pokered/data/maps/objects/*.asm`)
in the same pass, write destinations onto each map, and freeze a pinned copy
under `v3/frozen/maps/` (json + sha256, same pattern as `v3/frozen/splits/`).

This is geography, not a progress signal. Do not derive a Pallet→Champion order
from it. Do not change the Score. Fly / Teleport / Dig / dungeon-hole tables in
`special_warps.asm` are out of scope.

This is a Frozen change: follow the 2-commit flow from issue 07 (Frozen commit
with `--no-verify`, then manifest re-hash commit).

**Blocked by:** none (scaffold + pret clone are already there).

**Status:** ready-for-human

- [x] Each map with warps has a `warps` list `{x, y, dest, dest_warp}`; `dest`
      is a pret const or the sentinel `LAST_MAP` (not silently dropped)
- [x] Pallet’s three doors resolve to `REDS_HOUSE_1F` / `BLUES_HOUSE` /
      `OAKS_LAB`; Pewter Gym exits `LAST_MAP`; Mt Moon 1F/B1F/B2F name each
      other; unused/copy maps stay in the table but are not required as
      graph consumers
- [x] Overworld `connections` still form one component of 36 with every listed
      edge reciprocal
- [x] Regenerated `.scratch/references/v3-map-metadata.json` matches the Frozen
      file; `v3/frozen/maps/` is sha256-pinned and loaded like splits
- [ ] Tests cover parse fixtures (Pallet, a `LAST_MAP` interior, a named
      dungeon floor) without importing pyboy; Frozen manifest re-hashed via
      the issue-07 flow

## Why this is its own ticket

Issue 17 hangs essential map ids on Route DAG nodes and needs warp edges to
exist. Issues 10/11 (live / offline map viz) can consume adjacency later.
Neither owns the pret parse. The INBOX “expected sequence” item is 17, not this.

## Comments

- 2026-09-13: Locked with the human. D1 = parse warps in the same pret pass as
  the existing metadata. `LAST_MAP` stays a sentinel (~244 such warps in pret;
  reverse of a named overworld→indoor door is the usual pairing, not required
  as a stored edge here). Intra-map collision / pathfinding is out.
- 2026-09-13: Implemented. Parse-fixture + Frozen loader tests are green.
  `v3/frozen_manifest.sha256` was left alone on purpose — landing is the human
  issue-07 2-commit flow (`--no-verify` Frozen commit, then
  `v3/bin/rehash_frozen_manifest.py`). Until then, `frozen_manifest.verify`
  reports extra_on_disk:
  `v3/frozen/maps/{__init__.py,data.py,manifest.json,maps.json}`.
  Scratch and Frozen JSON match byte-for-byte (244 LAST_MAP warps). Two
  non-warp parse corrections vs the pre-ticket catalog: (1) `UNDERGROUND_PATH_ROUTE_7`
  `header` is `UndergroundPathRoute7.asm` (not the Copy alias that shares the
  same `map_header` const); (2) `SILPH_CO_7F` `object_count` is 11 object_event
  lines (old 12 counted `SILPHCO7F_UNUSED`, which has no object_event).
  Assumptions: `has_trainer` is any `OPP_*` object_event (8-arg statics like
  Zapdos stay false); every map has a `warps` list so `warp_count == len(warps)`;
  Frozen file is `maps.json` with `MAPS_VERSION = "1.0.0"`; tags overlay is
  read from the existing scratch JSON at generate time.
