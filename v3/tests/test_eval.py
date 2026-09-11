import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

V3_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V3_DIR))

from frozen.eval.maps import load_map_names, map_id_to_name, maps_seen_names
from frozen.eval.null_reward import NullReward
from frozen.eval.runner import score_episode_telemetry
from frozen.eval.scorecard import SCORECARD_VERSION, build_scorecard
from frozen.eval.seeds import derive_seed
from frozen.eval.suite import load_eval_suite
from frozen.scorer import load_baseline, score_snapshots

from conftest import FIXTURES_DIR

EVAL_DIR = V3_DIR / "frozen" / "eval"


def test_suite_loads_and_validates_state_sha256():
    suite = load_eval_suite()
    assert suite.eval_suite_version == "1.0.0"
    assert suite.step_cap == 16384
    assert suite.seeds_per_state == 3
    assert len(suite.states) == 2
    for state in suite.states:
        assert state.path.is_file()
        digest = hashlib.sha256(state.path.read_bytes()).hexdigest()
        assert digest == state.sha256


def test_suite_rejects_tampered_state_file():
    suite = load_eval_suite()
    state = suite.states[0]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        states_dir = root / "states"
        states_dir.mkdir()
        tampered = states_dir / state.file
        data = bytearray(state.path.read_bytes())
        data[0] ^= 0xFF
        tampered.write_bytes(data)
        manifest = json.loads((EVAL_DIR / "suite.json").read_text())
        suite_path = root / "suite.json"
        suite_path.write_text(json.dumps(manifest))
        with pytest.raises(ValueError, match="sha256 mismatch"):
            load_eval_suite(suite_path)


def test_suite_rejects_unknown_baseline():
    manifest = json.loads((EVAL_DIR / "suite.json").read_text())
    manifest["states"][0]["baseline"] = "nonexistent_baseline"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        states_dir = root / "states"
        states_dir.mkdir()
        for state in load_eval_suite().states:
            shutil.copy(state.path, states_dir / state.file)
        suite_path = root / "suite.json"
        suite_path.write_text(json.dumps(manifest))
        with pytest.raises(KeyError, match="unknown baseline"):
            load_eval_suite(suite_path)


def test_derive_seed_deterministic():
    a = derive_seed("1.0.0", "fresh_game", 0)
    b = derive_seed("1.0.0", "fresh_game", 0)
    c = derive_seed("1.0.0", "fresh_game", 1)
    assert a == b
    assert a != c


def test_derive_seed_formula():
    payload = "1.0.0:fresh_game:2"
    expected = int.from_bytes(
        hashlib.sha256(payload.encode("utf-8")).digest()[:4], "little"
    )
    assert derive_seed("1.0.0", "fresh_game", 2) == expected


def test_null_reward_interface():
    reward = NullReward()
    env = MagicMock()
    env.read_hp_fraction.return_value = 1.0
    env.read_m.return_value = 0

    reward.reset(env)
    assert reward.total_reward == 0.0
    assert reward.progress_reward["event"] == 0.0
    assert reward.died_count == 0

    reward.update_heal(env)
    step_rew = reward.update(env)
    reward.last_health = env.read_hp_fraction()
    grouped = reward.group_rewards(env)

    assert step_rew == 0.0
    assert grouped == (0.0, 0.0, 0.0)
    assert reward.progress_reward["event"] == 0.0


def test_null_reward_tracks_deaths_without_reward():
    reward = NullReward()
    env = MagicMock()
    env.read_hp_fraction.return_value = 0.5
    env.read_m.return_value = 1

    reward.reset(env)
    reward.party_size = 1
    reward.last_health = 0.0
    reward.update_heal(env)
    assert reward.died_count == 1
    assert reward.update(env) == 0.0


def test_maps_id_to_name_and_fallback():
    names = load_map_names()
    assert map_id_to_name(38, names) == names[38]
    assert map_id_to_name(0xFE, names) == "0xFE"


def test_maps_seen_respects_num_maps():
    seen = maps_seen_names({0, 0xF7, 0xFF})
    assert len(seen) == 2


