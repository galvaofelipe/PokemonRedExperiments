import hashlib
import os
from pathlib import Path

from stable_baselines3 import PPO

from frozen.env.red_gym_env import RedGymEnv
from frozen.eval.maps import maps_seen_names
from frozen.eval.null_reward import NullReward
from frozen.eval.scorecard import build_scorecard, write_scorecard
from frozen.eval.seeds import derive_seed
from frozen.eval.suite import EvalState, EvalSuite, load_eval_suite
from frozen.ram_map import NUM_MAPS
from frozen.scorer import load_baseline, score_snapshots
from frozen.telemetry import episode_path, iter_episode_records


def _normalize_checkpoint(path: str | Path) -> Path:
    path = Path(path)
    if path.suffix == ".zip":
        return path.resolve()
    zip_path = path.with_suffix(".zip")
    if not zip_path.is_file():
        raise FileNotFoundError(f"checkpoint not found: {zip_path}")
    return zip_path.resolve()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _checkpoint_load_path(path: Path) -> str:
    if path.suffix == ".zip":
        return str(path.with_suffix(""))
    return str(path)


def score_episode_telemetry(path: Path, baseline_event_bits: bytes):
    snapshots = []
    map_ids: set[int] = set()
    for rec in iter_episode_records(path):
        if "snapshot" not in rec:
            continue
        snapshots.append(rec["snapshot"])
        mid = rec["map"]
        if mid < NUM_MAPS:
            map_ids.add(mid)
    result = score_snapshots(snapshots, baseline_event_bits)
    return result, len(snapshots), map_ids


def run_episode(
    *,
    model: PPO,
    state: EvalState,
    seed_index: int,
    suite_version: str,
    session_path: Path,
    gb_path: Path,
    max_steps: int,
) -> dict:
    seed = derive_seed(suite_version, state.name, seed_index)
    instance_id = f"{state.name}_s{seed_index}"
    baseline = load_baseline(state.baseline)

    env = RedGymEnv(
        {
            "headless": True,
            "save_final_state": False,
            "print_rewards": False,
            "action_freq": 24,
            "init_state": str(state.path),
            "max_steps": max_steps,
            "save_video": False,
            "fast_video": True,
            "session_path": session_path,
            "gb_path": str(gb_path),
            "instance_id": instance_id,
            "reward": NullReward(),
        }
    )
    if not env.telemetry.enabled:
        env.close()
        raise RuntimeError(
            "telemetry is disabled (V3_TELEMETRY_OFF=1); eval requires telemetry recording"
        )

    try:
        obs, _ = env.reset(seed=seed)
        done = False
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, _rew, _terminated, truncated, _info = env.step(int(action))
            done = truncated
    finally:
        env.close()

    tel_path = episode_path(session_path, instance_id, reset_count=1)
    result, steps, map_ids = score_episode_telemetry(tel_path, baseline)

    return {
        "state": state.name,
        "seed": seed,
        "steps": steps,
        "score": result.score,
        "components": dict(result.components),
        "maps_seen_names": maps_seen_names(map_ids),
        "telemetry_file": tel_path.name,
        "_map_ids": map_ids,
    }


def run_eval(
    checkpoint: str | Path,
    session_path: Path,
    *,
    gb_path: Path = Path("../PokemonRed.gb"),
    max_steps: int | None = None,
    state_filter: str | None = None,
    seed_filter: int | None = None,
    suite_path: Path | None = None,
) -> dict:
    if os.environ.get("V3_TELEMETRY_OFF", "") == "1":
        raise RuntimeError(
            "V3_TELEMETRY_OFF=1 is set; eval requires telemetry recording"
        )

    suite = load_eval_suite(suite_path)
    checkpoint_path = _normalize_checkpoint(checkpoint)
    session_path = Path(session_path)
    session_path.mkdir(parents=True, exist_ok=True)
    gb_path = Path(gb_path)
    step_cap = max_steps if max_steps is not None else suite.step_cap

    states = list(suite.states)
    if state_filter is not None:
        states = [s for s in states if s.name == state_filter]
        if not states:
            raise ValueError(f"unknown state filter: {state_filter}")

    seed_indices = list(range(suite.seeds_per_state))
    if seed_filter is not None:
        if seed_filter < 0 or seed_filter >= suite.seeds_per_state:
            raise ValueError(
                f"seed_filter must be 0..{suite.seeds_per_state - 1}, got {seed_filter}"
            )
        seed_indices = [seed_filter]

    model = PPO.load(_checkpoint_load_path(checkpoint_path))

    episodes = []
    for state in states:
        for seed_index in seed_indices:
            episodes.append(
                run_episode(
                    model=model,
                    state=state,
                    seed_index=seed_index,
                    suite_version=suite.eval_suite_version,
                    session_path=session_path,
                    gb_path=gb_path,
                    max_steps=step_cap,
                )
            )

    init_states = [
        {"name": s.name, "file": s.file, "sha256": s.sha256} for s in states
    ]
    scorecard = build_scorecard(
        eval_suite_version=suite.eval_suite_version,
        checkpoint_path=checkpoint_path,
        checkpoint_sha256=_sha256_file(checkpoint_path),
        init_states=init_states,
        episodes=episodes,
    )
    write_scorecard(session_path / "scorecard.json", scorecard)
    return scorecard
