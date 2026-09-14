#!/usr/bin/env python
"""Ticket 21 — RAM audit of the accumulator (measurement only, no behavior change).

Runs short instrumented AccumulatingPPO trainings and records, per phase:
- live rollout-buffer nbytes broken down per obs key / array (dtype, shape)
- /proc/self/smaps_rollup (Rss/Pss/Anonymous/Swap) for the parent process
- tree PSS (parent + SubprocVecEnv children) via resource_callback.process_tree_stats
- per-batch gather nbytes and PSS sampled during train()
- glibc mallinfo2 (heap in-use vs free) for fragmentation attribution

Production behavior is untouched: this standalone script subclasses
AccumulatingPPO with measurement wrappers only. Run from anywhere; it chdirs
to v2/ itself (events.json is opened relative to cwd).

    .venv/bin/python v2/mem_audit_t21.py --tag small \
        --num-envs 8 --physical-envs 4 --n-steps 256 --total-timesteps 8192

Outputs land in v2/runs_scratch_t21_<tag>/ (audit_timeline.csv, audit_breakdown.json).
"""

import argparse
import ctypes
import gc
import json
import os
import sys
import threading
import time
import types
from pathlib import Path

V2_DIR = Path(__file__).resolve().parent
os.chdir(V2_DIR)  # events.json, init.state, ROM paths are cwd-relative
sys.path.insert(0, str(V2_DIR))

import numpy as np
from stable_baselines3.common.callbacks import CallbackList
from stable_baselines3.common.vec_env import SubprocVecEnv

from accumulator_ppo import AccumulatingPPO, ChainedRolloutBuffer
from baseline_fast_v2 import make_env
from resource_callback import process_tree_stats


# ---------------------------------------------------------------- sampling

class Mallinfo2(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_size_t)
        for name in (
            "arena", "ordblks", "smblks", "hblks", "hblkhd",
            "usmblks", "fsmblks", "uordblks", "fordblks", "keepcost",
        )
    ]


try:
    _libc = ctypes.CDLL("libc.so.6")
    _libc.mallinfo2.restype = Mallinfo2
except OSError:
    _libc = None


def mallinfo2():
    if _libc is None:
        return {}
    m = _libc.mallinfo2()
    return {name: getattr(m, name) for name, _ in Mallinfo2._fields_}


def smaps_rollup():
    out = {}
    try:
        with open("/proc/self/smaps_rollup") as f:
            for line in f:
                parts = line.split()
                key = parts[0].rstrip(":")
                if key in (
                    "Rss", "Pss", "Shared_Clean", "Shared_Dirty",
                    "Private_Clean", "Private_Dirty", "Anonymous",
                    "LazyFree", "Swap", "SwapPss",
                ):
                    out[key] = int(parts[1])  # kB
    except OSError:
        pass
    return out


class PeakSampler(threading.Thread):
    """Fast PSS/RSS sampler to catch transients between phase checkpoints."""

    def __init__(self, interval_s=0.05):
        super().__init__(daemon=True)
        self.interval_s = interval_s
        self._stop_evt = threading.Event()
        self.peak = {}
        self.samples = 0

    def run(self):
        while not self._stop_evt.wait(self.interval_s):
            snap = smaps_rollup()
            self.samples += 1
            if snap.get("Pss", 0) > self.peak.get("Pss", 0):
                self.peak = snap

    def stop(self):
        self._stop_evt.set()
        self.join(timeout=5)


# ---------------------------------------------------------------- records

TIMELINE = []   # rows for audit_timeline.csv
BREAKDOWN = []  # full dumps for audit_breakdown.json
MU_STATE = {"mu": 0, "round": 0, "tag": ""}
NO_BATCH_WRAP = False  # set by --no-batch-wrap: disables the get() monkeypatch


def _array_rec(arr):
    return {
        "dtype": str(arr.dtype),
        "shape": list(arr.shape),
        "nbytes": int(arr.nbytes),
    }


