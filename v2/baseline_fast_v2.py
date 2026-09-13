import argparse
import json
import os
import shutil
import socket
import sys
from datetime import datetime
from os.path import exists
from pathlib import Path

from red_gym_env_v2 import RedGymEnv
from stream_agent_wrapper import StreamWrapper
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import SubprocVecEnv
from stable_baselines3.common.utils import set_random_seed
from stable_baselines3.common.callbacks import CheckpointCallback, CallbackList
from accumulator_ppo import AccumulatingPPO
from tensorboard_callback import TensorboardCallback
from resource_callback import ResourceCallback

# Headless single-env step rate on this machine was ~225 sps.
# After PPO updates + SubprocVecEnv, budget ~90 sps per env.
SPS_PER_ENV = 90


def resolve_geometry(logical_envs: int, physical_envs: int | None) -> tuple[int, int]:
    """Resolve (physical_envs, rounds) from logical streams and the physical cap.

    physical_envs None/absent means physical = logical (bit-identical to the
    pre-accumulator behavior). logical must be divisible by physical.
    """
    physical = physical_envs if physical_envs is not None else logical_envs
    if physical < 1 or logical_envs % physical != 0:
        raise SystemExit(
            f"--num-envs ({logical_envs} logical streams) must be divisible by the "
            f"physical env cap ({physical}); got remainder {logical_envs % max(physical, 1)}"
        )
    return physical, logical_envs // physical


