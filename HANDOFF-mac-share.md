# HANDOFF-mac-share — Mac ↔ AM18 run/checkpoint sharing via tower share

**Purpose:** how the Mac (`mac-mini`) and the AM18 (`win-p2kh1a2oie9`, WSL2) exchange
run data through the unraid tower share. Audience: operator + agents on either machine.
Read together with `$POKERED_DATA/pokered/README.md` (share layout source of truth).

## Mount (both machines)

```sh
POKERED_DATA=$(scripts/ensure_tower.sh)   # idempotent; prints the mount point
```

- Prints `~/mnt/tower` on stdout; diagnostics on stderr. Already-mounted → prints and exits.
- Host selection: probes LAN `192.168.0.9:445`, falls back to `tower.ide-pogona.ts.net`.
  On Linux the mount itself is time-bounded and also falls back after a failed attempt —
  a bare 445 listener is NOT proof of a working SMB server (seen in the wild: LAN host
  accepted TCP then stalled negotiation and hung the mount).
- WSL2: needs `cifs-utils` + sudo (operator-run), `SMB_PASS` or interactive prompt.
- macOS: `mount_smbfs`, no sudo; `SMB_PASS` in the URL (special chars need %-encoding).
- Mount dies on reboot / `wsl --shutdown`. Persistence (fstab + `~/.smbcredentials` on
  WSL; Login Items on macOS) is a deliberate TODO.
- Code must reference the share via `POKERED_DATA` only, never hardcoded paths.

## Layout

```
$POKERED_DATA/pokered/
  roms/      # PokemonRed.gb + .state files (gitignored in repo; copy from here)
  runs/v2/   # published v2 run data — one dir per run name
  runs/v3/   # v3 run data
  bus/       # RESERVED for a future queue/bus — do not stash ad-hoc data here
```

## Publishing a run (producer side)

Copy, don't move. Write once; don't edit in place:

```
$POKERED_DATA/pokered/runs/v2/<run_name>/
  poke_*_steps.zip                     # checkpoints
  resource_summary.txt, resource_log.csv
  run.json                             # backup_run() metadata (cli args, seed, host, timesteps)
```

Skip tfevents, videos, and per-episode `.state` dumps — mirror what
`backup_run()` (`v2/baseline_fast_v2.py`) already skips. Small coordination files
(job specs, ledgers, perf manifests) stay in git, not on the share.

## Consuming (other machine)

1. `POKERED_DATA=$(scripts/ensure_tower.sh)`
2. Copy the needed checkpoint **down to local disk** before training (one-shot read
   from CIFS is fine; session dirs and TB logs always stay local).
3. Point `--checkpoint` at the local copy.

Known sharp edges:

- **Jobs 023/024** (`v2/jobs/`) resume from `runs_t05_*/poke_1966080_steps`, which
  exist only on the Mac until published. Mac: publish `runs_t05_g2560_s0` +
  `runs_t05_g20480_s0` to `pokered/runs/v2/`. AM18: copy the zips into local `v2/`
  before `./run_queue.sh`. (Ticket 19 tracks making this class of reference portable.)
- **Telemetry columns are NOT cross-platform comparable**: Mac = phys_footprint +
  lifetime cpu_pct; Linux = PSS footprint + interval cpu_pct. Compare SPS across
  machines; size RAM per machine via `docs/perf/<host>.md`.

## Performance manifests: `docs/perf/<host>.md`

Each machine keeps a living manifest **in git**: hardware, bench harness + cells,
results, recommended production geometries, headroom warnings, validation caveats.
Consult it before sizing any run for that machine; update it after bench sessions or
config changes (`.wslconfig`, torch version, etc.). Current: `docs/perf/am18.md`
(mac-mini pending).