def _synthetic_episode(score, components, map_ids):
    return {
        "state": "fresh_game",
        "seed": 1,
        "steps": 10,
        "score": score,
        "components": components,
        "maps_seen_names": maps_seen_names(map_ids),
        "telemetry_file": "fresh_game_s0_ep0001.telemetry.gz",
        "_map_ids": map_ids,
    }


def test_build_scorecard_aggregation():
    base = {
        "badges": 0,
        "events": 1,
        "dex_caught": 0,
        "dex_seen": 0,
        "unique_maps": 1,
        "level_sum_capped": 10,
    }
    episodes = [
        _synthetic_episode(1.0, dict(base), {0}),
        _synthetic_episode(3.0, {**base, "events": 3}, {0, 1}),
        _synthetic_episode(2.0, {**base, "events": 2}, {1}),
    ]
    card = build_scorecard(
        eval_suite_version="1.0.0",
        checkpoint_path=Path("runs/smoke/poke_40960_steps.zip"),
        checkpoint_sha256="abc",
        init_states=[{"name": "fresh_game", "file": "fast_text_start.state", "sha256": "x"}],
        episodes=episodes,
    )
    assert card["score"]["mean"] == 2.0
    assert card["score"]["max"] == 3.0
    assert card["components_mean"]["events"] == 2.0
    assert card["scorecard_version"] == SCORECARD_VERSION


def test_build_scorecard_maps_union():
    episodes = [
        _synthetic_episode(1.0, {
            "badges": 0, "events": 0, "dex_caught": 0, "dex_seen": 0,
            "unique_maps": 1, "level_sum_capped": 0,
        }, {0}),
        _synthetic_episode(1.0, {
            "badges": 0, "events": 0, "dex_caught": 0, "dex_seen": 0,
            "unique_maps": 1, "level_sum_capped": 0,
        }, {1}),
    ]
    card = build_scorecard(
        eval_suite_version="1.0.0",
        checkpoint_path=Path("x.zip"),
        checkpoint_sha256="abc",
        init_states=[],
        episodes=episodes,
    )
    names = load_map_names()
    assert card["maps_seen_names"] == [names[0], names[1]]


def test_scorecard_json_round_trip():
    ep = _synthetic_episode(1.5, {
        "badges": 0, "events": 0, "dex_caught": 0, "dex_seen": 0,
        "unique_maps": 1, "level_sum_capped": 5,
    }, {38})
    card = build_scorecard(
        eval_suite_version="1.0.0",
        checkpoint_path=Path("runs/smoke/poke_40960_steps.zip"),
        checkpoint_sha256="deadbeef",
        init_states=[{"name": "fresh_game", "file": "fast_text_start.state", "sha256": "x"}],
        episodes=[ep],
    )
    loaded = json.loads(json.dumps(card))
    assert loaded["scorecard_version"] == SCORECARD_VERSION
    assert "mean" in loaded["score"]
    assert "max" in loaded["score"]
    assert set(loaded["components_mean"].keys()) == {
        "badges", "events", "dex_caught", "dex_seen", "unique_maps", "level_sum_capped"
    }
    assert loaded["episodes"][0]["telemetry_file"].endswith(".telemetry.gz")


def test_score_episode_from_fixture_telemetry():
    meta = json.loads((FIXTURES_DIR / "telemetry_init" / "meta.json").read_text())
    baseline = load_baseline(meta["baseline"])
    tel_path = FIXTURES_DIR / "telemetry_init" / "telemetry" / meta["telemetry_files"][0]

    result, steps, map_ids = score_episode_telemetry(tel_path, baseline)

    snapshots = []
    for rec in iter_episode_records_helper(tel_path):
        if "snapshot" in rec:
            snapshots.append(rec["snapshot"])
    direct = score_snapshots(snapshots, baseline)

    assert result.score == direct.score
    assert result.components == direct.components
    assert steps == len(snapshots)
    assert result.components["unique_maps"] == len(map_ids)


def iter_episode_records_helper(path):
    from frozen.telemetry import iter_episode_records

    for item in iter_episode_records(path):
        if "_metadata" in item:
            continue
        yield item
