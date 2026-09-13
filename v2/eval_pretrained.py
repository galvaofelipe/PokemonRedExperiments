import argparse
import json
import time
from datetime import datetime
from os.path import exists
from pathlib import Path

import numpy as np
from red_gym_env_v2 import RedGymEnv
from stable_baselines3 import PPO
from stable_baselines3.common.utils import set_random_seed
from stable_baselines3.common.vec_env import SubprocVecEnv
from tensorboard_callback import merge_dicts
from torch.utils.tensorboard import SummaryWriter


def parse_args():
    p = argparse.ArgumentParser(
        description=(
            "Frozen-policy evaluation: run a PPO checkpoint with model.predict "
            "(no learn(), no gradient updates) and log the same telemetry tags "
            "as training (env_stats/*, env_stats_max/*, episode/*, episode_final/*)."
        )
    )
    p.add_argument("--checkpoint", default="runs/poke_26214400", help="PPO zip, without the .zip suffix.")
    p.add_argument("--num-envs", type=int, default=8)
    p.add_argument("--session-path", type=Path, default=Path("runs_eval_peter"))
    p.add_argument("--max-steps", type=int, default=16384, help="Episode length (16384 steps ≈ 2 game-hours at action_freq 24).")
    p.add_argument("--episodes", type=int, default=4, help="Episodes per env before stopping.")
    p.add_argument("--total-steps", type=int, default=None, help="Optional global env-step cap (across all envs).")
    p.add_argument("--snapshot-every", type=int, default=1024, help="Vec steps between env_stats/env_stats_max dumps.")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--deterministic", action="store_true", help="argmax actions instead of sampling (default: sample, like training).")
    p.add_argument("--save-final-state", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--gb-path", default="../PokemonRed.gb")
    p.add_argument("--init-state", default="../init.state")
    return p.parse_args()


def make_env(rank, env_conf, seed=0):
    def _init():
        env = RedGymEnv(env_conf)
        env.reset(seed=(seed + rank))
        return env

    set_random_seed(seed)
    return _init


if __name__ == "__main__":
    args = parse_args()
    sess_path = args.session_path
    sess_path.mkdir(exist_ok=True)

    env_config = {
        "headless": True,
        "save_final_state": args.save_final_state,
        "early_stop": False,
        "action_freq": 24,
        "init_state": args.init_state,
        "max_steps": args.max_steps,
        "print_rewards": True,
        "save_video": False,
        "fast_video": True,
        "session_path": sess_path,
        "gb_path": args.gb_path,
        "debug": False,
    }

    file_name = args.checkpoint.removesuffix(".zip")
    if not exists(file_name + ".zip"):
        raise SystemExit(f"checkpoint not found: {file_name}.zip")

    print(env_config)
    print(
        f"checkpoint={file_name} num_envs={args.num_envs} max_steps={args.max_steps} "
        f"episodes_per_env={args.episodes} total_steps={args.total_steps} "
        f"deterministic={args.deterministic} seed={args.seed}"
    )

    env = SubprocVecEnv(
        [make_env(i, env_config, seed=args.seed) for i in range(args.num_envs)]
    )

    print("\nloading checkpoint (frozen: predict only, no learn)")
    model = PPO.load(file_name, env=env, custom_objects={"lr_schedule": 0, "clip_range": 0})

    writer = SummaryWriter(log_dir=str(sess_path / "histogram"))
    obs = env.reset()

    episodes_done = [0] * args.num_envs
    last_stats = [{} for _ in range(args.num_envs)]
    episode_records = []
    global_steps = 0
    vec_steps = 0
    start_wall = time.time()
    start_ts = datetime.now().astimezone().isoformat()

    try:
        while True:
            actions, _ = model.predict(obs, deterministic=args.deterministic)
            obs, _rewards, dones, _infos = env.step(actions)
            vec_steps += 1
            global_steps += args.num_envs

            latest = env.env_method("get_latest_stats")
            for i, stats in enumerate(latest):
                if stats:
                    last_stats[i] = stats

            if np.any(dones):
                ep_infos = env.get_attr("last_episode_info")
                for env_idx, done in enumerate(dones):
                    if not done:
                        continue
                    episodes_done[env_idx] += 1
                    ep = ep_infos[env_idx]
                    writer.add_scalar("episode/length", ep["episode_length"], global_steps)
                    writer.add_scalar("episode/survival", 1.0 if ep["episode_survival"] else 0.0, global_steps)
                    writer.add_scalar("episode/end_wipe", 1.0 if ep["end_reason"] == "wipe" else 0.0, global_steps)
                    writer.add_scalar("episode/end_max_steps", 1.0 if ep["end_reason"] == "max_steps" else 0.0, global_steps)
                    final = dict(last_stats[env_idx])
                    for key, val in final.items():
                        if isinstance(val, (int, float)):
                            writer.add_scalar(f"episode_final/{key}", val, global_steps)
                    record = {
                        "env": env_idx,
                        "episode": episodes_done[env_idx],
                        "global_step_end": global_steps,
                        **ep,
                        **{k: v for k, v in final.items() if isinstance(v, (int, float))},
                    }
                    episode_records.append(record)
                    print(
                        f"[ep end] env={env_idx} ep={episodes_done[env_idx]} len={ep['episode_length']} "
                        f"end={ep['end_reason']} flags={final.get('event', 0) / 4:.0f} "
                        f"coords={final.get('coord_count', 0)} maps={final.get('unique_maps', 0)} "
                        f"lvls={final.get('levels_sum', 0)} deaths={final.get('deaths', 0)} "
                        f"badges={final.get('badge', 0)} mmp={final.get('max_map_progress', 0)} "
                        f"dex_seen={final.get('dex_seen', 0)} pcount={final.get('pcount', 0)} "
                    )

            if vec_steps % args.snapshot_every == 0:
                current = [s for s in last_stats if s]
                if current:
                    mean_infos, distributions = merge_dicts(current)
                    for key, val in mean_infos.items():
                        writer.add_scalar(f"env_stats/{key}", val, global_steps)
                    for key, distrib in distributions.items():
                        writer.add_scalar(f"env_stats_max/{key}", float(np.max(distrib)), global_steps)
                    sps = global_steps / max(time.time() - start_wall, 1e-9)         
                    igt = mean_infos.get("step", 0) * 24 / 59.727
                    formatted_igt = time.strftime("%H:%M:%S", time.gmtime(igt))
                    print(
                        f"[tick] ({vec_steps // args.snapshot_every}/{args.max_steps * args.episodes // args.snapshot_every}) "
                        f"steps={global_steps} eps={sum(episodes_done)}/{args.episodes * args.num_envs} "
                        f"sps={sps:.0f} igt={formatted_igt} "
                        f"flags_max={mean_infos.get('event', 0) / 4:.0f} "
                        f"coord_max={float(np.max(distributions['coord_count'])):.0f} "
                        f"lvls_max={float(np.max(distributions['levels_sum'])):.0f} "
                        f"pcount_max={float(np.max(distributions['pcount'])):.0f} "
                        f"badges_max={float(np.max(distributions['badge'])):.0f} "
                        f"dex_seen_max={float(np.max(distributions['dex_seen'])):.0f} "
                        f"unique_maps_max={float(np.max(distributions['unique_maps'])):.0f} "
                    )

            if all(e >= args.episodes for e in episodes_done):
                print("all envs reached the episode target")
                break
            if args.total_steps is not None and global_steps >= args.total_steps:
                print("total-steps cap reached")
                break
    finally:
        end_ts = datetime.now().astimezone().isoformat()
        summary = {
            "checkpoint": file_name,
            "cli_args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
            "start": start_ts,
            "end": end_ts,
            "global_steps": global_steps,
            "wall_seconds": time.time() - start_wall,
            "episodes": episode_records,
        }
        (sess_path / "eval_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        writer.close()
        env.close()
        print(f"summary written to {sess_path / 'eval_summary.json'}")
