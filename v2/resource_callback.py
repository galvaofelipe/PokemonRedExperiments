import csv
import ctypes
import ctypes.util
import os
import platform
import subprocess
import threading
import time
from pathlib import Path

from stable_baselines3.common.callbacks import BaseCallback

GB_FPS = 59.727
CSV_FIELDS = (
    "wall_s",
    "timesteps",
    "instant_sps",
    "avg_sps",
    "game_s",
    "per_env_game_s",
    "per_env_speedup",
    "rss_mb",
    "footprint_mb",
    "cpu_pct",
    "n_procs",
)

# Per-platform semantics (columns keep their names; meanings differ — do NOT
# compare memory/cpu columns directly across platforms):
#   macOS: footprint_mb = phys_footprint (Activity Monitor semantics: resident +
#     compressed + iokit) via proc_pid_rusage; ps/rss underreports ~4.5x vs it.
#     cpu_pct = ps %cpu, a lifetime average (understates peaks).
#   Linux: footprint_mb = PSS sum over the tree (smaps_rollup; shared fork pages
#     split proportionally — RSS sums double-count them). cpu_pct = interval CPU
#     from /proc stat deltas between samples (100% = one core).
# rusage_info_v4 lays uuid[16] then 7 uint64 before resident/footprint.
_SYSTEM = platform.system()
_libproc = None
if _SYSTEM == "Darwin":
    try:
        _libproc = ctypes.CDLL(ctypes.util.find_library("proc"))
    except OSError:
        _libproc = None

_CLK_TCK = os.sysconf("SC_CLK_TCK") if _SYSTEM == "Linux" else 100


def _phys_footprint_mb(pid: int):
    if _libproc is None:
        return None
    buf = (ctypes.c_uint64 * 64)()  # rusage_info_v4 fits with room to spare
    if _libproc.proc_pid_rusage(pid, 4, ctypes.byref(buf)) != 0:
        return None
    return buf[9] / (1024.0 * 1024.0)


def _pss_mb(pid: int):
    """Linux PSS from /proc/<pid>/smaps_rollup; None if unreadable/gone."""
    try:
        with open(f"/proc/{pid}/smaps_rollup") as f:
            for line in f:
                if line.startswith("Pss:"):
                    return int(line.split()[1]) / 1024.0
    except (OSError, ValueError, IndexError):
        return None
    return None


