#!/usr/bin/env python
"""External memory watch for a training run: system-wide + process-tree view
from OUTSIDE the training process (independent sampler over /proc).

Usage: mem_watch.py <root_pid> <interval_s> <out_csv>
Columns: epoch, sys_used_mb (MemTotal-MemAvailable), sys_available_mb,
         swap_used_mb, tree_pss_mb, tree_rss_mb
"""
import os
import subprocess
import sys
import time
from pathlib import Path

root = int(sys.argv[1])
interval = float(sys.argv[2])
out = Path(sys.argv[3])


def meminfo():
    d = {}
    for line in open("/proc/meminfo"):
        k, _, rest = line.partition(":")
        d[k] = int(rest.strip().split()[0])  # kB
    return d


def tree_pids(root_pid):
    ps = subprocess.check_output(
        ["ps", "-ax", "-o", "pid=,ppid="], text=True, env={"LC_ALL": "C", "PATH": os.environ["PATH"]}
    )
    kids = {}
    for line in ps.splitlines():
        p = line.split()
        if len(p) == 2:
            kids.setdefault(int(p[1]), []).append(int(p[0]))
    seen, stack = set(), [root_pid]
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        stack.extend(kids.get(pid, []))
    return seen


def field_kb(pid, fname, prefix):
    try:
        for line in open(f"/proc/{pid}/{fname}"):
            if line.startswith(prefix):
                return int(line.split()[1])
    except OSError:
        pass
    return 0


with out.open("w") as f:
    f.write("epoch,sys_used_mb,sys_available_mb,swap_used_mb,tree_pss_mb,tree_rss_mb\n")
    while True:
        try:
            os.kill(root, 0)
        except OSError:
            break
        mi = meminfo()
        pids = tree_pids(root)
        pss = sum(field_kb(p, "smaps_rollup", "Pss:") for p in pids) / 1024
        rss = sum(field_kb(p, "status", "VmRSS:") for p in pids) / 1024
        used = (mi["MemTotal"] - mi["MemAvailable"]) / 1024
        avail = mi["MemAvailable"] / 1024
        swap = (mi["SwapTotal"] - mi["SwapFree"]) / 1024
        f.write(f"{time.time():.0f},{used:.0f},{avail:.0f},{swap:.0f},{pss:.0f},{rss:.0f}\n")
        f.flush()
        time.sleep(interval)
