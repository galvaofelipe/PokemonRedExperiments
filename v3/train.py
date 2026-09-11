import argparse
from datetime import datetime
from os.path import exists
from pathlib import Path

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import SubprocVecEnv
from stable_baselines3.common.utils import set_random_seed
from stable_baselines3.common.callbacks import CheckpointCallback, CallbackList

from frozen.env.red_gym_env import RedGymEnv
from frozen.stream_agent_wrapper import StreamWrapper
from frozen.tensorboard_callback import TensorboardCallback
from frozen.resource_callback import ResourceCallback
from frozen.ram_map import (
    W_EVENT_FLAGS_END_EXCLUSIVE_V2,
    W_EVENT_FLAGS_START,
    W_PARTY_COUNT,
    W_ENEMY_MON_LEVEL,
    W_PARTY_MON_LEVEL,
    EVENT_BOUGHT_MUSEUM_TICKET,
)

# Headless single-env step rate on this machine was ~225 sps.
# After PPO updates + SubprocVecEnv, budget ~90 sps per env.
SPS_PER_ENV = 90

# ============ EDITABLE: Reward config ============
REWARD_SCALE = 0.5
EXPLORE_WEIGHT = 0.25


class DefaultReward:
    def __init__(self, reward_scale=REWARD_SCALE, explore_weight=EXPLORE_WEIGHT):
        self.reward_scale = reward_scale
        self.explore_weight = explore_weight

    def reset(self, env):
        self.levels_satisfied = False
        self.base_explore = 0
        self.max_opponent_level = 0
        self.max_event_rew = 0
        self.max_level_rew = 0
        self.last_health = 1
        self.total_healing_rew = 0
        self.died_count = 0
        self.party_size = 0

        self.base_event_flags = sum(
            env.bit_count(env.read_m(i))
            for i in range(W_EVENT_FLAGS_START, W_EVENT_FLAGS_END_EXCLUSIVE_V2)
        )

        self.progress_reward = self.get_game_state_reward(env)
        self.total_reward = sum(val for _, val in self.progress_reward.items())

    def update_heal(self, env):
        cur_health = env.read_hp_fraction()
        if cur_health > self.last_health and env.read_m(W_PARTY_COUNT) == self.party_size:
            if self.last_health > 0:
                heal_amount = cur_health - self.last_health
                self.total_healing_rew += heal_amount * heal_amount
            else:
                self.died_count += 1

    def update(self, env):
        self.progress_reward = self.get_game_state_reward(env)
        new_total = sum(val for _, val in self.progress_reward.items())
        new_step = new_total - self.total_reward
        self.total_reward = new_total
        return new_step

    def group_rewards(self, env):
        prog = self.progress_reward
        return (
            prog["level"] * 100 / self.reward_scale,
            env.read_hp_fraction() * 2000,
            prog["explore"] * 150 / (self.explore_weight * self.reward_scale),
        )

    def get_levels_sum(self, env):
        min_poke_level = 2
        starter_additional_levels = 4
        poke_levels = [
            max(env.read_m(a) - min_poke_level, 0) for a in W_PARTY_MON_LEVEL
        ]
        return max(sum(poke_levels) - starter_additional_levels, 0)

    def get_levels_reward(self, env):
        explore_thresh = 22
        scale_factor = 4
        level_sum = self.get_levels_sum(env)
        if level_sum < explore_thresh:
            scaled = level_sum
        else:
            scaled = (level_sum - explore_thresh) / scale_factor + explore_thresh
        self.max_level_rew = max(self.max_level_rew, scaled)
        return self.max_level_rew

    def get_all_events_reward(self, env):
        return max(
            sum(
                env.bit_count(env.read_m(i))
                for i in range(W_EVENT_FLAGS_START, W_EVENT_FLAGS_END_EXCLUSIVE_V2)
            )
            - self.base_event_flags
            - int(
                env.read_bit(
                    EVENT_BOUGHT_MUSEUM_TICKET[0], EVENT_BOUGHT_MUSEUM_TICKET[1]
                )
            ),
            0,
        )

    def get_game_state_reward(self, env, print_stats=False):
        state_scores = {
            "event": self.reward_scale * self.update_max_event_rew(env) * 4,
            "heal": self.reward_scale * self.total_healing_rew * 10,
            "badge": self.reward_scale * env.get_badges() * 10,
            "explore": self.reward_scale
            * self.explore_weight
            * len(env.seen_coords)
            * 0.1,
            "stuck": self.reward_scale
            * env.get_current_coord_count_reward()
            * -0.05,
        }
        return state_scores

    def update_max_op_level(self, env):
        opp_base_level = 5
        opponent_level = (
            max(env.read_m(a) for a in W_ENEMY_MON_LEVEL) - opp_base_level
        )
        self.max_opponent_level = max(self.max_opponent_level, opponent_level)
        return self.max_opponent_level

    def update_max_event_rew(self, env):
        cur_rew = self.get_all_events_reward(env)
        self.max_event_rew = max(cur_rew, self.max_event_rew)
        return self.max_event_rew


# ============ EDITABLE: PPO hyperparameters ============
PPO_GAMMA = 0.997
PPO_ENT_COEF = 0.01
PPO_BATCH_SIZE = 512
PPO_N_EPOCHS = 1


def parse_args():
    p = argparse.ArgumentParser(
        description="Train PPO on Pokemon Red (v3). Override env_config and run length from the CLI."
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
    p.add_argument("--stream-user", default="v3-default")
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
    p.add_argument("--reward-scale", type=float, default=REWARD_SCALE)
    p.add_argument("--explore-weight", type=float, default=EXPLORE_WEIGHT)
    return p.parse_args()


def latest_checkpoint(sess_path: Path) -> str:
    zips = list(sess_path.glob("poke_*_steps.zip"))
    if not zips:
        return ""
    return str(max(zips, key=lambda p: p.stat().st_mtime)).removesuffix(".zip")


def make_env(rank, env_conf, seed=0, stream=True, stream_user="v3-default"):
    def _init():
        conf = {
            **env_conf,
            "instance_id": str(rank),
            "reward": DefaultReward(
                reward_scale=env_conf["reward_scale"],
                explore_weight=env_conf["explore_weight"],
            ),
        }
        env = RedGymEnv(conf)
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
    file_name = args.checkpoint or (latest_checkpoint(sess_path) if args.resume else "")

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
            name="v3-a",
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
            batch_size=PPO_BATCH_SIZE,
            n_epochs=PPO_N_EPOCHS,
            gamma=PPO_GAMMA,
            ent_coef=PPO_ENT_COEF,
            tensorboard_log=sess_path,
        )

    print(model.policy)
    start_ts = datetime.now().astimezone().isoformat()
    try:
        model.learn(
            total_timesteps=total_timesteps,
            callback=CallbackList(callbacks),
            tb_log_name="poke_ppo",
        )
    finally:
        end_ts = datetime.now().astimezone().isoformat()
        if args.use_wandb:
            run.finish()
