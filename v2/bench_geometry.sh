#!/usr/bin/env bash
# Geometry benchmark: the 3 Mac-tested cells as-configured + accumulator
# variants across logical/physical splits. Each cell runs 2 mega-updates
# (2 x n_steps x logical steps; g2560 ran 327680 = 16 stock updates), so
# ResourceCallback's sampling thread sees the train()-phase memory peak at
# least twice.
#
# Usage:  ./bench_geometry.sh [cell...]   (default: original four)
# Output: bench/bench_geometry.csv + per-cell logs/sessions under bench/geo_*
#
# Cells:
#   g2560      8 logical / 8 physical,  n_steps 2560   (t05 cell A, status quo)
#   g20480     8 logical / 8 physical,  n_steps 20480  (t05 cell B)
#   acc64_p8   64 logical / 8 physical, n_steps 2560   (t16 acc64 as-configured)
#   acc64_p16  64 logical / 16 physical, n_steps 2560  (RAM/throughput variant)
#   acc40_p8   40 logical / 8 physical  (buffer ~102k samples)
#   acc40_p20  40 logical / 20 physical (same buffer, more rollout width)
#   acc48_p16  48 logical / 16 physical (buffer ~123k samples)
#   acc80_p16  80 logical / 16 physical (buffer ~205k — expect RAM pressure)
#   acc80_p20  80 logical / 20 physical (same buffer, more rollout width)
#
# memory columns come from the platform-correct ResourceCallback (Linux: PSS
# footprint + interval CPU); do NOT compare them against Mac-measured numbers.

set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PYTHON="$ROOT/../.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON=python

MAX_STEPS=16384

OUT="$ROOT/bench"
mkdir -p "$OUT"
RESULTS="$OUT/bench_geometry.csv"
if [[ ! -f "$RESULTS" ]]; then
  echo "geometry,logical,physical,n_steps,total_steps,wall_min,avg_sps,peak_rss_mb,peak_footprint_mb,peak_cpu_pct" > "$RESULTS"
fi

run_cell() {
  local name="$1" logical="$2" physical="$3" nsteps="$4" total="$5"
  local sess="bench/geo_${name}"
  echo "=== geometry ${name}: logical=${logical} physical=${physical} n_steps=${nsteps} total=${total} ==="
  local extra=()
  if (( physical != logical )); then
    extra=(--physical-envs "$physical")
  fi
  # save_freq counts vec-steps, not timesteps; =total means checkpointing
  # never fires during the bench (intended — benches need no checkpoints).
  "$PYTHON" "$ROOT/baseline_fast_v2.py" \
    --num-envs "$logical" "${extra[@]}" \
    --n-steps "$nsteps" \
    --max-steps "$MAX_STEPS" \
    --total-timesteps "$total" \
    --save-freq "$total" \
    --seed 0 --no-stream \
    --session-path "$sess" \
    </dev/null > "$OUT/geo_${name}.log" 2>&1
  local rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "  run failed (exit $rc); see $OUT/geo_${name}.log"
    return
  fi
  local summary="$sess/resource_summary.txt"
  local wall avg rss fp cpu
  wall="$(grep -oP '^wall_minutes=\K[0-9.]+' "$summary" || echo '?')"
  avg="$(grep -oP '^avg_sps=\K[0-9.]+' "$summary" || echo '?')"
  rss="$(grep -oP '^peak_rss_mb=\K[0-9.]+' "$summary" || echo '?')"
  fp="$(grep -oP '^peak_footprint_mb=\K[0-9.]+' "$summary" || echo '?')"
  cpu="$(grep -oP '^peak_cpu_pct=\K[0-9.]+' "$summary" || echo '?')"
  echo "${name},${logical},${physical},${nsteps},${total},${wall},${avg},${rss},${fp},${cpu}" >> "$RESULTS"
  echo "  avg_sps=${avg}  peak_rss=${rss}MB  peak_footprint=${fp}MB  peak_cpu=${cpu}%  wall=${wall}m"
}

ALL_CELLS=(g2560 g20480 acc64_p8 acc64_p16)
if (( $# > 0 )); then CELLS=("$@"); else CELLS=("${ALL_CELLS[@]}"); fi

for cell in "${CELLS[@]}"; do
  case "$cell" in
    g2560)     run_cell g2560 8 8 2560 327680 ;;
    g20480)    run_cell g20480 8 8 20480 327680 ;;
    acc64_p8)  run_cell acc64_p8 64 8 2560 327680 ;;
    acc64_p16) run_cell acc64_p16 64 16 2560 327680 ;;
    acc40_p8)  run_cell acc40_p8 40 8 2560 204800 ;;
    acc40_p20) run_cell acc40_p20 40 20 2560 204800 ;;
    acc48_p16) run_cell acc48_p16 48 16 2560 245760 ;;
    acc80_p16) run_cell acc80_p16 80 16 2560 409600 ;;
    acc80_p20) run_cell acc80_p20 80 20 2560 409600 ;;
    *) echo "unknown cell: $cell (known: ${ALL_CELLS[*]} acc40_p8 acc40_p20 acc48_p16 acc80_p16 acc80_p20)" ;;
  esac
done

echo
echo "results: $RESULTS"
column -s, -t "$RESULTS" 2>/dev/null || cat "$RESULTS"
