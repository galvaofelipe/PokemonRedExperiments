# 15 — Badge identity in Scorecard + Milestones

**What to build:** Per-badge identity in the eval pipeline. Today the Scorecard
exposes badges only as a count (`components.badges`), so a run that skipped
Brock and earned a later badge is indistinguishable from one that earned
Brock's and missed the later one. Extract the eight badge bits (wObtainedBadges,
`0xD356`, already verified for splits in D16) during eval, record the achieved
badge names per episode in the Scorecard (version bump), and let the Milestones
log record first-ever badge achievements by badge identity — not only via the
badge-named splits. This is a Frozen change: follow the 2-commit flow from
issue 07 (Frozen commit with `--no-verify`, then manifest re-hash commit).

**Blocked by:** 08 — Ledger + Milestones + Champion promotion.

**Status:** needs-triage

- [ ] Scorecard records which badges each episode earned, not just the count
- [ ] First-ever badge achievements land in the Milestones log by badge identity
- [ ] A badge-skip run (later badge without Brock) is distinguishable in the
      Scorecard and Milestones from a Brock-only run
- [ ] Frozen manifest re-hashed via the issue-07 flow; suite stays green
