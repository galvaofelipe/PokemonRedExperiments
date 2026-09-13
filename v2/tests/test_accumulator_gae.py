"""Validation layer 1 of ticket 14: hand-computed GAE (gamma=0.997, lambda=0.95)
vs the per-round buffers produced by AccumulatingPPO, including the bootstrap at
each round frontier."""

import gymnasium as gym
import numpy as np
import pytest
from gymnasium import spaces
from stable_baselines3.common.buffers import DictRolloutBuffer, RolloutBuffer
from stable_baselines3.common.vec_env import DummyVecEnv

from accumulator_ppo import AccumulatingPPO, ChainedRolloutBuffer

GAMMA = 0.997
GAE_LAMBDA = 0.95
N_ENVS = 2
N_STEPS = 8
ROUNDS = 3
EPISODE_LEN = 7  # < N_STEPS: each round contains an episode boundary AND a frontier bootstrap


class TinyDictEnv(gym.Env):
    """Deterministic dict-obs env; reward depends on action and time."""

    def __init__(self, episode_len=EPISODE_LEN):
        self.observation_space = spaces.Dict(
            {
                "vec": spaces.Box(low=-100.0, high=100.0, shape=(3,), dtype=np.float32),
                "aux": spaces.Box(low=-100.0, high=100.0, shape=(2,), dtype=np.float32),
            }
        )
        self.action_space = spaces.Discrete(3)
        self.episode_len = episode_len
        self.t = 0

    def _obs(self):
        return {
            "vec": np.array([float(self.t), 1.0, -1.0], dtype=np.float32),
            "aux": np.array([float(self.t), 0.5], dtype=np.float32),
        }

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.t = 0
        return self._obs(), {}

    def step(self, action):
        self.t += 1
        reward = 1.0 + 0.1 * int(action) - 0.01 * self.t
        terminated = self.t >= self.episode_len
        return self._obs(), float(reward), terminated, False, {}


def make_model(rounds, seed=1):
    env = DummyVecEnv([lambda: TinyDictEnv() for _ in range(N_ENVS)])
    return AccumulatingPPO(
        "MultiInputPolicy",
        env,
        n_steps=N_STEPS,
        batch_size=16,
        n_epochs=1,
        gamma=GAMMA,
        gae_lambda=GAE_LAMBDA,
        accumulation_rounds=rounds,
        seed=seed,
        verbose=0,
    )


def hand_gae(buffer, last_values, dones):
    """Backwards GAE recursion over a filled round buffer (float64 hand calc)."""
    n = buffer.buffer_size
    rewards = buffer.rewards.astype(np.float64)
    values = buffer.values.astype(np.float64)
    episode_starts = buffer.episode_starts.astype(np.float64)
    last_values = last_values.astype(np.float64)
    adv = np.zeros((n, buffer.n_envs), dtype=np.float64)
    last_gae = np.zeros(buffer.n_envs, dtype=np.float64)
    for step in reversed(range(n)):
        if step == n - 1:
            next_non_terminal = 1.0 - dones.astype(np.float64)
            next_values = last_values
        else:
            next_non_terminal = 1.0 - episode_starts[step + 1]
            next_values = values[step + 1]
        delta = rewards[step] + GAMMA * next_values * next_non_terminal - values[step]
        last_gae = delta + GAMMA * GAE_LAMBDA * next_non_terminal * last_gae
        adv[step] = last_gae
    return adv


@pytest.fixture
def gae_spy(monkeypatch):
    captured = []
    orig = RolloutBuffer.compute_returns_and_advantage

    def spy(self, last_values, dones):
        captured.append((self, last_values.clone().cpu().numpy().flatten().copy(), dones.copy()))
        return orig(self, last_values, dones)

    monkeypatch.setattr(RolloutBuffer, "compute_returns_and_advantage", spy)
    return captured


@pytest.fixture
def train_spy(monkeypatch):
    seen = []
    orig = AccumulatingPPO.train

    def spy(self):
        seen.append(self.rollout_buffer)
        return orig(self)

    monkeypatch.setattr(AccumulatingPPO, "train", spy)
    return seen


