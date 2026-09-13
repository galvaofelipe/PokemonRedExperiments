# 09 — Daily Report + WR pace references

**What to build:** The human-facing daily Report (spec D8/D17): frozen reference
tables derived from the two LiveSplit `.lss` files (pokeguy PB with WR-pace
column; Headbob 2018-era), and a renderer that turns a day's Ledger rows +
Scorecards + Milestones into a readable digest: experiments run, keeps/discards,
Score progression, splits achieved with in-game times, and — where a human
counterpart split exists (13 of our 16) — agent split time vs WR pace. The
Report influences no automated decision.

**Blocked by:** 08 — Ledger + Milestones + Champion promotion.

**Status:** ready-for-agent

- [ ] The reference tables capture both runners' cumulative split times and note
      the era difference
- [ ] Rendering a day with runs produces the digest with Score progression and
      split/WR comparisons
- [ ] Rendering a day with no runs produces a sane empty report
- [ ] Splits without a human counterpart (Bill, HM01, Bike) render without a
      comparison, not with an error
