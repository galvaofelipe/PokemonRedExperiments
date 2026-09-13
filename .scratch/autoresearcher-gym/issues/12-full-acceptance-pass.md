# 12 — Full acceptance pass

**What to build:** The spec's five-point definition of done (D13), executed
end-to-end by hand with zero auto-researcher code: the human simulates the
researcher. This is the gate that declares the gym side finished and unblocks
auto-researcher work.

**Blocked by:** 07 — Frozen enforcement; 08 — Ledger + Milestones + Champion;
09 — daily Report; 10 — live map viz; 11 — offline replay.

**Status:** ready-for-agent

- [ ] Baseline reproduction: a v3 baseline run matches v2 behavior within noise
      (telemetry + tensorboard)
- [ ] Manual loop iteration: hand-edit the Editable file, submit a job, receive a
      Scorecard with Score + breakdown + splits, Ledger row appended
- [ ] Enforcement proven: hash check passes normally; a deliberate Frozen tamper
      is caught and the run refused
- [ ] A run is watched live on the map viz AND replayed offline after finishing
- [ ] A daily Report renders from that day's Ledger + Scorecards + Milestones
- [ ] Everything above is recorded as a short verification log in the repo's
      scratch area so the auto-researcher phase starts from evidence
