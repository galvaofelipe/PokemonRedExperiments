# Telemetry storage on UNRAID

Status: needs-triage

## Context

Settled in the v3 grilling session (2026-09-11): v3 records full per-decision-step
telemetry per env per episode (gzipped, ~20 bytes/step before compression) — the
foundation for map replay, split timing, and audits. At marathon scale
(~145–300M steps/weekend across envs) this accumulates fast.

## The question

How to store/archive run telemetry on the UNRAID box: directory layout, retention
policy (keep all cadence-run telemetry vs. keep only kept-experiments + marathons),
compression, and how the researcher/runner accesses it (mount? sync job?).

Not a blocker for v3 bring-up — local storage on the Mac is fine for now.

## Comments

- 2026-09-11: noted during grilling round 3; user deferred it explicitly.
