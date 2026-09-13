"""PPO with rollout accumulation (ticket 06 spec, variant 1a "chained buffer").

AccumulatingPPO collects R rounds of stock collect_rollouts with the policy
frozen (no gradient step between rounds), chains the R per-round rollout
buffers into a single read-only view, and runs one PPO.train() per
mega-update. GAE is computed natively per round, with the stock bootstrap at
each round frontier, matching the author's (n_steps, 64) buffer semantics.
"""

from typing import Generator, List, Optional, Union

import numpy as np
import torch as th
from stable_baselines3 import PPO
from stable_baselines3.common.buffers import DictRolloutBuffer, RolloutBuffer
from stable_baselines3.common.type_aliases import (
    DictRolloutBufferSamples,
    MaybeCallback,
    RolloutBufferSamples,
)
from stable_baselines3.common.vec_env import VecEnv


class ChainedRolloutBuffer:
    """Read-only view chaining per-round rollout buffers along the time axis.

    Implements the minimal interface PPO.train() consumes: get(batch_size)
    and the values/returns arrays used for explained variance.
    """

    def __init__(self, buffers: List[RolloutBuffer], device: Union[th.device, str]):
        assert buffers, "ChainedRolloutBuffer needs at least one round buffer"
        self.buffers = list(buffers)
        self.device = device
        self.n_envs = self.buffers[0].n_envs
        self.round_stride = self.buffers[0].buffer_size * self.n_envs
        self.buffer_size = sum(b.buffer_size for b in self.buffers)
        self.is_dict = isinstance(self.buffers[0], DictRolloutBuffer)
        self.values = np.concatenate([b.values for b in self.buffers], axis=0)
        self.returns = np.concatenate([b.returns for b in self.buffers], axis=0)
        self.advantages = np.concatenate([b.advantages for b in self.buffers], axis=0)

    def _locate(self, indices: np.ndarray):
        rounds = indices // self.round_stride
        rem = indices % self.round_stride
        return rounds, rem // self.n_envs, rem % self.n_envs

    def _gather_per_round(self, indices: np.ndarray, fetch) -> np.ndarray:
        rounds, steps, envs = self._locate(indices)
        chunks = []
        for r in np.unique(rounds):
            mask = rounds == r
            chunks.append(fetch(self.buffers[r], steps[mask], envs[mask]))
        return np.concatenate(chunks, axis=0)

    def _gather(self, attr: str, indices: np.ndarray) -> np.ndarray:
        return self._gather_per_round(indices, lambda buf, s, e: getattr(buf, attr)[s, e])

    def _gather_obs(self, indices: np.ndarray):
        if not self.is_dict:
            return self._gather("observations", indices)
        return {
            key: self._gather_per_round(indices, lambda buf, s, e, k=key: buf.observations[k][s, e])
            for key in self.buffers[0].observations
        }

    def _samples(self, indices: np.ndarray):
        def to_torch(x):
            return th.as_tensor(x).to(self.device)

        obs = self._gather_obs(indices)
        rest = (
            self._gather("actions", indices),
            self._gather("values", indices).flatten(),
            self._gather("log_probs", indices).flatten(),
            self._gather("advantages", indices).flatten(),
            self._gather("returns", indices).flatten(),
        )
        if self.is_dict:
            return DictRolloutBufferSamples(
                {k: to_torch(v) for k, v in obs.items()}, *tuple(map(to_torch, rest))
            )
        return RolloutBufferSamples(*tuple(map(to_torch, (obs,) + rest)))

    def get(self, batch_size: Optional[int] = None) -> Generator:
        total = self.buffer_size * self.n_envs
        indices = np.random.permutation(total)
        if batch_size is None:
            batch_size = total
        start = 0
        while start < total:
            yield self._samples(indices[start : start + batch_size])
            start += batch_size


class AccumulatingPPO(PPO):
    """PPO that trains once per R frozen-policy rollout rounds (mega-update).

    accumulation_rounds=1 delegates learn() to stock PPO unchanged.
    """

    def __init__(self, *args, accumulation_rounds: int = 1, **kwargs):
        super().__init__(*args, **kwargs)
        if accumulation_rounds < 1:
            raise ValueError(f"accumulation_rounds must be >= 1, got {accumulation_rounds}")
        self.accumulation_rounds = accumulation_rounds

    def _new_round_buffer(self) -> RolloutBuffer:
        return self.rollout_buffer_class(
            self.n_steps,
            self.observation_space,
            self.action_space,
            device=self.device,
            gamma=self.gamma,
            gae_lambda=self.gae_lambda,
            n_envs=self.n_envs,
            **self.rollout_buffer_kwargs,
        )

    def learn(
        self,
        total_timesteps: int,
        callback: MaybeCallback = None,
        log_interval: int = 1,
        tb_log_name: str = "PPO",
        reset_num_timesteps: bool = True,
        progress_bar: bool = False,
    ) -> "AccumulatingPPO":
        if self.accumulation_rounds <= 1:
            return super().learn(
                total_timesteps, callback, log_interval, tb_log_name, reset_num_timesteps, progress_bar
            )

        # Mirrors OnPolicyAlgorithm.learn from stable_baselines3 2.3.2, with the
        # rollout phase split into R frozen-policy rounds; re-audit on SB3 bumps.
        iteration = 0
        total_timesteps, callback = self._setup_learn(
            total_timesteps, callback, reset_num_timesteps, tb_log_name, progress_bar
        )
        callback.on_training_start(locals(), globals())

        assert self.env is not None
        env: VecEnv = self.env
        while self.num_timesteps < total_timesteps:
            round_buffers = []
            continue_training = True
            for _ in range(self.accumulation_rounds):
                round_buffer = self._new_round_buffer()
                continue_training = self.collect_rollouts(
                    env, callback, round_buffer, n_rollout_steps=self.n_steps
                )
                if not continue_training:
                    break
                round_buffers.append(round_buffer)
            if not continue_training:
                break

            iteration += 1
            self.rollout_buffer = ChainedRolloutBuffer(round_buffers, self.device)
            self._update_current_progress_remaining(self.num_timesteps, total_timesteps)
            if log_interval is not None and iteration % log_interval == 0:
                self._dump_logs(iteration)
            self.train()

        callback.on_training_end()
        return self
