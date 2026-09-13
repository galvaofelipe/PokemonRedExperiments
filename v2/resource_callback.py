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

# macOS: ps/rss underreports ~4.5x vs Activity Monitor, whose "Memory" column is
# phys_footprint (resident + compressed + iokit). proc_pid_rusage(RUSAGE_INFO_V4)
# exposes it; rusage_info_v4 lays uuid[16] then 7 uint64 before resident/footprint.
_libproc = None
if platform.system() == "Darwin":
    try:
        _libproc = ctypes.CDLL(ctypes.util.find_library("proc"))
    except OSError:
        _libproc = None


def _phys_footprint_mb(pid: int):
    if _libproc is None:
        return None
    buf = (ctypes.c_uint64 * 64)()  # rusage_info_v4 fits with room to spare
    if _libproc.proc_pid_rusage(pid, 4, ctypes.byref(buf)) != 0:
        return None
    return buf[9] / (1024.0 * 1024.0)


def _parse_float(value: str) -> float:
    return float(value.replace(",", "."))


def process_tree_stats(root_pid: int):
    """Return (rss_mb, footprint_mb, cpu_pct, n_procs) for root_pid and descendants.

    footprint_mb sums phys_footprint (Activity Monitor semantics) on macOS and
    falls back to rss elsewhere. Summing footprints may double-count pages
    shared between parent and children.
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
    rss_kb = 0
    footprint_mb = 0.0
    cpu = 0.0
    while stack:
        pid = stack.pop()
        if pid in seen or pid not in by_pid:
            continue
        seen.add(pid)
        r, c = by_pid[pid]
        rss_kb += r
        fp = _phys_footprint_mb(pid)
        footprint_mb += fp if fp is not None else r / 1024.0
        cpu += c
        stack.extend(children.get(pid, []))
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
        rss_mb, footprint_mb, cpu_pct, n_procs = process_tree_stats(self.root_pid)
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
        lines = [
            f"wall_minutes={last['wall_s'] / 60:.1f}",
            f"timesteps={last['timesteps']}",
            f"avg_sps={last['avg_sps']:.1f}",
            f"per_env_speedup={last['per_env_speedup']:.2f}x  # game-seconds per env / wall-seconds",
            f"peak_footprint_mb={self.peak_footprint_mb:.1f}  # phys_footprint, ~= Activity Monitor",
            f"peak_rss_mb={self.peak_rss_mb:.1f}  # resident only; ~4.5x below footprint on macOS",
            f"peak_cpu_pct={self.peak_cpu:.1f}  # 100% = one core; this Mac has 10",
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