def chain_breakdown(chain):
    """nbytes breakdown of a stock buffer or a ChainedRolloutBuffer."""
    rec = {"buffer_type": type(chain).__name__}
    if isinstance(chain, ChainedRolloutBuffer):
        obs_totals = {}
        grand = 0
        for i, buf in enumerate(chain.buffers):
            rd = {"obs": {}, "arrays": {}}
            for key, arr in buf.observations.items():
                rd["obs"][key] = _array_rec(arr)
                obs_totals[key] = obs_totals.get(key, 0) + arr.nbytes
                grand += arr.nbytes
            for attr in ("actions", "rewards", "returns", "episode_starts",
                         "values", "log_probs", "advantages"):
                arr = getattr(buf, attr)
                rd["arrays"][attr] = _array_rec(arr)
                grand += arr.nbytes
            rec[f"round{i}"] = rd
        rec["obs_totals_nbytes"] = obs_totals
        rec["round_arrays_total_nbytes"] = grand - sum(obs_totals.values())
        for attr in ("values", "returns", "advantages"):
            arr = getattr(chain, attr)
            rec[f"chain_concat_{attr}"] = _array_rec(arr)
            grand += arr.nbytes
        rec["chain_total_nbytes"] = grand
        rec["n_rounds"] = len(chain.buffers)
        rec["samples"] = chain.buffer_size * chain.n_envs
    else:
        for key, arr in chain.observations.items():
            rec[f"obs.{key}"] = _array_rec(arr)
        for attr in ("actions", "rewards", "returns", "episode_starts",
                     "values", "log_probs", "advantages"):
            rec[attr] = _array_rec(getattr(chain, attr))
        rec["chain_total_nbytes"] = sum(
            v["nbytes"] for v in rec.values() if isinstance(v, dict)
        )
        rec["samples"] = chain.buffer_size * chain.n_envs
    return rec


def record(phase, model=None, note=""):
    smap = smaps_rollup()
    rss_mb, tree_pss_mb, _, n_procs = process_tree_stats(os.getpid())
    row = {
        "t": round(time.monotonic(), 3),
        "phase": phase,
        "mu": MU_STATE["mu"],
        "round": MU_STATE["round"],
        "pss_kb": smap.get("Pss", 0),
        "rss_kb": smap.get("Rss", 0),
        "anon_kb": smap.get("Anonymous", 0),
        "swap_kb": smap.get("Swap", 0),
        "tree_pss_mb": round(tree_pss_mb, 1),
        "tree_rss_mb": round(rss_mb, 1),
        "n_procs": n_procs,
        "note": note,
    }
    TIMELINE.append(row)
    if model is not None:
        entry = {"phase": phase, "timeline_row": row, "mallinfo2": mallinfo2(),
                 "gc_counts": gc.get_count(),
                 "gc_stats_total_collected": sum(s.get("collected", 0) for s in gc.get_stats())}
        chain = getattr(model, "rollout_buffer", None)
        if chain is not None:
            entry["rollout_buffer"] = chain_breakdown(chain)
            entry["policy_params"] = sum(p.numel() for p in model.policy.parameters())
        BREAKDOWN.append(entry)
    print(
        f"[audit] {phase:24s} mu={MU_STATE['mu']} r={MU_STATE['round']} "
        f"pss={row['pss_kb']/1024:8.0f}MB anon={row['anon_kb']/1024:8.0f}MB "
        f"tree_pss={tree_pss_mb:8.0f}MB swap={row['swap_kb']/1024:6.0f}MB {note}",
        flush=True,
    )
    return row


# ---------------------------------------------------------------- audited PPO

class AuditPPO(AccumulatingPPO):
    """AccumulatingPPO wrapped with measurement-only hooks."""

    peak_sampler = None
    batch_records = []

    def learn(self, total_timesteps, callback=None, **kwargs):
        self.peak_sampler = PeakSampler()
        self.peak_sampler.start()
        record("learn_start", self)
        try:
            return super().learn(total_timesteps, callback=callback, **kwargs)
        finally:
            self.peak_sampler.stop()
            record("learn_end_pre_gc", self,
                   f"peak_sampler={self.peak_sampler.peak.get('Pss', 0)/1024:.0f}MB "
                   f"over {self.peak_sampler.samples} samples")
            gc.collect()
            record("learn_end_post_gc", self)

    def collect_rollouts(self, env, callback, rollout_buffer, n_rollout_steps):
        MU_STATE["round"] += 1
        ret = super().collect_rollouts(env, callback, rollout_buffer, n_rollout_steps)
        record("post_collect_round", self,
               f"round_buffer={rollout_buffer.buffer_size * rollout_buffer.n_envs} samples "
               f"nbytes={sum(a.nbytes for a in rollout_buffer.observations.values()):,}")
        return ret

    def train(self):
        MU_STATE["mu"] += 1
        MU_STATE["round"] = 0
        # learn() already reassigned self.rollout_buffer to the new
        # ChainedRolloutBuffer (accumulator_ppo.py:159) before calling us; the
        # previous MU's chain is dead from here on. The last
        # post_collect_round row captured the double-alive window.
        chain = self.rollout_buffer
        record("pre_train", self,
               f"chain samples={chain.buffer_size * chain.n_envs}")
        if not NO_BATCH_WRAP:
            self._audit_wrap_get(chain)
        t0 = time.monotonic()
        ret = super().train()
        dt = time.monotonic() - t0
        record("post_train", self, f"train took {dt:.1f}s")
        return ret

    def _audit_wrap_get(self, chain):
        """Measure per-batch gather nbytes + PSS at each batch during train."""
        if not isinstance(chain, ChainedRolloutBuffer):
            return
        orig_get = chain.get
        batch_records = self.batch_records

        def audited_get(batch_size=None):
            for batch in orig_get(batch_size):
                obs_nb = sum(
                    t.numel() * t.element_size() for t in batch.observations.values()
                )
                rest_nb = sum(
                    t.numel() * t.element_size()
                    for t in (batch.actions, batch.old_values, batch.old_log_prob,
                              batch.advantages, batch.returns)
                )
                smap = smaps_rollup()
                batch_records.append({
                    "mu": MU_STATE["mu"],
                    "batch_size": int(batch.actions.shape[0]),
                    "obs_nb": obs_nb,
                    "rest_nb": rest_nb,
                    "pss_kb": smap.get("Pss", 0),
                    "rss_kb": smap.get("Rss", 0),
                    "anon_kb": smap.get("Anonymous", 0),
                })
                yield batch

        chain.get = types.MethodType(lambda self_, bs=None: audited_get(bs), chain)


