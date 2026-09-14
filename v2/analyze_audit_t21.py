#!/usr/bin/env python
"""Summarize a mem_audit_t21 run into a per-component budget table."""
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
d = json.loads(p.read_text())
cfg = d["config"]
spm = cfg["samples_per_mu"]

print(f"config: {cfg}")
print()

# per-key buffer bytes from the last pre_train breakdown
pre = next(b for b in reversed(d["breakdowns"]) if b["phase"] == "pre_train")
rb = pre["rollout_buffer"]
print(f"pre_train: {rb['buffer_type']} samples={rb['samples']} "
      f"chain_total={rb['chain_total_nbytes']:,} B "
      f"({rb['chain_total_nbytes']/rb['samples']:.0f} B/sample)")
if "obs_totals_nbytes" in rb:
    for k, v in sorted(rb["obs_totals_nbytes"].items(), key=lambda kv: -kv[1]):
        print(f"  obs.{k:16s} {v:>13,} B  {v/rb['samples']:>9.0f} B/sample")
    print(f"  round arrays     {rb['round_arrays_total_nbytes']:>13,} B  {rb['round_arrays_total_nbytes']/rb['samples']:>9.0f} B/sample")
    for k in ("values", "returns", "advantages"):
        r = rb[f"chain_concat_{k}"]
        print(f"  concat {k:9s} {r['nbytes']:>13,} B  {r['dtype']}")
    # per-round per-key dtype/shape from round0
    r0 = rb["round0"]
    for k, rec in r0["obs"].items():
        print(f"    round0 obs.{k:12s} dtype={rec['dtype']:8s} shape={rec['shape']}")
print()

# timeline
print("timeline:")
for row in d["timeline"]:
    print(f"  mu={row['mu']} r={row['round']} {row['phase']:22s} "
          f"pss={row['pss_kb']/1024:8.0f}MB anon={row['anon_kb']/1024:8.0f}MB "
          f"tree={row['tree_pss_mb']:8.0f}MB swap={row['swap_kb']/1024:5.0f}MB {row['note'][:60]}")
print()

# batches
if d["batches"]:
    obs_nb = [b["obs_nb"] for b in d["batches"]]
    pss = [b["pss_kb"] for b in d["batches"]]
    print(f"batches: n={len(d['batches'])} obs_nb min={min(obs_nb):,} max={max(obs_nb):,} "
          f"pss_at_batch min={min(pss)/1024:.0f} max={max(pss)/1024:.0f}MB")

# mallinfo2 fields are bytes
for b in d["breakdowns"]:
    if b["phase"] in ("pre_train", "post_train", "learn_end_post_gc"):
        m = b.get("mallinfo2", {})
        g = b.get("gc_stats_total_collected", 0)
        if m:
            print(f"  mallinfo2 {b['phase']:20s} heap_inuse(uordblks)={m.get('uordblks',0)/2**20:8.0f}MiB "
                  f"heap_free(fordblks)={m.get('fordblks',0)/2**20:8.0f}MiB "
                  f"mmap(hblkhd)={m.get('hblkhd',0)/2**20:8.0f}MiB "
                  f"gc_collected_total={g}")
