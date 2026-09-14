"""Ticket 23: uint8 round-buffer storage + free-after-train lifetimes."""

import gc
import weakref

import gymnasium as gym
import numpy as np
import torch as th
from gymnasium import spaces
from stable_baselines3.common.buffers import DictRolloutBuffer
from stable_baselines3.common.vec_env import DummyVecEnv

from accumulator_ppo import AccumulatingPPO, ChainedRolloutBuffer
from native_dtype_rollout_buffer import NativeDtypeDictRolloutBuffer, obs_key_dtype

N_ENVS = 2
N_STEPS = 8
ROUNDS = 2


class Uint8DictEnv(gym.Env):
    """Dict-obs env whose heavy keys are 1-byte, matching the v2 poke spaces."""

    def __init__(self):
        # 2-D uint8 (not 3-D 0–255) so CombinedExtractor will not route
        # these keys through NatureCNN; dtype coverage is what we need.
        self.observation_space = spaces.Dict(
            {
                "screens": spaces.Box(low=0, high=255, shape=(6, 8), dtype=np.uint8),
                "map": spaces.Box(low=0, high=255, shape=(4, 4), dtype=np.uint8),
                "events": spaces.MultiBinary(16),
                "vec": spaces.Box(low=-1.0, high=1.0, shape=(2,), dtype=np.float32),
            }
        )
        self.action_space = spaces.Discrete(3)
        self.t = 0

    def _obs(self):
        return {
            "screens": np.full((6, 8), self.t % 256, dtype=np.uint8),
            "map": np.full((4, 4), (self.t * 3) % 256, dtype=np.uint8),
            "events": np.zeros(16, dtype=np.int8),
            "vec": np.array([self.t, 0.5], dtype=np.float32),
        }

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.t = 0
        return self._obs(), {}

    def step(self, action):
        self.t += 1
        return self._obs(), 1.0, False, False, {}


def make_model(rounds, seed=1):
    env = DummyVecEnv([lambda: Uint8DictEnv() for _ in range(N_ENVS)])
    return AccumulatingPPO(
        "MultiInputPolicy",
        env,
        n_steps=N_STEPS,
        batch_size=16,
        n_epochs=1,
        accumulation_rounds=rounds,
        seed=seed,
        verbose=0,
    )


def test_round_buffer_obs_use_space_dtype():
    space = Uint8DictEnv().observation_space
    buf = NativeDtypeDictRolloutBuffer(
        N_STEPS, space, spaces.Discrete(3), device="cpu", n_envs=N_ENVS
    )
    assert buf.observations["screens"].dtype == np.uint8
    assert buf.observations["map"].dtype == np.uint8
    assert buf.observations["events"].dtype == np.int8
    assert buf.observations["events"].dtype.itemsize == 1
    assert buf.observations["vec"].dtype == np.float32
    assert obs_key_dtype(space, "screens") == np.dtype(np.uint8)


def test_round_buffer_on_collect_is_uint8(monkeypatch):
    seen = []
    orig = AccumulatingPPO.collect_rollouts

    def spy(self, env, callback, rollout_buffer, n_rollout_steps):
        seen.append(rollout_buffer)
        return orig(self, env, callback, rollout_buffer, n_rollout_steps)

    monkeypatch.setattr(AccumulatingPPO, "collect_rollouts", spy)
    model = make_model(ROUNDS)
    model.learn(total_timesteps=ROUNDS * N_STEPS * N_ENVS)

    assert seen
    for buf in seen:
        assert isinstance(buf, NativeDtypeDictRolloutBuffer)
        assert buf.observations["screens"].dtype == np.uint8
        assert buf.observations["map"].dtype == np.uint8
        assert buf.observations["events"].dtype.itemsize == 1