def _proc_ticks(pid: int):
    """Linux utime+stime in clock ticks from /proc/<pid>/stat; None if gone."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            data = f.read()
    except OSError:
        return None
    # comm (field 2) is parenthesized and may itself contain spaces/parens.
    rest = data[data.rfind(")") + 1 :].split()
    try:
        return int(rest[11]) + int(rest[12])  # utime, stime (fields 14, 15)
    except (ValueError, IndexError):
        return None


def _parse_float(value: str) -> float:
    return float(value.replace(",", "."))


def process_tree_stats(root_pid: int, cpu_state: dict | None = None):
    """Return (rss_mb, footprint_mb, cpu_pct, n_procs) for root_pid and descendants.

    footprint_mb sums phys_footprint (Activity Monitor semantics) on macOS and
    PSS on Linux, falling back to rss on either. Summing phys_footprint may
    double-count pages shared between parent and children; PSS does not.

    cpu_pct sums ps %cpu (lifetime average) unless cpu_state is provided on
    Linux: pass the same dict across calls and cpu_pct becomes the tree's
    interval CPU since the previous call (100% = one core). The first call
    with a fresh dict establishes the baseline and reports 0.
    """
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    try:
        out = subprocess.check_output(
            ["ps", "-ax", "-o", "pid=,ppid=,rss=,%cpu="],
            text=True,
            env=env,
        )
    except (OSError, subprocess.CalledProcessError):
        return 0.0, 0.0, 0.0, 0

    by_pid = {}
    children = {}
    for line in out.strip().splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            pid, ppid, rss_kb = int(parts[0]), int(parts[1]), int(parts[2])
            cpu = _parse_float(parts[3])
        except ValueError:
            continue
        by_pid[pid] = (rss_kb, cpu)
        children.setdefault(ppid, []).append(pid)

    stack = [root_pid]
    seen = set()
    while stack:
        pid = stack.pop()
        if pid in seen or pid not in by_pid:
            continue
        seen.add(pid)
        stack.extend(children.get(pid, []))

    rss_kb = 0
    footprint_mb = 0.0
    cpu = 0.0
    for pid in seen:
        r, c = by_pid[pid]
        rss_kb += r
        if _SYSTEM == "Linux":
            fp = _pss_mb(pid)
        else:
            fp = _phys_footprint_mb(pid)
        footprint_mb += fp if fp is not None else r / 1024.0
        cpu += c

    if cpu_state is not None and _SYSTEM == "Linux":
        now = time.monotonic()
        ticks = {}
        for pid in seen:
            t = _proc_ticks(pid)
            if t is not None:
                ticks[pid] = t
        prev_t = cpu_state.get("t")
        prev = cpu_state.get("ticks", {})
        if prev_t is not None:
            dt = max(now - prev_t, 1e-6)
            cpu = sum(t - prev.get(pid, t) for pid, t in ticks.items()) / _CLK_TCK / dt * 100.0
        else:
            cpu = 0.0  # baseline sample; no interval to measure yet
        cpu_state["t"] = now
        cpu_state["ticks"] = ticks

    return rss_kb / 1024.0, footprint_mb, cpu, len(seen)


class ResourceCallback(BaseCallback):
    """Log RAM/CPU and wall-vs-game-time so a short run can size an overnight one.

    Samples on a daemon thread every interval_s, not in _on_step: rollout-only
    sampling is blind to the train() phase, which is where the accumulator's
    chained buffer peaks.
    """

    def __init__(self, log_dir, num_envs, action_freq, interval_s=30.0, verbose=0):
        super().__init__(verbose)
        self.log_path = Path(log_dir) / "resource_log.csv"
        self.summary_path = Path(log_dir) / "resource_summary.txt"
        self.num_envs = num_envs
        self.action_freq = action_freq
        self.interval_s = interval_s
        self.root_pid = os.getpid()
        self.t0 = None
        self.last_t = None
        self.last_steps = 0
        self.peak_rss_mb = 0.0
        self.peak_footprint_mb = 0.0
        self.peak_cpu = 0.0
        self.samples = []
        self._cpu_state: dict = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def _on_training_start(self):
        self.t0 = time.monotonic()
        self.last_t = self.t0
        self.last_steps = 0
        self.log_path.parent.mkdir(exist_ok=True)
        if not self.log_path.exists() or self.log_path.stat().st_size == 0:
            with self.log_path.open("w", newline="") as f:
                csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()
        self._write_row()
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

    def _sample_loop(self):
        while not self._stop.wait(self.interval_s):
            self._write_row()

    def _on_step(self) -> bool:
        return True

    def _on_training_end(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._write_row()
        self._write_summary()

    def _write_row(self):
        try:
            with self._lock:
                self._write_row_unsafe()
        except Exception as exc:
            print(f"[perf] skipped sample: {exc}", flush=True)

    def _write_row_unsafe(self):
        now = time.monotonic()
        wall_s = now - self.t0
        steps = int(self.model.num_timesteps)
        dt = max(now - self.last_t, 1e-6)
        instant_sps = (steps - self.last_steps) / dt
        avg_sps = steps / max(wall_s, 1e-6)
        game_s = steps * self.action_freq / GB_FPS
        per_env_game_s = game_s / max(self.num_envs, 1)
        per_env_speedup = per_env_game_s / max(wall_s, 1e-6)
        rss_mb, footprint_mb, cpu_pct, n_procs = process_tree_stats(self.root_pid, self._cpu_state)
        self.peak_rss_mb = max(self.peak_rss_mb, rss_mb)
        self.peak_footprint_mb = max(self.peak_footprint_mb, footprint_mb)
        self.peak_cpu = max(self.peak_cpu, cpu_pct)
        row = {
            "wall_s": f"{wall_s:.1f}",
            "timesteps": steps,
            "instant_sps": f"{instant_sps:.1f}",
            "avg_sps": f"{avg_sps:.1f}",
            "game_s": f"{game_s:.1f}",
            "per_env_game_s": f"{per_env_game_s:.1f}",
            "per_env_speedup": f"{per_env_speedup:.2f}",
            "rss_mb": f"{rss_mb:.1f}",
            "footprint_mb": f"{footprint_mb:.1f}",
            "cpu_pct": f"{cpu_pct:.1f}",
            "n_procs": n_procs,
        }
        with self.log_path.open("a", newline="") as f:
            csv.DictWriter(f, fieldnames=CSV_FIELDS).writerow(row)
        self.samples.append(
            {
                "wall_s": wall_s,
                "avg_sps": avg_sps,
                "rss_mb": rss_mb,
                "footprint_mb": footprint_mb,
                "cpu_pct": cpu_pct,
                "per_env_speedup": per_env_speedup,
                "timesteps": steps,
            }
        )
        if self.logger is not None:
            self.logger.record("perf/instant_sps", instant_sps)
            self.logger.record("perf/avg_sps", avg_sps)
            self.logger.record("perf/rss_mb", rss_mb)
            self.logger.record("perf/footprint_mb", footprint_mb)
            self.logger.record("perf/cpu_pct", cpu_pct)
            self.logger.record("perf/per_env_speedup", per_env_speedup)
            self.logger.record("perf/per_env_game_hours", per_env_game_s / 3600)
        print(
            f"[perf] wall={wall_s/60:.1f}m steps={steps} "
            f"sps={instant_sps:.0f} (avg {avg_sps:.0f}) "
            f"game/env={per_env_game_s/60:.1f}m ({per_env_speedup:.1f}x) "
            f"fp={footprint_mb:.0f}MB rss={rss_mb:.0f}MB cpu={cpu_pct:.0f}% procs={n_procs}",
            flush=True,
        )
        self.last_t = now
        self.last_steps = steps

    def _write_summary(self):
        if not self.samples:
            return
        last = self.samples[-1]
        if _SYSTEM == "Darwin":
            fp_note = "phys_footprint, ~= Activity Monitor"
            rss_note = "resident only; ~4.5x below footprint on macOS"
            cpu_note = "ps %cpu lifetime average; understates peaks"
        elif _SYSTEM == "Linux":
            fp_note = "PSS sum over tree; shared fork pages split proportionally"
            rss_note = "sum of per-process RSS; double-counts shared fork pages"
            cpu_note = "interval CPU between samples"
        else:
            fp_note = rss_note = cpu_note = "rss fallback"
        threads = os.cpu_count() or "?"
        lines = [
            f"wall_minutes={last['wall_s'] / 60:.1f}",
            f"timesteps={last['timesteps']}",
            f"avg_sps={last['avg_sps']:.1f}",
            f"per_env_speedup={last['per_env_speedup']:.2f}x  # game-seconds per env / wall-seconds",
            f"peak_footprint_mb={self.peak_footprint_mb:.1f}  # {fp_note}",
            f"peak_rss_mb={self.peak_rss_mb:.1f}  # {rss_note}",
            f"peak_cpu_pct={self.peak_cpu:.1f}  # {cpu_note}; 100% = one core, host has {threads} threads",
            f"num_envs={self.num_envs}",
            f"action_freq={self.action_freq}",
            "",
            "Overnight sketch (linear scale from this run):",
            f"  24h timesteps ~= {last['avg_sps'] * 86400:.0f}",
            f"  24h game per env ~= {last['per_env_speedup'] * 24:.1f} hours",
            f"  footprint if envs stay at {self.num_envs}: ~{self.peak_footprint_mb:.0f}MB",
            f"  footprint per env ~= {self.peak_footprint_mb / max(self.num_envs, 1):.0f}MB",
        ]
        text = "\n".join(lines) + "\n"
        self.summary_path.write_text(text)
        print("\n" + text, flush=True)
