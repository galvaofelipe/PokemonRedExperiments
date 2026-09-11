#!/usr/bin/env bash
# Sequential job queue for baseline_fast_v2.py. One training process at a time.
# Bash 3.2 compatible (macOS /bin/bash).

set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

JOBS="$ROOT/jobs"
LOGS="$ROOT/logs"
LOCK="$JOBS/.queue.lock"

if [[ -x "$ROOT/../.venv/bin/python" ]]; then
  PYTHON="$ROOT/../.venv/bin/python"
else
  PYTHON="python"
fi

iso_now() {
  "$PYTHON" -c "from datetime import datetime; print(datetime.now().astimezone().isoformat())"
}

mkdir -p "$JOBS/done" "$JOBS/failed" "$LOGS"

if [[ -f "$LOCK" ]]; then
  oldpid="$(cat "$LOCK" 2>/dev/null || true)"
  if [[ -n "${oldpid}" ]] && kill -0 "$oldpid" 2>/dev/null; then
    echo "queue already running (pid $oldpid); refuse second instance" >&2
    exit 1
  fi
  echo "stale lock (pid ${oldpid:-unknown}), replacing" >&2
fi
echo $$ > "$LOCK"
cleanup() { rm -f "$LOCK"; }
trap cleanup EXIT

shopt -s nullglob
job_files=("$JOBS"/*.json)
if (( ${#job_files[@]} == 0 )); then
  echo "jobs/ is empty; nothing to run"
  exit 0
fi

json_name() {
  "$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "$1"
}

# Sets global JOB_ARGS from JSON args array (NUL-delimited; no eval).
load_job_args() {
  JOB_ARGS=()
  while IFS= read -r -d '' arg; do
    JOB_ARGS+=("$arg")
  done < <("$PYTHON" -c '
import json, sys
args = json.load(open(sys.argv[1]))["args"]
if args:
    sys.stdout.buffer.write(b"\0".join(a.encode() for a in args) + b"\0")
' "$1")
}

# Snapshot + sort up front. Do not iterate a stdin pipe: children inherit it,
# and baseline_fast_v2.py reads stdin for a checkpoint path.
old_ifs="$IFS"
IFS=$'\n'
sorted_jobs=($(printf '%s\n' "${job_files[@]}" | LC_ALL=C sort))
IFS="$old_ifs"

for job in "${sorted_jobs[@]}"; do
  [[ -f "$job" ]] || continue
  name="$(json_name "$job")"
  load_job_args "$job"

  start="$(iso_now)"
  {
    echo "running"
    echo "start: $start"
    echo "command: $PYTHON $ROOT/baseline_fast_v2.py ${JOB_ARGS[*]}"
  } > "$JOBS/${name}.status"

  echo "starting job $name"
  set +e
  "$PYTHON" "$ROOT/baseline_fast_v2.py" "${JOB_ARGS[@]}" \
    </dev/null >> "$LOGS/${name}.log" 2>&1
  rc=$?
  end="$(iso_now)"

  if [[ $rc -eq 0 ]]; then
    {
      echo "done"
      echo "end: $end"
    } >> "$JOBS/${name}.status"
    mv "$job" "$JOBS/done/"
    echo "job $name done"
  else
    {
      echo "failed"
      echo "exit: $rc"
      echo "end: $end"
    } >> "$JOBS/${name}.status"
    mv "$job" "$JOBS/failed/"
    echo "job $name failed (exit $rc); continuing" >&2
  fi
done

echo "queue finished"
