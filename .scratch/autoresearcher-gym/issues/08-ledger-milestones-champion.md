# 08 — Ledger + Milestones + Champion promotion

**What to build:** The Ratchet's memory (spec D9/D12): after each run the runner
appends one row to the append-only Ledger (commit, tag, Score mean/max, component
counts, steps, sps, train minutes, status keep/discard/crash, description, run
type, score version, suite version, init states). First-time split/badge
achievements are recorded permanently in a separate Milestones log with run and
step. A win (Score > Champion + δ, δ = 2.0 initially) automatically keeps the
commit and promotes the checkpoint to Champion (Marathon warm-start target);
the human can demote via git. Discards reset the lineage to the Champion.

**Blocked by:** 05 — split extraction; 06 — runner + job queue.

**Status:** ready-for-agent

- [ ] Each completed job appends exactly one Ledger row with the full schema
- [ ] A first-ever split achievement lands in the Milestones log once, with the
      run id and step; repeat achievements do not re-log
- [ ] A winning experiment promotes automatically; a non-winning one resets the
      tree to the Champion commit
- [ ] Scores differing by less than δ do not promote (noise gate)
- [ ] The Ledger is never committed to git and survives tree resets