def test_policy_batch_obs_are_float32():
    space = Uint8DictEnv().observation_space
    buf = NativeDtypeDictRolloutBuffer(
        4, space, spaces.Discrete(3), device="cpu", n_envs=2
    )
    for t in range(4):
        obs = {
            "screens": np.zeros((2, 6, 8), dtype=np.uint8),
            "map": np.zeros((2, 4, 4), dtype=np.uint8),
            "events": np.zeros((2, 16), dtype=np.int8),
            "vec": np.zeros((2, 2), dtype=np.float32),
        }
        buf.add(
            obs,
            np.zeros(2),
            np.zeros(2),
            np.ones(2),
            th.zeros(2),
            th.zeros(2),
        )
    buf.compute_returns_and_advantage(last_values=th.zeros(2), dones=np.zeros(2))
    batch = next(buf.get(batch_size=4))
    for key, tensor in batch.observations.items():
        assert tensor.dtype == th.float32, key
    assert buf.observations["screens"].dtype == np.uint8


def test_chain_released_after_train(monkeypatch):
    chain_refs = []
    round_refs = []
    buffers_during_collect = []

    orig_train = AccumulatingPPO.train
    orig_collect = AccumulatingPPO.collect_rollouts

    def train_spy(self):
        assert isinstance(self.rollout_buffer, ChainedRolloutBuffer)
        chain_refs.append(weakref.ref(self.rollout_buffer))
        for buf in self.rollout_buffer.buffers:
            round_refs.append(weakref.ref(buf))
        return orig_train(self)

    def collect_spy(self, env, callback, rollout_buffer, n_rollout_steps):
        buffers_during_collect.append(self.rollout_buffer)
        return orig_collect(self, env, callback, rollout_buffer, n_rollout_steps)

    monkeypatch.setattr(AccumulatingPPO, "train", train_spy)
    monkeypatch.setattr(AccumulatingPPO, "collect_rollouts", collect_spy)

    model = make_model(ROUNDS)
    # Two mega-updates so the second collection would have double-alive'd the
    # first chain without free-after-train.
    model.learn(total_timesteps=2 * ROUNDS * N_STEPS * N_ENVS)

    assert model.rollout_buffer is None
    gc.collect()
    assert chain_refs and all(ref() is None for ref in chain_refs)
    assert round_refs and all(ref() is None for ref in round_refs)
    assert all(not isinstance(b, ChainedRolloutBuffer) for b in buffers_during_collect)


def test_accumulating_ppo_defaults_to_native_dtype_buffer():
    model = make_model(1)
    assert isinstance(model.rollout_buffer, NativeDtypeDictRolloutBuffer)
    assert isinstance(model.rollout_buffer, DictRolloutBuffer)
    assert model.rollout_buffer.observations["screens"].dtype == np.uint8


def test_poke_like_round_buffer_obs_nbytes():
    """Lock the ticket-21 1024-sample obs footprint: 90.5 MB → ~22.6 MB."""
    space = spaces.Dict(
        {
            "screens": spaces.Box(0, 255, (72, 80, 3), np.uint8),
            "health": spaces.Box(0, 1),
            "level": spaces.Box(-1, 1, (8,)),
            "badges": spaces.MultiBinary(8),
            "events": spaces.MultiBinary(2488),
            "map": spaces.Box(0, 255, (48, 48, 1), np.uint8),
            "recent_actions": spaces.MultiDiscrete([7] * 3),
        }
    )
    buf = NativeDtypeDictRolloutBuffer(256, space, spaces.Discrete(7), device="cpu", n_envs=4)
    obs_nbytes = sum(a.nbytes for a in buf.observations.values())
    assert buf.observations["screens"].dtype == np.uint8
    assert buf.observations["map"].dtype == np.uint8
    assert buf.observations["events"].dtype.itemsize == 1
    # 22,671,360 B = 22,140 B/sample × 1024; ticket 21 baseline was 90,488,832.
    assert obs_nbytes == 22_671_360
    stock = DictRolloutBuffer(256, space, spaces.Discrete(7), device="cpu", n_envs=4)
    stock_obs = sum(a.nbytes for a in stock.observations.values())
    assert stock_obs == 90_488_832