# ---------------------------------------------------------------- runner

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tag", required=True)
    p.add_argument("--num-envs", type=int, default=8)
    p.add_argument("--physical-envs", type=int, default=4)
    p.add_argument("--n-steps", type=int, default=256)
    p.add_argument("--total-timesteps", type=int, default=8192)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--no-batch-wrap", action="store_true",
                   help="skip the ChainedRolloutBuffer.get() monkeypatch "
                        "(control run: detects measurement-induced retention)")
    args = p.parse_args()

    global NO_BATCH_WRAP
    NO_BATCH_WRAP = args.no_batch_wrap

    physical = args.physical_envs
    rounds = args.num_envs // physical
    assert args.num_envs % physical == 0
    MU_STATE["tag"] = args.tag

    sess = Path(f"runs_scratch_t21_{args.tag}")
    sess.mkdir(exist_ok=True)

    print(
        f"[audit] logical={args.num_envs} physical={physical} rounds={rounds} "
        f"n_steps={args.n_steps} samples/MU={args.n_steps * args.num_envs} "
        f"total={args.total_timesteps}",
        flush=True,
    )

    env_config = {
        "headless": True,
        "save_final_state": False,
        "early_stop": False,
        "early_stop_survival": 0.05,
        "action_freq": 24,
        "init_state": "../init.state",
        "max_steps": 2048 * 80,
        "print_rewards": False,
        "save_video": False,
        "fast_video": True,
        "session_path": sess,
        "gb_path": "../PokemonRed.gb",
        "debug": False,
        "reward_scale": 0.5,
        "explore_weight": 0.25,
    }

    env = SubprocVecEnv([make_env(i, env_config, seed=args.seed, stream=False)
                         for i in range(physical)])

    model = AuditPPO(
        "MultiInputPolicy",
        env,
        verbose=1,
        n_steps=args.n_steps,
        batch_size=512,
        n_epochs=1,
        gamma=0.997,
        ent_coef=0.01,
        tensorboard_log=sess,
        accumulation_rounds=rounds,
    )
    print(f"[audit] torch threads={__import__('torch').get_num_threads()}", flush=True)
    record("model_built", model)

    try:
        model.learn(
            total_timesteps=args.total_timesteps,
            callback=CallbackList([]),
            tb_log_name="poke_ppo",
        )
    finally:
        out_csv = sess / "audit_timeline.csv"
        with out_csv.open("w") as f:
            cols = ["t", "phase", "mu", "round", "pss_kb", "rss_kb", "anon_kb",
                    "swap_kb", "tree_pss_mb", "tree_rss_mb", "n_procs", "note"]
            f.write(",".join(cols) + "\n")
            for row in TIMELINE:
                f.write(",".join(str(row[c]).replace(",", ";") for c in cols) + "\n")
        out_json = sess / "audit_breakdown.json"
        out_json.write_text(json.dumps({
            "config": {
                "logical": args.num_envs, "physical": physical, "rounds": rounds,
                "n_steps": args.n_steps,
                "samples_per_mu": args.n_steps * args.num_envs,
                "total_timesteps": args.total_timesteps,
                "batch_size": 512, "n_epochs": 1,
            },
            "timeline": TIMELINE,
            "breakdowns": BREAKDOWN,
            "batches": model.batch_records,
        }, indent=1))
        print(f"[audit] wrote {out_csv} and {out_json}", flush=True)
        env.close()


if __name__ == "__main__":
    main()
