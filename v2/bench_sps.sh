#!/usr/bin/env bash
# SPS-per-env benchmark for baseline_fast_v2.py.
# Runs a short training slice at several physical env counts and records
# avg_sps / peak memory / peak cpu from ResourceCallback's resource_summary.txt.
#
# Usage:  ./bench_sps.sh [env_counts...]     (default: 1 2 4 8 12 16 24 32)
# Output: bench/bench_results.csv + per-run logs under bench/e<N>/

set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PYTHON="$ROOT/../.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON=python

COUNTS=("${@:-1 2 4 8 12 16 24 32}")
# Allow "./bench_sps.sh 8 16" style args (the default expansion above only
# covers the no-arg case).
if (( $# > 0 )); then COUNTS=("$@"); fi

OUT="$ROOT/bench"
mkdir -p "$OUT"
RESULTS="$OUT/bench_results.csv"
if [[ ! -f "$RESULTS" ]]; then
  echo "envs,total_steps,wall_min,avg_sps,sps_per_env,peak_rss_mb,peak_cpu_pct" > "$RESULTS"
fi

for n in "${COUNTS[@]}"; do
  steps=$((4 * 2560 * n))   # 4 PPO updates worth of timesteps
  sess="bench/e${n}"
  echo "=== bench: ${n} envs, ${steps} steps ==="
  "$PYTHON" "$ROOT/baseline_fast_v2.py" \
    --num-envs "$n" \
    --n-steps 2560 \
    --total-timesteps "$steps" \
    --seed 0 \
    --no-stream \
    --session-path "$sess" \
    </dev/null > "$OUT/e${n}.log" 2>&1
  rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "  run failed (exit $rc); see $OUT/e${n}.log"
    continue
  fi
  summary="$sess/resource_summary.txt"
  avg="$(grep -oP '^avg_sps=\K[0-9.]+' "$summary" || echo '?')"
  rss="$(grep -oP '^peak_rss_mb=\K[0-9.]+' "$summary" || echo '?')"
  cpu="$(grep -oP '^peak_cpu_pct=\K[0-9.]+' "$summary" || echo '?')"
  wall="$(grep -oP '^wall_minutes=\K[0-9.]+' "$summary" || echo '?')"
  spe="$(awk -v a="$avg" -v n="$n" 'BEGIN{printf "%.1f", a/n}')"
  echo "${n},${steps},${wall},${avg},${spe},${rss},${cpu}" >> "$RESULTS"
  echo "  avg_sps=${avg}  sps/env=${spe}  peak_rss=${rss}MB  peak_cpu=${cpu}%  wall=${wall}m"
done

echo
echo "results: $RESULTS"
column -s, -t "$RESULTS" 2>/dev/null || cat "$RESULTS"