def test_gae_per_round_matches_hand_computed(gae_spy, train_spy):
    model = make_model(ROUNDS)
    model.learn(total_timesteps=ROUNDS * N_STEPS * N_ENVS)

    assert len(gae_spy) == ROUNDS, "one GAE computation per round"
    for buffer, last_values, dones in gae_spy:
        expected = hand_gae(buffer, last_values, dones)
        np.testing.assert_allclose(buffer.advantages, expected, rtol=1e-4, atol=1e-4)
        np.testing.assert_allclose(buffer.returns, buffer.advantages + buffer.values, rtol=1e-5, atol=1e-5)

    assert len(train_spy) == 1, "exactly one mega-update per R rounds"
    chained = train_spy[0]
    assert isinstance(chained, ChainedRolloutBuffer)
    assert chained.buffer_size == ROUNDS * N_STEPS
    np.testing.assert_array_equal(
        chained.advantages, np.concatenate([b.advantages for b, _, _ in gae_spy], axis=0)
    )
    assert model._n_updates == model.n_epochs, "_n_updates counts mega-updates"


def test_rounds_one_is_stock(gae_spy, train_spy):
    model = make_model(1)
    model.learn(total_timesteps=ROUNDS * N_STEPS * N_ENVS)

    assert len(gae_spy) == 3, "stock cadence: one update per round-trip"
    assert train_spy == [] or all(not isinstance(b, ChainedRolloutBuffer) for b in train_spy)
    assert isinstance(model.rollout_buffer, DictRolloutBuffer)
    assert model._n_updates == 3 * model.n_epochs


def fill_round(buffer, tag, n_steps, n_envs):
    """Fill a round buffer with values encoding (tag, step, env) = tag*100 + step*10 + env."""
    for t in range(n_steps):
        for e in range(n_envs):
            v = np.float32(tag * 100 + t * 10 + e)
            for key in buffer.observations:
                buffer.observations[key][t, e].fill(0)
                buffer.observations[key][t, e].flat[0] = tag * 100 + t * 10 + e
            buffer.actions[t, e].fill(v)
            buffer.values[t, e] = v
            buffer.log_probs[t, e] = v
            buffer.advantages[t, e] = v
            buffer.returns[t, e] = v
    buffer.pos = n_steps
    buffer.full = True
    return buffer


def test_chained_buffer_gather():
    obs_space = TinyDictEnv().observation_space
    act_space = spaces.Discrete(3)
    buffers = [
        fill_round(
            DictRolloutBuffer(4, obs_space, act_space, device="cpu", n_envs=2), r, 4, 2
        )
        for r in range(3)
    ]
    chained = ChainedRolloutBuffer(buffers, "cpu")
    assert chained.buffer_size == 12
    assert chained.n_envs == 2

    total = chained.buffer_size * chained.n_envs
    samples = chained._samples(np.arange(total))
    for i in range(total):
        r = i // (4 * 2)
        t = (i % (4 * 2)) // 2
        e = i % 2
        expected = np.float32(r * 100 + t * 10 + e)
        assert samples.observations["vec"][i, 0].item() == expected
        assert samples.old_values[i].item() == expected
        assert samples.advantages[i].item() == expected
        assert samples.returns[i].item() == expected

    batches = list(chained.get(batch_size=5))
    assert len(batches) == (total + 4) // 5
    got = np.sort(np.concatenate([b.advantages.numpy() for b in batches]))
    expected_all = np.sort(chained.advantages.flatten())
    np.testing.assert_array_equal(got, expected_all)


def test_resolve_geometry():
    # Deferred import: baseline_fast_v2 pulls in pyboy via red_gym_env_v2.
    from baseline_fast_v2 import resolve_geometry

    assert resolve_geometry(64, None) == (64, 1)
    assert resolve_geometry(8, None) == (8, 1)
    assert resolve_geometry(64, 8) == (8, 8)
    assert resolve_geometry(64, 16) == (16, 4)
    with pytest.raises(SystemExit):
        resolve_geometry(64, 12)
    with pytest.raises(SystemExit):
        resolve_geometry(8, 0)
