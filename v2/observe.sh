#!/usr/bin/env bash
# Brings up the monitoring stack for the training queue:
#   - watch_progress.py  (queue + SPS/progress page) on :8765
#   - tensorboard        (training metrics)          on :6006
# TensorBoard watches .tb_logs/, a symlink farm with one link per queued job's
# session dir (jobs/*.json); dirs are pre-created so runs that haven't started
# yet appear once they do. (Plain --logdir recurses; --logdir_spec does not.)
# Ctrl+C stops both. Bash 3.2 compatible (macOS /bin/bash).

set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/../.venv/bin/python" ]]; then
  PYTHON="$ROOT/../.venv/bin/python"
  TB="$ROOT/../.venv/bin/tensorboard"
else
  PYTHON="python"
  TB="tensorboard"
fi

PROGRESS_PORT="${PROGRESS_PORT:-8765}"
TB_PORT="${TB_PORT:-6006}"

# name<TAB>session-path for each job, queued or already done (done jobs keep
# their runs visible in tensorboard for comparison)
jobs_tsv="$("$PYTHON" - <<'EOF'
import json
from pathlib import Path

def arg_map(args):
    out = {}
    i = 0
    while i < len(args):
        key = args[i]
        if not key.startswith("--"):
            i += 1
            continue
        if i + 1 < len(args) and not args[i + 1].startswith("--"):
            out[key] = args[i + 1]
            i += 2
        else:
            out[key] = True
            i += 1
    return out

jobs = Path("jobs")
paths = sorted(jobs.glob("*.json")) + sorted((jobs / "done").glob("*.json"))
for path in paths:
    job = json.loads(path.read_text())
    session = arg_map(job.get("args") or []).get("--session-path", "")
    if session:
        print(f"{job['name']}\t{session}")

# include the last smoke for immediate data, if still around
smoke = Path("runs_smoke_15m_v2")
if smoke.is_dir():
    print(f"smoke15m\t{smoke}")
EOF
)"

if [[ -z "${jobs_tsv}" ]]; then
  echo "no queued jobs found in jobs/*.json; tensorboard will have nothing to watch" >&2
fi

# TensorBoard's --logdir_spec does not recurse into subdirectories, and our
# event files live in <session>/poke_ppo_1 and <session>/histogram. So stage a
# symlink farm: .tb_logs/<job> -> <session dir>, and point plain --logdir at it.
TB_LOGS="$ROOT/.tb_logs"
mkdir -p "$TB_LOGS"

old_ifs="$IFS"
IFS=$'\n'
for line in ${jobs_tsv}; do
  name="${line%%	*}"
  session="${line#*	}"
  mkdir -p "$ROOT/$session"
  ln -sfn "$ROOT/$session" "$TB_LOGS/$name"
done
IFS="$old_ifs"

# drop stale links from jobs no longer queued
for link in "$TB_LOGS"/*; do
  [[ -L "$link" ]] || continue
  target="$(readlink "$link")"
  [[ -d "$target" ]] || rm "$link"
done

pids=()
cleanup() {
  for pid in "${pids[@]:-}"; do
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null
  done
}
trap cleanup EXIT INT TERM

"$PYTHON" "$ROOT/watch_progress.py" --port "$PROGRESS_PORT" &
pids+=($!)

if [[ -n "${jobs_tsv}" ]]; then
  "$TB" --logdir "$TB_LOGS" --port "$TB_PORT" --reload_interval 15 &
  pids+=($!)
fi

echo "progress page: http://127.0.0.1:$PROGRESS_PORT"
[[ -n "${jobs_tsv}" ]] && echo "tensorboard:   http://127.0.0.1:$TB_PORT  (via $TB_LOGS symlink farm)"
echo "Ctrl+C to stop both"
wait
