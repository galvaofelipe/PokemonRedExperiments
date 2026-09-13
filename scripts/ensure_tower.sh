#!/usr/bin/env bash
# ensure_tower.sh — idempotently mount the tower (unraid) data share and print
# the mount point on stdout:
#
#   POKERED_DATA=$(scripts/ensure_tower.sh)
#
# Works on macOS and WSL2/Linux. Share layout/conventions live in
# $POKERED_DATA/pokered/README.md. Code must reference the share via
# POKERED_DATA only, never hardcoded paths — mount points differ per machine.
#
# Config (env overrides):
#   TOWER_HOST   share host. Default: probe LAN 192.168.0.9:445, else the
#                tailnet name tower.ide-pogona.ts.net. On Linux a failed
#                mount of a probed host also falls back to the tailnet name.
#   TOWER_SHARE  share name (default: data)
#   TOWER_USER   smb user (default: galvaofelipe)
#   TOWER_MNT    mount base (default: ~/mnt/tower); the share mounts at
#                $TOWER_MNT/$TOWER_SHARE, i.e. ~/mnt/tower/data by default
#   SMB_PASS     smb password; if unset the mount tool prompts interactively.
#                (macOS: special chars in SMB_PASS need URL-encoding.)
#
# Linux requires cifs-utils and root for the mount itself — the script calls
# sudo. Diagnostics go to stderr so $(...) captures only the path.
set -euo pipefail

SHARE_USER="${TOWER_USER:-galvaofelipe}"
SHARE_NAME="${TOWER_SHARE:-data}"
MNT="${TOWER_MNT:-$HOME/mnt/tower}/$SHARE_NAME"

err() { printf '%s\n' "$*" >&2; }

lan_reachable() {
  if [[ "$(uname -s)" == "Darwin" ]]; then
    # macOS has no GNU timeout; nc -G bounds the connect attempt.
    nc -z -G 2 192.168.0.9 445 >/dev/null 2>&1
  else
    timeout 2 bash -c ':</dev/tcp/192.168.0.9/445' 2>/dev/null
  fi
}

pick_host() {
  if [[ -n "${TOWER_HOST:-}" ]]; then
    printf '%s' "$TOWER_HOST"
  elif lan_reachable; then
    printf '192.168.0.9'
  else
    printf 'tower.ide-pogona.ts.net'
  fi
}

already_mounted() {
  if [[ "$(uname -s)" == "Darwin" ]]; then
    mount | grep -q " on $MNT ("
  else
    findmnt -M "$MNT" >/dev/null 2>&1
  fi
}

if already_mounted; then
  printf '%s\n' "$MNT"
  exit 0
fi

HOST="$(pick_host)"
mkdir -p "$MNT"
err "mounting //$HOST/$SHARE_NAME at $MNT (user $SHARE_USER)"

if [[ "$(uname -s)" == "Darwin" ]]; then
  if [[ -n "${SMB_PASS:-}" ]]; then
    mount_smbfs "//$SHARE_USER:$SMB_PASS@$HOST/$SHARE_NAME" "$MNT"
  else
    mount_smbfs "//$SHARE_USER@$HOST/$SHARE_NAME" "$MNT"
  fi
else
  command -v mount.cifs >/dev/null || {
    err "mount.cifs not found — install cifs-utils first: sudo apt install cifs-utils"
    exit 1
  }

  try_mount() {
    local host="$1"
    local opts="username=$SHARE_USER,vers=3.0,uid=$(id -u),gid=$(id -g),iocharset=utf8,file_mode=0755,dir_mode=0755"
    # Bounded so a host that accepts :445 but stalls SMB negotiation fails
    # fast instead of hanging forever; interactive runs get room to type the
    # SMB password at the mount.cifs prompt.
    local limit=20
    if [[ -z "${SMB_PASS:-}" ]]; then limit=90; fi
    if [[ -n "${SMB_PASS:-}" ]]; then
      sudo timeout -k 5 "$limit" mount -t cifs "//$host/$SHARE_NAME" "$MNT" -o "$opts,password=$SMB_PASS"
    else
      sudo timeout -k 5 "$limit" mount -t cifs "//$host/$SHARE_NAME" "$MNT" -o "$opts"
    fi
  }

  if ! try_mount "$HOST"; then
    # Clean up a possible half-mounted mountpoint from the killed attempt.
    if findmnt -M "$MNT" >/dev/null 2>&1; then sudo umount -l "$MNT"; fi
    if [[ -z "${TOWER_HOST:-}" && "$HOST" != "tower.ide-pogona.ts.net" ]]; then
      err "mount via $HOST failed — falling back to tower.ide-pogona.ts.net"
      HOST="tower.ide-pogona.ts.net"
      err "mounting //$HOST/$SHARE_NAME at $MNT (user $SHARE_USER)"
      try_mount "$HOST"
    else
      exit 1
    fi
  fi
fi

if [[ ! -d "$MNT/pokered" ]]; then
  err "warning: $MNT/pokered not found after mount — unexpected share layout"
fi
printf '%s\n' "$MNT"
