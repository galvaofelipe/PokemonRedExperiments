#!/usr/bin/env bash
# publish_run.sh — copy a lineage's shareable artifacts to the tower share
# (ticket 19, frozen design item 6):
#
#   v2/publish_run.sh <lineage>
#
# Copies checkpoint zips + sidecars + tfevents (+ resource_summary.txt,
# resource_log.csv, run.json when present) from the local lineage dir
# runs_<lineage>/ to $POKERED_DATA/pokered/runs/v2/<lineage>/. Videos and
# per-episode .state dumps stay out. Copy-only, never deletes; safe to
# re-run. run.json is produced by backup_run() into baselines/<lineage>/,
# so it is picked up from there when the session dir lacks one.
#
# Bash 3.2 compatible (macOS /bin/bash). Diagnostics go to stderr.

set -euo pipefail

err() { printf '%s\n' "$*" >&2; }

if [[ $# -ne 1 ]]; then
  err "usage: $0 <lineage>   (e.g. t16_acc64_s0; runs_ prefix optional)"
  exit 2
fi

LINEAGE="${1#runs_}"
LINEAGE="${LINEAGE%/}"

if [[ -z "${POKERED_DATA:-}" ]]; then
  err "POKERED_DATA is unset; mount the share first:"
  err "  POKERED_DATA=\$(scripts/ensure_tower.sh)"
  exit 1
fi
if [[ ! -d "$POKERED_DATA" ]]; then
  err "POKERED_DATA ($POKERED_DATA) is not a directory; is the share mounted?"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")" && pwd)"
SRC="$ROOT/runs_$LINEAGE"
DST="$POKERED_DATA/pokered/runs/v2/$LINEAGE"

if [[ ! -d "$SRC" ]]; then
  err "local lineage dir not found: $SRC"
  exit 1
fi

mkdir -p "$DST"

# tar-pipe preserves the relative layout (tfevents live in poke_ppo_*/
# subdirs) and works with both GNU tar and macOS bsdtar.
list_files() {
  (cd "$SRC" && find . -type f \( \
      -name 'poke_*_steps.zip' -o \
      -name 'poke_*_steps.json' -o \
      -name '*tfevents*' -o \
      -name 'resource_summary.txt' -o \
      -name 'resource_log.csv' -o \
      -name 'run.json' \
  \) -print)
}

count="$(list_files | wc -l | tr -d ' ')"
if [[ "$count" -eq 0 ]]; then
  err "nothing publishable under $SRC (no zips/sidecars/tfevents/summaries)"
  exit 1
fi

(cd "$SRC" && list_files | tar -cf - -T -) | tar -xf - -C "$DST"

if [[ ! -f "$DST/run.json" && -f "$ROOT/baselines/$LINEAGE/run.json" ]]; then
  cp -p "$ROOT/baselines/$LINEAGE/run.json" "$DST/run.json"
  err "run.json taken from baselines/$LINEAGE/"
fi

err "published $count file(s) from $SRC to $DST"
printf '%s\n' "$DST"
