import argparse
import sys
from os.path import exists
from pathlib import Path

from red_gym_env_v2 import RedGymEnv
from stream_agent_wrapper import StreamWrapper
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import SubprocVecEnv
from stable_baselines3.common.utils import set_random_seed
from stable_baselines3.common.callbacks import CheckpointCallback, CallbackList
from tensorboard_callback import TensorboardCallback
from resource_callback import ResourceCallback

# Headless single-env step rate on this machine was ~225 sps.
# After PPO updates + SubprocVecEnv, budget ~90 sps per env.
SPS_PER_ENV = 90


def parse_args():
    p = argparse.ArgumentParser(
        description="Train PPO on Pokemon Red (v2). Override env_config and run length from the CLI."
    )
    p.add_argument("--num-envs", type=int, default=64, help="Parallel envs (also rollout width). 6 is safer on 16GB.")
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
    p.add_argument("--max-steps", type=int, default=2048 * 80, help="Episode length / env max_steps.")
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
    p.add_argument("--action-freq", type=int, default=24)
    p.add_argument("--init-state", default="../init.state")
    p.add_argument("--print-rewards", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--save-video", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--fast-video", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--gb-path", default="../PokemonRed.gb")
    p.add_argument("--debug", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--reward-scale", type=float, default=0.5)
    p.add_argument("--explore-weight", type=float, default=0.25)
    return p.parse_args()


def latest_checkpoint(sess_path: Path) -> str:
    zips = list(sess_path.glob("poke_*_steps.zip"))
    if not zips:
        return ""
    return str(max(zips, key=lambda p: p.stat().st_mtime)).removesuffix(".zip")


def stdin_checkpoint() -> str:
    if sys.stdin.isatty():
        return ""
    return sys.stdin.read().strip()


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

    sps = args.sps if args.sps is not None else args.num_envs * SPS_PER_ENV
    if args.total_timesteps is not None:
        total_timesteps = args.total_timesteps
    elif args.minutes is not None:
        total_timesteps = int(args.minutes * 60 * sps)
    else:
        total_timesteps = args.max_steps * args.num_envs * 10000

    save_freq = args.save_freq if args.save_freq is not None else args.max_steps // 2
    file_name = args.checkpoint or (latest_checkpoint(sess_path) if args.resume else stdin_checkpoint())

    print(env_config)
    print(
        f"num_envs={args.num_envs} total_timesteps={total_timesteps} "
        f"save_freq={save_freq} assumed_sps={sps:.0f} "
        f"est_hours={total_timesteps / sps / 3600:.1f} stream={args.stream} "
        f"checkpoint={file_name or '(none)'}"
    )
    if args.num_envs > 12:
        print("warning: --num-envs > 12 is likely to OOM on a 16GB Mac")

    env = SubprocVecEnv(
        [
            make_env(i, env_config, seed=args.seed, stream=args.stream, stream_user=args.stream_user)
            for i in range(args.num_envs)
        ]
    )

    callbacks = [
        CheckpointCallback(save_freq=save_freq, save_path=sess_path, name_prefix="poke"),
        TensorboardCallback(sess_path),
        ResourceCallback(sess_path, num_envs=args.num_envs, action_freq=args.action_freq),
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

    train_steps_batch = args.max_steps // 64

    if file_name and exists(file_name + ".zip"):
        print("\nloading checkpoint")
        model = PPO.load(file_name, env=env)
        model.n_steps = train_steps_batch
        model.n_envs = args.num_envs
        model.rollout_buffer.buffer_size = train_steps_batch
        model.rollout_buffer.n_envs = args.num_envs
        model.rollout_buffer.reset()
    else:
        if file_name:
            print(f"checkpoint not found: {file_name}.zip (starting fresh)")
        model = PPO(
            "MultiInputPolicy",
            env,
            verbose=1,
            n_steps=train_steps_batch,
            batch_size=512,
            n_epochs=1,
            gamma=0.997,
            ent_coef=0.01,
            tensorboard_log=sess_path,
        )

    print(model.policy)
    model.learn(
        total_timesteps=total_timesteps,
        callback=CallbackList(callbacks),
        tb_log_name="poke_ppo",
    )

    if args.use_wandb:
        run.finish()
