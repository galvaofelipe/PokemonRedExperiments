"""Boot one RedGymEnv window and take a few random actions."""
from pathlib import Path

from red_gym_env_v2 import RedGymEnv

STEPS = 120

env = RedGymEnv(
    {
        "headless": False,
        "save_final_state": False,
        "early_stop": False,
        "action_freq": 24,
        "init_state": "../init.state",
        "max_steps": STEPS,
        "print_rewards": True,
        "save_video": False,
        "fast_video": True,
        "session_path": Path("session_smoke"),
        "gb_path": "../PokemonRed.gb",
        "debug": False,
        "reward_scale": 0.5,
        "explore_weight": 0.25,
    }
)

try:
    obs, info = env.reset()
    print("reset ok; window should be visible. taking random actions.")
    for step in range(STEPS):
        obs, reward, terminated, truncated, info = env.step(env.action_space.sample())
        env.render()
        if terminated or truncated:
            print(f"ended at step {step}")
            break
finally:
    env.close()
print("smoke test finished")