def parse_args():
    p = argparse.ArgumentParser(
        description="Train PPO on Pokemon Red (v2). Override env_config and run length from the CLI."
    )
    p.add_argument(
        "--num-envs",
        type=int,
        default=64,
        help="Logical streams the experiment asks for (= rollout width). 6 physical is safer on 16GB.",
    )
    p.add_argument(
        "--physical-envs",
        type=int,
        default=None,
        help=(
            "Physical subprocess cap. Default: V2_PHYSICAL_ENVS env var, else = --num-envs "
            "(stock behavior). num_envs must be divisible by the resolved physical count; "
            "rounds = logical / physical frozen-policy rollouts accumulate into one mega-update."
        ),
    )
    p.add_argument("--session-path", type=Path, default=Path("runs"))
    p.add_argument(
        "--minutes",
        type=float,
        default=None,
        help="Wall-clock budget. Converted to timesteps with --sps (or num_envs * 90).",
    )
    p.add_argument(
        "--sps",
        type=float,
        default=None,
        help="Assumed total env-steps/sec for --minutes. Default: num_envs * 90.",
    )
    p.add_argument("--total-timesteps", type=int, default=None, help="Exact SB3 timestep budget. Overrides --minutes.")
    p.add_argument(
        "--target-steps",
        type=int,
        default=None,
        help=(
            "Absolute lineage step count to train up to (requires a checkpoint). "
            "Resumes with the global clock (reset_num_timesteps=False): TB and "
            "checkpoint names continue from --base-steps instead of restarting at 0."
        ),
    )
    p.add_argument(
        "--base-steps",
        type=int,
        default=None,
        help=(
            "Lineage steps the loaded checkpoint represents. Default: num_timesteps "
            "stored in the zip. Set explicitly for legs trained with "
            "reset_num_timesteps=True (e.g. Mac t16 zips: 10977280)."
        ),
    )
    p.add_argument(
        "--max-steps",
        type=int,
        default=2048 * 80,
        help=(
            "Episode length / env max_steps. At default action_freq=24, "
            "steps × action_freq frames/step ÷ ~59.727 fps ≈ in-game hours "
            "(163840 steps ≈ 18.3 game-hours)."
        ),
    )
    p.add_argument(
        "--n-steps",
        type=int,
        default=None,
        help="PPO rollout horizon per env (SB3 n_steps). Default: max_steps // 64.",
    )
    p.add_argument("--save-freq", type=int, default=None, help="Vec-env steps between checkpoints. Default: max_steps/2.")
    p.add_argument("--checkpoint", default="", help="PPO zip to resume, without the .zip suffix.")
    p.add_argument("--resume", action="store_true", help="Resume the newest poke_*.zip in --session-path.")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--use-wandb", action="store_true")
    p.add_argument("--stream", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--stream-user", default="v2-default")
    p.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--save-final-state", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--early-stop", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument(
        "--early-stop-survival",
        type=float,
        default=0.05,
        help=(
            "With --early-stop: per-episode probability that a wipe does not end "
            "the episode (agent continues after blackout). Ignored when early-stop is off."
        ),
    )
    p.add_argument("--action-freq", type=int, default=24)
    p.add_argument("--init-state", default="../init.state")
    p.add_argument("--print-rewards", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--save-video", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--fast-video", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--gb-path", default="../PokemonRed.gb")
    p.add_argument("--debug", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--reward-scale", type=float, default=0.5)
    p.add_argument("--explore-weight", type=float, default=0.25)
    p.add_argument(
        "--backup",
        default="",
        help="After learn(), copy checkpoints/summaries to baselines/NAME. Empty skips.",
    )
    return p.parse_args()


def latest_checkpoint(sess_path: Path) -> str:
    zips = list(sess_path.glob("poke_*_steps.zip"))
    if not zips:
        return ""
    return str(max(zips, key=lambda p: p.stat().st_mtime)).removesuffix(".zip")


def stdin_checkpoint() -> str:
    if sys.stdin.isatty():
        return ""
    data = sys.stdin.read().strip()
    if not data:
        return ""
    first = data.splitlines()[0].strip()
    # Queue leftover paths are .json job files, not PPO checkpoints.
    if first.endswith(".json"):
        return ""
    return first


def _skip_backup_file(path: Path) -> bool:
    name = path.name
    if "tfevents" in name:
        return True
    if path.suffix.lower() in {".mp4", ".webm", ".avi", ".mov"}:
        return True
    return False


def backup_run(name, sess_path, args, start_ts, end_ts, model, completed):
    dest = Path("baselines") / name
    dest.mkdir(parents=True, exist_ok=True)

    for zipf in sess_path.glob("poke_*_steps.zip"):
        shutil.copy2(zipf, dest / zipf.name)

    for state in sess_path.rglob("*.state"):
        if not _skip_backup_file(state):
            shutil.copy2(state, dest / state.name)

    for extra in (
        sess_path / "resource_summary.txt",
        sess_path / "resource_log.csv",
    ):
        if extra.exists():
            shutil.copy2(extra, dest / extra.name)

    for path in sess_path.rglob("*"):
        if not path.is_file() or _skip_backup_file(path):
            continue
        low = path.name.lower()
        if "summary" in low or (low.endswith(".json") and path.name != "run.json"):
            target = dest / path.name
            if not target.exists():
                shutil.copy2(path, target)

    timesteps = int(getattr(model, "num_timesteps", 0) or 0) if model is not None else None
    meta = {
        "cli_args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
        "seed": args.seed,
        "start": start_ts,
        "end": end_ts,
        "num_timesteps": timesteps,
        "hostname": socket.gethostname(),
        "completed": bool(completed),
    }
    (dest / "run.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"backup written to {dest.resolve()}")


def make_env(rank, env_conf, seed=0, stream=True, stream_user="v2-default"):
    def _init():
        env = RedGymEnv(env_conf)
        if stream:
            env = StreamWrapper(
                env,
                stream_metadata={
                    "user": stream_user,
                    "env_id": rank,
                    "color": "#447799",
                    "extra": "",
                },
            )
        env.reset(seed=(seed + rank))
        return env

    set_random_seed(seed)
    return _init


if __name__ == "__main__":
    args = parse_args()
    sess_path = args.session_path
    sess_path.mkdir(exist_ok=True)

    env_config = {
        "headless": args.headless,
        "save_final_state": args.save_final_state,
        "early_stop": args.early_stop,
        "early_stop_survival": args.early_stop_survival,
        "action_freq": args.action_freq,
        "init_state": args.init_state,
        "max_steps": args.max_steps,
        "print_rewards": args.print_rewards,
        "save_video": args.save_video,
        "fast_video": args.fast_video,
        "session_path": sess_path,
        "gb_path": args.gb_path,
        "debug": args.debug,
        "reward_scale": args.reward_scale,
        "explore_weight": args.explore_weight,
    }

    env_var = os.environ.get("V2_PHYSICAL_ENVS", "").strip()
    if args.physical_envs is not None:
        physical_cap = args.physical_envs
    else:
        physical_cap = int(env_var) if env_var else None
    physical_envs, rounds = resolve_geometry(args.num_envs, physical_cap)

    sps = args.sps if args.sps is not None else physical_envs * SPS_PER_ENV
    if args.target_steps is not None and (args.total_timesteps is not None or args.minutes is not None):
        raise SystemExit("--target-steps is an absolute lineage target; do not combine with --total-timesteps/--minutes")
    if args.total_timesteps is not None:
        total_timesteps = args.total_timesteps
    elif args.minutes is not None:
        total_timesteps = int(args.minutes * 60 * sps)
    else:
        total_timesteps = args.max_steps * args.num_envs * 10000

    n_steps = args.n_steps if args.n_steps is not None else args.max_steps // 64

    save_freq = args.save_freq if args.save_freq is not None else args.max_steps // 2
    file_name = args.checkpoint or (latest_checkpoint(sess_path) if args.resume else stdin_checkpoint())

    print(env_config)
    print(
        f"logical={args.num_envs} physical={physical_envs} rounds={rounds} "
        f"update={n_steps * args.num_envs}"
    )
    print(
        f"num_envs={args.num_envs} n_steps={n_steps} total_timesteps={total_timesteps} "
        f"save_freq={save_freq} assumed_sps={sps:.0f} "
        f"est_hours={total_timesteps / sps / 3600:.1f} stream={args.stream} "
        f"checkpoint={file_name or '(none)'}"
    )
    if physical_envs > 12:
        print("warning: physical envs > 12 is likely to OOM on a 16GB Mac")

    env = SubprocVecEnv(
        [
            make_env(i, env_config, seed=args.seed, stream=args.stream, stream_user=args.stream_user)
            for i in range(physical_envs)
        ]
    )

    callbacks = [
        CheckpointCallback(save_freq=save_freq, save_path=sess_path, name_prefix="poke"),
        TensorboardCallback(sess_path),
        ResourceCallback(sess_path, num_envs=physical_envs, action_freq=args.action_freq),
    ]

    if args.use_wandb:
        import wandb
        from wandb.integration.sb3 import WandbCallback

        wandb.tensorboard.patch(root_logdir=str(sess_path))
        run = wandb.init(
            project="pokemon-train",
            id=sess_path.name,
            name="v2-a",
            config=env_config,
            sync_tensorboard=True,
            monitor_gym=True,
            save_code=True,
        )
        callbacks.append(WandbCallback())

    ppo_cls = AccumulatingPPO if rounds > 1 else PPO

    if file_name and exists(file_name + ".zip"):
        print("\nloading checkpoint")
        model = ppo_cls.load(file_name, env=env)
        model.n_steps = n_steps
        model.n_envs = physical_envs
        model.rollout_buffer.buffer_size = n_steps
        model.rollout_buffer.n_envs = physical_envs
        model.rollout_buffer.reset()
        if rounds > 1:
            model.accumulation_rounds = rounds
    else:
        if file_name:
            print(f"checkpoint not found: {file_name}.zip (starting fresh)")
        model = ppo_cls(
            "MultiInputPolicy",
            env,
            verbose=1,
            n_steps=n_steps,
            batch_size=512,
            n_epochs=1,
            gamma=0.997,
            ent_coef=0.01,
            tensorboard_log=sess_path,
            **({"accumulation_rounds": rounds} if rounds > 1 else {}),
        )

    reset_num_timesteps = True
    if args.target_steps is not None:
        if not (file_name and exists(file_name + ".zip")):
            raise SystemExit("--target-steps requires a loadable checkpoint (--checkpoint/--resume/stdin)")
        base_steps = args.base_steps if args.base_steps is not None else model.num_timesteps
        additional = args.target_steps - base_steps
        if additional <= 0:
            raise SystemExit(
                f"--target-steps ({args.target_steps}) <= base steps ({base_steps}); nothing to train"
            )
        # Continue the lineage clock: SB3 keeps num_timesteps when
        # reset_num_timesteps=False, so TB and checkpoint names stay on the
        # global step count and no tb_stitch/offset is needed downstream.
        model.num_timesteps = base_steps
        # Keep this leg's TB in its own session dir (loaded models otherwise
        # keep writing to the original run's tensorboard_log path). Steps
        # continue globally either way, so multi-dir TB/extraction stays one
        # continuous series.
        model.tensorboard_log = str(sess_path)
        total_timesteps = additional
        reset_num_timesteps = False
        print(f"resume-global: base={base_steps} target={args.target_steps} additional={additional}")

    print(model.policy)
    completed = False
    start_ts = datetime.now().astimezone().isoformat()
    try:
        model.learn(
            total_timesteps=total_timesteps,
            callback=CallbackList(callbacks),
            tb_log_name="poke_ppo",
            reset_num_timesteps=reset_num_timesteps,
        )
        completed = True
    finally:
        end_ts = datetime.now().astimezone().isoformat()
        if args.use_wandb:
            run.finish()
        if args.backup:
            backup_run(args.backup, sess_path, args, start_ts, end_ts, model, completed)
