import os
import json

from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.logger import Image
from torch.utils.tensorboard import SummaryWriter
import numpy as np
from einops import rearrange, reduce

def merge_dicts(dicts):
    sum_dict = {}
    count_dict = {}
    distrib_dict = {}

    for d in dicts:
        for k, v in d.items():
            if isinstance(v, (int, float)): 
                sum_dict[k] = sum_dict.get(k, 0) + v
                count_dict[k] = count_dict.get(k, 0) + 1
                distrib_dict.setdefault(k, []).append(v)

    mean_dict = {}
    for k in sum_dict:
        mean_dict[k] = sum_dict[k] / count_dict[k]
        distrib_dict[k] = np.array(distrib_dict[k])

    return mean_dict, distrib_dict

class TensorboardCallback(BaseCallback):

    def __init__(self, log_dir, verbose=0):
        super().__init__(verbose)
        self.log_dir = log_dir
        self.writer = None

    def _on_training_start(self):
        if self.writer is None:
            self.writer = SummaryWriter(log_dir=os.path.join(self.log_dir, 'histogram'))

    def _on_step(self) -> bool:
        
        if self.training_env.env_method("check_if_done", indices=[0])[0]:
            all_infos = self.training_env.get_attr("agent_stats")
            all_final_infos = [stats[-1] for stats in all_infos]
            mean_infos, distributions = merge_dicts(all_final_infos)
            # TODO log distributions, and total return
            for key, val in mean_infos.items():
                self.logger.record(f"env_stats/{key}", val)

            for key, distrib in distributions.items():
                self.writer.add_histogram(f"env_stats_distribs/{key}", distrib, self.n_calls)
                self.logger.record(f"env_stats_max/{key}", max(distrib))

        dones = self.locals.get("dones")
        if dones is not None and np.any(dones):
            # writer.add_scalar, not logger.record: logger overwrites same-key
            # values between rollout dumps, dropping episodes when more than
            # one ends inside a single rollout. Triggered by the vec dones so
            # every env's episode end is logged exactly once, on the step it
            # happens (last_episode_info survives the vec autoreset).
            all_ep_infos = self.training_env.get_attr("last_episode_info")
            for env_idx, done in enumerate(dones):
                if not done:
                    continue
                episode_info = all_ep_infos[env_idx]
                if not episode_info:
                    continue
                self.writer.add_scalar("episode/length", episode_info["episode_length"], self.num_timesteps)
                self.writer.add_scalar(
                    "episode/survival",
                    1.0 if episode_info["episode_survival"] else 0.0,
                    self.num_timesteps,
                )
                self.writer.add_scalar(
                    "episode/end_wipe",
                    1.0 if episode_info["end_reason"] == "wipe" else 0.0,
                    self.num_timesteps,
                )
                self.writer.add_scalar(
                    "episode/end_max_steps",
                    1.0 if episode_info["end_reason"] == "max_steps" else 0.0,
                    self.num_timesteps,
                )

        if self.training_env.env_method("check_if_done", indices=[0])[0]:

            #images = self.training_env.get_attr("recent_screens")
            #images_row = rearrange(np.array(images), "(r f) h w c -> (r c h) (f w)", r=2)
            #self.logger.record("trajectory/image", Image(images_row, "HW"), exclude=("stdout", "log", "json", "csv"))

            explore_map = np.array(self.training_env.get_attr("explore_map"))
            map_sum = reduce(explore_map, "f h w -> h w", "max")
            self.logger.record("trajectory/explore_sum", Image(map_sum, "HW"), exclude=("stdout", "log", "json", "csv"))

            map_row = rearrange(explore_map, "(r f) h w -> (r h) (f w)", r=2)
            self.logger.record("trajectory/explore_map", Image(map_row, "HW"), exclude=("stdout", "log", "json", "csv"))

            list_of_flag_dicts = self.training_env.get_attr("current_event_flags_set")
            merged_flags = {k: v for d in list_of_flag_dicts for k, v in d.items()}
            self.logger.record("trajectory/all_flags", json.dumps(merged_flags))

        return True
    
    def _on_training_end(self):
        if self.writer:
            self.writer.close()

