#!/usr/bin/env python
"""Ticket-15 table: per-seed metrics at the 2M cutoff, ticket-05 format.

Reproduces the t05 table (validation) and then applies the same extraction
to the t15 accumulator cell. flags = event / 2 (reward_scale 0.5).

Usage: cell_table.py SESSION_DIR [SESSION_DIR ...]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tb_extract import load_series

CUTOFF = 2_000_000


def at_cutoff(series, step_cut=CUTOFF):
    """Last value at step <= cutoff, and max over the same window."""
    pts = [(s, v) for s, v in series if s <= step_cut]
    if not pts:
        return None, None
    return pts[-1][1], max(v for _, v in pts)


def metrics(sess: str) -> dict:
    s = load_series(sess)
    out = {"sess": sess}
    flags_at, flags_mt = at_cutoff(s["env_stats_max/event"])
    out["flags"] = None if flags_at is None else flags_at / 2
    out["flags_mt"] = None if flags_mt is None else flags_mt / 2
    for col, tag in [
        ("coord", "env_stats_max/coord_count"),
        ("levels", "env_stats_max/levels_sum"),
        ("maps", "env_stats_max/unique_maps"),
        ("dex", "env_stats_max/dex_seen"),
        ("mmp", "env_stats_max/max_map_progress"),
    ]:
        at, mt = at_cutoff(s[tag])
        out[col] = at
        out[col + "_mt"] = mt
    # ticket-05 convention: deaths column is the series max within the window
    _, out["deaths"] = at_cutoff(s["env_stats_max/deaths"])
    wipes = [v for st, v in s.get("episode/end_wipe", []) if st <= CUTOFF and v >= 0.5]
    out["wipes"] = len(wipes)
    return out


def main():
    rows = [metrics(sess) for sess in sys.argv[1:]]
    hdr = ["sess", "flags", "coord", "levels", "maps", "dex", "mmp", "deaths", "wipes"]
    print("\t".join(hdr))
    for r in rows:
        print("\t".join(str(r[h]) for h in hdr))
    print("\n# max-along-time (series max <= cutoff)")
    print("\t".join(["sess", "flags_mt", "coord_mt"]))
    for r in rows:
        print("\t".join([r["sess"], str(r["flags_mt"]), str(r["coord_mt"])]))


if __name__ == "__main__":
    main()
