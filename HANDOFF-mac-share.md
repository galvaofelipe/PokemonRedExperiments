# HANDOFF-mac-share — Mac ↔ AM18 run/checkpoint sharing via tower share

**Purpose:** how the Mac (`mac-mini`) and the AM18 (`win-p2kh1a2oie9`, WSL2) exchange
run data through the unraid tower share. Audience: operator + agents on either machine.
Read together with `$POKERED_DATA/pokered/README.md` (share layout source of truth).

## Mount (both machines)

```sh
POKERED_DATA=$(scripts/ensure_tower.sh)   # idempotent; prints the mount point
```

- Prints the share root `~/mnt/tower/data` on stdout; diagnostics on stderr.
  Already-mounted → prints and exits. The `data` share mounts at
  `$TOWER_MNT/$TOWER_SHARE` on both OSes, so sibling shares (`appdata`, `media`)
  can live side by side under `~/mnt/tower/`.
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

Copy, don't move. Write once; don't edit in place. Since the lineage system
(ticket 19), the standard way is:

```sh
v2/publish_run.sh <lineage>   # → $POKERED_DATA/pokered/runs/v2/<lineage>/
```

It copies zips + lineage sidecars + tfevents + resource files (run.json taken
from `v2/baselines/<lineage>/` when absent in the session dir), never deletes,
and refuses to run without a valid `POKERED_DATA`. Manual publishing follows
the same layout:

```
$POKERED_DATA/pokered/runs/v2/<run_name>/   # <run_name> = backup name (e.g. t16_g20480_s0)
  poke_*_steps.zip + poke_*_steps.json  # checkpoints + lineage sidecars
  tfevents (poke_ppo_*/, histogram/)    # the lineage's TB curve travels with it
  resource_summary.txt, resource_log.csv
  run.json                             # backup_run() metadata (cli args, seed, host, timesteps)
```

Canonical source: `v2/baselines/<run_name>/` (the `--backup` output) — rsync it
verbatim. tfevents are included since 2026-09-14 (a lineage = one TB curve;
scalar event files are small); videos and per-episode `.state` dumps stay out —
mirror what `backup_run()` (`v2/baseline_fast_v2.py`) already skips. Small
coordination files (job specs, ledgers, perf manifests) stay in git, not on the
share.

## Consuming (other machine)

1. `POKERED_DATA=$(scripts/ensure_tower.sh)`
2. Copy the needed checkpoint **down to local disk** before training (one-shot read
   from CIFS is fine; session dirs and TB logs always stay local).
3. Point `--checkpoint` at the local copy.

Known sharp edges:

- **Jobs 022/023/024** resume from `runs_t05_*/runs_t15_*/poke_1966080_steps`.
  RESOLVED 2026-09-13: published to `pokered/runs/v2/` under backup names —
  `t05_g2560_s0`, `t05_g20480_s0`, `t15_acc64_s0` (parents) and `t16_acc64_s0`,
  `t16_g20480_s0` (tonight's finished runs). `t16_g2560_s0` still running on the
  Mac — publish from `v2/baselines/t16_g2560_s0/` once done. Consumer: copy the
  needed zip into local `v2/runs_*/` before `./run_queue.sh`. (Ticket 19 tracks
  making this class of reference portable.)
- **Telemetry columns are NOT cross-platform comparable**: Mac = phys_footprint +
  lifetime cpu_pct; Linux = PSS footprint + interval cpu_pct. Compare SPS across
  machines; size RAM per machine via `docs/perf/<host>.md`.

## Performance manifests: `docs/perf/<host>.md`

Each machine keeps a living manifest **in git**: hardware, bench harness + cells,
results, recommended production geometries, headroom warnings, validation caveats.
Consult it before sizing any run for that machine; update it after bench sessions or
config changes (`.wslconfig`, torch version, etc.). Current: `docs/perf/am18.md`
(mac-mini pending).

## Publicando as legs t16 s1/s2 (instrução pro agente no Mac, 2026-09-14)

As runs da fase 2 (jobs 024–029, s1/s2, terminam ~17h) já saem com **relógio
global** — NÃO rodar `tb_stitch.py`, NÃO aplicar offset na extração. Quando cada
uma terminar:

1. Publica o dir da leg2 em `pokered/runs/v2/t16_<braço>_s<seed>/` como sempre
   (zips, `resource_summary.txt`, `resource_log.csv`, `run.json`) **+ os tfevents
   desta vez** — mudança de convenção: sob o desenho congelado do ticket 19 a
   curva TB viaja com a linhagem (tfevents de scalars são pequenos; vídeos e
   states por-episódio continuam fora).
2. Publica também os tfevents da leg1 correspondente (`runs_t15_acc64_s<seed>`
   ou `runs_t05_<braço>_s<seed>`) no dir da linhagem de origem no share.
3. NÃO consolidar leg1+leg2 num dir único no Mac — a consolidação é passo da
   migração no AM18 e só acontece depois do mecanismo novo ser validado
   (ticket 19). Deixa os dirs como estão.
4. Publica também os tfevents das runs **t16 s0** (`runs_t16_*_s0/poke_ppo_1` +
   `histogram/`) nos dirs `t16_*_s0` do share — a curva stitchada 0→11M só
   existe no Mac; o share está com zero tfevents hoje (verificado 2026-09-14).
5. Depois de publicar as s1/s2, roda o backfill de sidecars delas (idempotente,
   manifest já cobre s1/s2):
   `python3 .scratch/explore-v2-training/scripts/migrate_legacy_sidecars.py $POKERED_DATA/pokered/runs/v2 --apply`
6. `git pull -r` antes de mexer em qualquer doc — o desenho congelado está no
   ticket 19, no CONTEXT.md e no ADR `docs/adr/0001` desde 2026-09-14.
