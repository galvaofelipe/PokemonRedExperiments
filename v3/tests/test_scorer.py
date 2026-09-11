import sys
from pathlib import Path

import pytest

V3_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V3_DIR))

from frozen.scorer import SCORE_VERSION, load_baseline, score_snapshots
from frozen.ram_map import SNAPSHOT_SIZE

from conftest import FIXTURES_DIR, load_fixture_meta, load_fixture_snapshots

WEIGHTS = {
    "badges": 100,
    "events": 1,
    "dex_caught": 2,
    "dex_seen": 0.5,
    "unique_maps": 1,
    "level_sum_capped": 0.1,
}


def weighted_sum(components):
    return sum(WEIGHTS[k] * components[k] for k in WEIGHTS)


def score_fixture(name, baseline_name=None):
    fixture_dir = FIXTURES_DIR / name
    snapshots = load_fixture_snapshots(fixture_dir)
    meta = load_fixture_meta(fixture_dir)
    baseline = load_baseline(meta["baseline"] if baseline_name is None else baseline_name)
    return score_snapshots(snapshots, baseline), meta


def test_pokedex_milestone(fixture_loader):
    snapshots, meta = fixture_loader("pokedex_milestone")
    baseline = load_baseline(meta["baseline"])
    result = score_snapshots(snapshots, baseline)
    expected = meta["expected"]
    assert result.score == expected["score"]
    assert result.components == expected["components"]
    delta = expected["delta_from_first"]
    assert delta["score"] > 0


def test_badge_milestone(fixture_loader):
    snapshots, meta = fixture_loader("badge_milestone")
    baseline = load_baseline(meta["baseline"])
    result = score_snapshots(snapshots, baseline)
    expected = meta["expected"]
    assert result.score == expected["score"]
    assert result.components["badges"] == 2
    assert expected["delta_from_first"]["score"] == 200


def test_museum_ticket_excluded(fixture_loader):
    snapshots, meta = fixture_loader("museum_ticket_excluded")
    baseline = load_baseline(meta["baseline"])
    result = score_snapshots(snapshots, baseline)
    delta = meta["expected"]["delta_from_first"]
    assert delta["score"] == 0
    assert delta["components"]["events"] == 0


def test_money_noop(fixture_loader):
    snapshots, meta = fixture_loader("money_noop")
    baseline = load_baseline(meta["baseline"])
    result = score_snapshots(snapshots, baseline)
    delta = meta["expected"]["delta_from_first"]
    assert delta["score"] == 0
    for key in delta["components"]:
        assert delta["components"][key] == 0


def test_heal_noop(fixture_loader):
    snapshots, meta = fixture_loader("heal_noop")
    baseline = load_baseline(meta["baseline"])
    result = score_snapshots(snapshots, baseline)
    delta = meta["expected"]["delta_from_first"]
    assert delta["score"] == 0
    for key in delta["components"]:
        assert delta["components"][key] == 0


def test_map_revisit(fixture_loader):
    snapshots, meta = fixture_loader("map_revisit")
    baseline = load_baseline(meta["baseline"])
    result = score_snapshots(snapshots, baseline)
    assert result.components["unique_maps"] == meta["expected"]["unique_maps"]


def test_level_cap(fixture_loader):
    snapshots, meta = fixture_loader("level_cap")
    baseline = load_baseline(meta["baseline"])
    result = score_snapshots(snapshots, baseline)
    assert result.components["level_sum_capped"] == 100
    result_high = score_snapshots([snapshots[0]], baseline)
    result_low = score_snapshots([snapshots[1]], baseline)
    assert result_high.components["level_sum_capped"] == 100
    assert result_low.components["level_sum_capped"] == 30
    assert result.components["level_sum_capped"] == result_high.components["level_sum_capped"]


def test_gym_skip_worse():
    takes_dir = FIXTURES_DIR / "gym_skip_worse" / "takes_gym"
    skips_dir = FIXTURES_DIR / "gym_skip_worse" / "skips_gym"
    takes_snaps = load_fixture_snapshots(takes_dir)
    skips_snaps = load_fixture_snapshots(skips_dir)
    takes_meta = load_fixture_meta(takes_dir)
    skips_meta = load_fixture_meta(skips_dir)
    baseline = load_baseline("init")
    takes = score_snapshots(takes_snaps, baseline)
    skips = score_snapshots(skips_snaps, baseline)
    assert takes.score == takes_meta["expected"]["score"]
    assert skips.score == skips_meta["expected"]["score"]
    assert takes.score > skips.score


def test_breakdown_emitted(fixture_loader):
    snapshots, meta = fixture_loader("badge_milestone")
    baseline = load_baseline(meta["baseline"])
    result = score_snapshots(snapshots, baseline)
    assert result.score_version == SCORE_VERSION
    for key in WEIGHTS:
        assert key in result.components
    assert result.score == weighted_sum(result.components)
    d = result.to_dict()
    assert d["score_version"] == SCORE_VERSION
    assert set(d["components"].keys()) == set(WEIGHTS.keys())


def test_wrong_snapshot_length():
    baseline = load_baseline("init")
    with pytest.raises(ValueError, match="snapshot must be"):
        score_snapshots([b"\x00" * (SNAPSHOT_SIZE - 1)], baseline)


def test_wrong_baseline_length():
    with pytest.raises(ValueError, match="baseline_event_bits must be"):
        score_snapshots([b"\x00" * SNAPSHOT_SIZE], b"\x00" * 319)
