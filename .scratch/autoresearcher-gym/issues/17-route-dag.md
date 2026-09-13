# 17 — Route DAG + Scorecard compass

**What to build:** The Frozen Route DAG: named story beats as nodes, required-before
as edges, essential maps annotated on each node, plus a post-hoc extractor and a
Scorecard `route` section that acts as a compass (what has fired, what can come
next, what is off the Spine). Membership is Human-owned, then Frozen like
splits (`v3/frozen/route/route.json` + sha256, own `ROUTE_VERSION`).

This is **not** pokerl’s published quest mermaid — that sketch informs the
shape, it is not our artifact. This is **not** a Score component (`unique_maps`
stays the unordered count). This is **not** a topological sort of the Map
graph. Nodes may fire out of Spine order; parallel groups are progress.

Mirror splits (issue 05): first-hit decision step + in-game play clock from
telemetry; CLI `python -m frozen.route <telemetry.gz|dir>`; Scorecard omits
the `route` section when the extractor is not passed so 1.1.0 cards stay
interpretable (version bump when present). Report (09) and TensorBoard (14)
consume later — do not block this ticket on them.

This is a Frozen change: follow the 2-commit flow from issue 07.

**Blocked by:** 16 — Map graph (node `maps[]` resolve through the Frozen map
table). Split hit conditions (05) and telemetry (03) already exist.

**Status:** ready-for-human

- [x] Frozen `route.json` has `nodes` (id, kind, hit, maps[], spine,
      optional `parallel_group`) and `edges` (from → to required-before).
      Spine starts from `.scratch/references/v3-obs-ram-map.json`
      `any_percent_spine` and uses split names where they overlap
- [x] Parallel groups exist at least for: Misty ↔ Bill/Anne; Surge / Erika /
      Hideout; Koga / Sabrina / Safari HMs / Blaine. Achieving a
      `spine: false` node counts as progress
- [x] `maps[]` are essential maps only (D4): gyms, Forest, Mt Moon floors,
      Bill’s, dock + Anne floors for Cut, hideout to Scope, Tower to Fuji,
      Silph floors to Giovanni, Safari entrance + West + Secret House,
      Mansion B1F, VR + E4 rooms + Champion + HOF, Viridian Mart (parcel).
      Exclude houses, PCs, marts, museum, copies, unused. Bike shop is not
      on `maps[]` (Bike remains a split)
- [x] Extractor reports first-hit step + play clock per achieved node from
      telemetry; hit conditions reuse issue-05 split defs when the node is a
      split, else event bit or map entry. Tests cover an in-order Spine hit,
      a parallel-only hit, and a parent-blocked node that must not enter the
      frontier
- [x] Scorecard `route` section: `{route_version, spine, achieved, frontier,
      furthest_spine, off_spine}` plus per-episode achieved. Omitted when
      `episode_route` is not passed. Score formula and `unique_maps` unchanged
- [ ] CLI `python -m frozen.route` inspects training or eval telemetry.
      Frozen manifest re-hashed via the issue-07 flow; suite stays green

## Compass (acceptance meaning)

Given achieved node hits:

- **frontier** — unachieved nodes whose parents are all achieved
- **furthest_spine** — last Spine node achieved
- **off_spine** — achieved nodes with `spine: false`
- **missing_essential_maps** — optional, cheap: Spine/frontier `maps[]` never
  entered this episode

Do not score graph distance. Do not grow `mmp` to Champion.

## Why this is its own ticket

Issue 16 is ROM adjacency. Issue 05 is named split timing. Issue 04 already
lists map names on the Scorecard as an unordered set. The INBOX “expected map
sequence” item is this DAG + compass, not a 248-long list.

## Comments

- 2026-09-13: Locked with the human. D2 = Spine (not every map). D3 = parallel
  groups so off-main-route beats still show as progress. D4 = exclude most
  interiors; keep maps required for necessary achievements. Pokerl docs are a
  reference for forks, not Frozen data.
- 2026-09-13: STOP — implementation blocked on hit conditions for `card_key`
  and `secret_key`. Neither `EVENT_GOT_CARD_KEY` nor a Secret Key EVENT exists
  in Frozen `v3/frozen/env/events.json` or in
  `.scratch/references/v3-obs-ram-map.json` `event_bits`. events.json has no
  "Got Card Key" / "Got Secret Key" row (the only "Key" event is
  `0xD81B-6` "Rocket Dropped Lift Key"). The ram catalog lists CARD_KEY /
  SECRET_KEY only as bag item ids (`0x30` / `0x2B`) in `required_items`, and
  `.scratch/references/v3-obs-ram-catalog.md` says both have "no GOT event"
  and live in the bag. How should those two nodes hit? Do not invent
  addresses.
- 2026-09-13: Human lock — **bag first-presence** for both. Hit kind
  `bag_item`: CARD_KEY `$30`, SECRET_KEY `$2B` in `wBagItems` (`0xD31E`,
  20×(id,qty)+`$FF`; count at `wNumBagItems` `0xD31D`). First snapshot the
  id appears. No GOT event. Key items are not tossable, so the hit stays
  monotone.
- 2026-09-13: Implemented. `v3/frozen/route/` (`route.json` + sha256
  `manifest.json`, `ROUTE_VERSION = "1.0.0"`, `load_route()` resolves
  pret consts via `load_maps()`). Extractor + CLI `python -m frozen.route`.
  Scorecard omits `route` without `episode_route`; with it emits
  `{route_version, spine, achieved, frontier, furthest_spine, off_spine}`
  and per-episode `route.achieved`. `SCORECARD_VERSION` is `1.2.0` on new
  cards from `build_scorecard` (1.1.0 fixtures stay interpretable; `route`
  is optional). `run_eval` passes `episode_route` like `episode_splits`.
  `card_key` / `secret_key` are `bag_item` (no GOT event). `EVENT_BEAT_LANCE`
  is `0xD866` bit 6 from Frozen `events.json` "Beat Lance" (named in the
  locked table; not in `event_bits`). `v3/frozen_manifest.sha256` was left
  alone on purpose — landing is the human issue-07 2-commit flow
  (`--no-verify` Frozen commit, then `v3/bin/rehash_frozen_manifest.py`).
  Until then, `frozen_manifest.verify` reports extra_on_disk:
  `v3/frozen/route/{__init__.py,data.py,extractor.py,manifest.json,route.json,__main__.py}`.
  Tests: `.venv/bin/pytest v3/tests/test_route.py v3/tests/test_splits.py`
  → 21 passed; `test_scorer.py` + `test_eval.py` + `test_maps.py` → 33
  passed. Scorer / unique_maps / maps.json untouched.
