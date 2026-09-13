# docs/perf — per-machine performance manifests

One `<hostname>.md` per training machine. This is how we decide geometry and capacity
for a run **on that machine** instead of carrying folk numbers between boxes.

## What a manifest records

- Hardware + relevant config (RAM cap, swap, torch build, WSL/macOS version).
- Bench method: harness (`v2/bench_sps.sh`, `v2/bench_geometry.sh`), cell definitions,
  run length (bursts vs steady-state).
- Results tables (SPS, peak memory, peak CPU) with the date measured.
- Recommended production geometries + headroom warnings.
- Validation caveats (e.g. burst numbers vs week-long thermal soak).

## Rules

- Manifests live in git (small coordination files; run data itself stays gitignored
  or on the tower share — see `HANDOFF-mac-share.md`).
- Update after every bench session or config change (`.wslconfig`, torch, OS).
- Memory/CPU metrics are platform-specific (Mac: phys_footprint + lifetime cpu;
  Linux: PSS + interval cpu). **Never compare mem/cpu columns across manifests —
  compare SPS only.** RAM sizing is per-machine.
