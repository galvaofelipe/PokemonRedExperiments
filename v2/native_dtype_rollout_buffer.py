"""Dict rollout buffer that honors observation_space.dtype per key.

SB3 2.3.2 DictRolloutBuffer.reset() hardcodes np.float32 for every obs key
(stable_baselines3/common/buffers.py:747), ignoring space.dtype. Screens,
events, and map in this env are 1-byte; storing them as float32 is the 4×
that ticket 21 measured. Cast to float32 happens only when assembling the
batch that goes to the policy forward — not as a full-buffer copy.
"""

from typing import Optional, Union

import numpy as np
import torch as th
from gymnasium import spaces
from stable_baselines3.common.buffers import DictRolloutBuffer, RolloutBuffer
from stable_baselines3.common.type_aliases import DictRolloutBufferSamples
from stable_baselines3.common.vec_env import VecNormalize


def obs_key_dtype(observation_space: spaces.Dict, key: str) -> np.dtype:
    dtype = observation_space.spaces[key].dtype
    return np.dtype(np.float32) if dtype is None else np.dtype(dtype)


def obs_batch_to_torch(array: np.ndarray, device: Union[th.device, str]) -> th.Tensor:
    """Torch float32 copy of a gathered obs batch (buffer storage stays native)."""
    tensor = th.as_tensor(array, device=device)
    if tensor.dtype != th.float32:
        tensor = tensor.float()
    return tensor


class NativeDtypeDictRolloutBuffer(DictRolloutBuffer):
    """DictRolloutBuffer whose obs arrays use each subspace's declared dtype."""

    def reset(self) -> None:
        self.observations = {}
        for key, obs_input_shape in self.obs_shape.items():
            self.observations[key] = np.zeros(
                (self.buffer_size, self.n_envs, *obs_input_shape),
                dtype=obs_key_dtype(self.observation_space, key),
            )
        self.actions = np.zeros((self.buffer_size, self.n_envs, self.action_dim), dtype=np.float32)
        self.rewards = np.zeros((self.buffer_size, self.n_envs), dtype=np.float32)
        self.returns = np.zeros((self.buffer_size, self.n_envs), dtype=np.float32)
        self.episode_starts = np.zeros((self.buffer_size, self.n_envs), dtype=np.float32)
        self.values = np.zeros((self.buffer_size, self.n_envs), dtype=np.float32)
        self.log_probs = np.zeros((self.buffer_size, self.n_envs), dtype=np.float32)
        self.advantages = np.zeros((self.buffer_size, self.n_envs), dtype=np.float32)
        self.generator_ready = False
        super(RolloutBuffer, self).reset()

    def _get_samples(  # type: ignore[override]
        self,
        batch_inds: np.ndarray,
        env: Optional[VecNormalize] = None,
    ) -> DictRolloutBufferSamples:
        return DictRolloutBufferSamples(
            observations={
                key: obs_batch_to_torch(obs[batch_inds], self.device)
                for key, obs in self.observations.items()
            },
            actions=self.to_torch(self.actions[batch_inds]),
            old_values=self.to_torch(self.values[batch_inds].flatten()),
            old_log_prob=self.to_torch(self.log_probs[batch_inds].flatten()),
            advantages=self.to_torch(self.advantages[batch_inds].flatten()),
            returns=self.to_torch(self.returns[batch_inds].flatten()),
        )
