import csv
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import pytest

V3_DIR = Path(__file__).resolve().parents[1]
BIN_DIR = V3_DIR / "bin"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "scorecards"
sys.path.insert(0, str(BIN_DIR))

import ratchet  # noqa: E402


def _load_scorecard(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _ratchet_config(tmp_path: Path) -> SimpleNamespace:
    scratch = tmp_path / "ratchet"
    scratch.mkdir()
    return SimpleNamespace(
        ledger_path=str(scratch / "ledger.tsv"),
        milestones_path=str(scratch / "milestones.jsonl"),
        champion_json=str(scratch / "champion.json"),
        champion_dir=str(scratch / "champion"),
    )


def _make_job(**overrides):
    defaults = {
        "name": "exp01",
        "run_type": "cadence",
        "tag": "t1",
        "description": "desc",
        "init_state": "../init.state",
        "eval": SimpleNamespace(enabled=True),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_ctx(tmp_path: Path, job=None, commit="abc123", started_offset_s=120):
    run_dir = tmp_path / "runs" / "exp01_20260101_120000"
    run_dir.mkdir(parents=True)
    started = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    train_ended = started + timedelta(seconds=started_offset_s)
    return SimpleNamespace(
        job=job or _make_job(),
        run_dir=run_dir,
        claimed_path=Path("host-exp01.json"),
        started_at=started,
        planned_timesteps=8192,
        commit=commit,
        hostname="testhost",
        train_ended_at=train_ended,
    )


def _write_checkpoint(run_dir: Path, steps: int = 4096) -> Path:
    ckpt = run_dir / f"poke_{steps}_steps.zip"
    ckpt.write_bytes(b"zip")
    return ckpt


def _write_scorecard(run_dir: Path, scorecard: dict) -> None:
    (run_dir / "scorecard.json").write_text(json.dumps(scorecard))


def _read_ledger_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _init_git_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.check_call(["git", "init"], cwd=repo, stdout=subprocess.DEVNULL)
    subprocess.check_call(["git", "config", "user.email", "t@example.com"], cwd=repo)
    subprocess.check_call(["git", "config", "user.name", "test"], cwd=repo)
    (repo / "file.txt").write_text("v1\n")
    subprocess.check_call(["git", "add", "file.txt"], cwd=repo, stdout=subprocess.DEVNULL)
    subprocess.check_call(["git", "commit", "-m", "champion"], cwd=repo, stdout=subprocess.DEVNULL)
    champion_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    (repo / "file.txt").write_text("v2\n")
    subprocess.check_call(["git", "add", "file.txt"], cwd=repo, stdout=subprocess.DEVNULL)
    subprocess.check_call(["git", "commit", "-m", "experiment"], cwd=repo, stdout=subprocess.DEVNULL)
    experiment_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    return repo, champion_commit, experiment_commit


def test_ledger_append_writes_header_once(tmp_path):
    cfg = _ratchet_config(tmp_path)
    paths = ratchet.paths_from_config(cfg)
    row = {col: "" for col in ratchet.LEDGER_COLUMNS}
    row["commit"] = "abc"
    row["status"] = "keep"
    ratchet.append_ledger_row(paths.ledger, row)
    ratchet.append_ledger_row(paths.ledger, row)
    lines = paths.ledger.read_text().splitlines()
    assert lines[0].startswith("commit\t")
    assert len(lines) == 3


def test_ledger_row_full_schema(tmp_path):
    ctx = _make_ctx(tmp_path)
    scorecard = _load_scorecard("baseline.json")
    row = ratchet.build_ledger_row(
        ctx,
        scorecard=scorecard,
        status="keep",
        train_elapsed_s=120.0,
        steps=4096,
    )
    assert set(row.keys()) == set(ratchet.LEDGER_COLUMNS)
    assert row["commit"] == "abc123"
    assert row["tag"] == "t1"
    assert row["score_mean"] == "10"
    assert row["score_max"] == "11"
    assert row["badges"] == "0"
    assert row["events"] == "5"
    assert row["dex_caught"] == "1"
    assert row["maps"] == "3"
    assert row["steps"] == "4096"
    assert float(row["sps"]) == pytest.approx(4096 / 120.0)
    assert row["train_min"] == "2"
    assert row["status"] == "keep"
    assert row["description"] == "desc"
    assert row["run_type"] == "cadence"
    assert row["score_version"] == "1.0.0"
    assert row["eval_suite_version"] == "1.0.0"
    assert row["init_states"] == "fresh_game"


def test_milestones_first_ever(tmp_path):
    cfg = _ratchet_config(tmp_path)
    paths = ratchet.paths_from_config(cfg)
    scorecard = _load_scorecard("with_brock_split.json")
    recorded = ratchet.record_milestones(paths.milestones, scorecard, "exp01_20260101_120000")
    assert recorded == ["Brock"]
    lines = paths.milestones.read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["split"] == "Brock"
    assert entry["run_id"] == "exp01_20260101_120000"
    assert entry["first_hit_step"] == 1234
    assert entry["game_time"] == "0:05:30"


def test_milestones_repeat_skipped(tmp_path):
    cfg = _ratchet_config(tmp_path)
    paths = ratchet.paths_from_config(cfg)
    scorecard = _load_scorecard("with_brock_split.json")
    ratchet.record_milestones(paths.milestones, scorecard, "run_a")
    recorded = ratchet.record_milestones(paths.milestones, scorecard, "run_b")
    assert recorded == []
    assert len(paths.milestones.read_text().strip().splitlines()) == 1


def test_bootstrap_promotes_first_scorecard(tmp_path):
    cfg = _ratchet_config(tmp_path)
    ctx = _make_ctx(tmp_path)
    _write_checkpoint(ctx.run_dir)
    _write_scorecard(ctx.run_dir, _load_scorecard("baseline.json"))
    outcome = ratchet.finalize_job(
        cfg,
        ctx,
        repo_root=tmp_path,
        outcome="success",
        train_ended_at=ctx.train_ended_at,
        dirty_paths_fn=lambda _r: [],
        head_commit_fn=lambda _r: ctx.commit,
        latest_checkpoint_fn=lambda _d: 4096,
    )
    assert outcome.status == "keep"
    assert outcome.promoted is True
    champion = ratchet.load_champion(ratchet.paths_from_config(cfg).champion_json)
    assert champion is not None
    assert champion["score_mean"] == 10.0
    rows = _read_ledger_rows(ratchet.paths_from_config(cfg).ledger)
    assert rows[-1]["status"] == "keep"


def test_delta_gate_promotes(tmp_path):
    cfg = _ratchet_config(tmp_path)
    paths = ratchet.paths_from_config(cfg)
    ratchet.save_champion(
        paths.champion_json,
        {
            "commit": "champ",
            "checkpoint_path": "champion/poke_1000_steps.zip",
            "score_mean": 10.0,
            "promoted_at": "2026-01-01T00:00:00+00:00",
            "run_id": "old_run",
        },
    )
    ctx = _make_ctx(tmp_path)
    _write_checkpoint(ctx.run_dir)
    _write_scorecard(ctx.run_dir, _load_scorecard("winner.json"))
    outcome = ratchet.finalize_job(
        cfg,
        ctx,
        repo_root=tmp_path,
        outcome="success",
        train_ended_at=ctx.train_ended_at,
        dirty_paths_fn=lambda _r: [],
        head_commit_fn=lambda _r: ctx.commit,
        latest_checkpoint_fn=lambda _d: 4096,
    )
    assert outcome.status == "keep"
    assert outcome.promoted is True
    champion = ratchet.load_champion(paths.champion_json)
    assert champion["score_mean"] == 12.5


def test_delta_boundary_equal_does_not_promote(tmp_path):
    cfg = _ratchet_config(tmp_path)
    paths = ratchet.paths_from_config(cfg)
    repo, champion_commit, experiment_commit = _init_git_repo(tmp_path)
    ratchet.save_champion(
        paths.champion_json,
        {
            "commit": champion_commit,
            "checkpoint_path": "champion/poke_1000_steps.zip",
            "score_mean": 10.0,
            "promoted_at": "2026-01-01T00:00:00+00:00",
            "run_id": "old_run",
        },
    )
    ctx = _make_ctx(tmp_path, commit=experiment_commit)
    _write_checkpoint(ctx.run_dir)
    _write_scorecard(ctx.run_dir, _load_scorecard("boundary.json"))
    outcome = ratchet.finalize_job(
        cfg,
        ctx,
        repo_root=repo,
        outcome="success",
        train_ended_at=ctx.train_ended_at,
        dirty_paths_fn=lambda _r: [],
        head_commit_fn=lambda _r: experiment_commit,
        latest_checkpoint_fn=lambda _d: 4096,
    )
    assert outcome.status == "discard"
    assert outcome.promoted is False
    assert outcome.reset_performed is True
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    assert head == champion_commit


def test_discard_resets_git_tree(tmp_path):
    cfg = _ratchet_config(tmp_path)
    paths = ratchet.paths_from_config(cfg)
    repo, champion_commit, experiment_commit = _init_git_repo(tmp_path)
    ratchet.save_champion(
        paths.champion_json,
        {
            "commit": champion_commit,
            "checkpoint_path": "champion/poke_1000_steps.zip",
            "score_mean": 10.0,
            "promoted_at": "2026-01-01T00:00:00+00:00",
            "run_id": "old_run",
        },
    )
    ctx = _make_ctx(tmp_path, commit=experiment_commit)
    _write_checkpoint(ctx.run_dir)
    scorecard = _load_scorecard("baseline.json")
    _write_scorecard(ctx.run_dir, scorecard)
    outcome = ratchet.finalize_job(
        cfg,
        ctx,
        repo_root=repo,
        outcome="success",
        train_ended_at=ctx.train_ended_at,
        dirty_paths_fn=lambda _r: [],
        head_commit_fn=lambda _r: experiment_commit,
        latest_checkpoint_fn=lambda _d: 4096,
    )
    assert outcome.status == "discard"
    assert outcome.reset_performed is True
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    assert head == champion_commit
    assert (repo / "file.txt").read_text() == "v1\n"


def test_reset_failsafe_dirty_tree(tmp_path):
    cfg = _ratchet_config(tmp_path)
    paths = ratchet.paths_from_config(cfg)
    repo, champion_commit, experiment_commit = _init_git_repo(tmp_path)
    ratchet.save_champion(
        paths.champion_json,
        {
            "commit": champion_commit,
            "checkpoint_path": "champion/poke_1000_steps.zip",
            "score_mean": 10.0,
            "promoted_at": "2026-01-01T00:00:00+00:00",
            "run_id": "old_run",
        },
    )
    ctx = _make_ctx(tmp_path, commit=experiment_commit)
    _write_checkpoint(ctx.run_dir)
    _write_scorecard(ctx.run_dir, _load_scorecard("baseline.json"))
    outcome = ratchet.finalize_job(
        cfg,
        ctx,
        repo_root=repo,
        outcome="success",
        train_ended_at=ctx.train_ended_at,
        dirty_paths_fn=lambda _r: ["dirty.py"],
        head_commit_fn=lambda _r: experiment_commit,
        latest_checkpoint_fn=lambda _d: 4096,
    )
    assert outcome.status == "discard-pending"
    assert outcome.reset_performed is False
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    assert head == experiment_commit


def test_reset_failsafe_head_moved(tmp_path):
    cfg = _ratchet_config(tmp_path)
    paths = ratchet.paths_from_config(cfg)
    repo, champion_commit, experiment_commit = _init_git_repo(tmp_path)
    ratchet.save_champion(
        paths.champion_json,
        {
            "commit": champion_commit,
            "checkpoint_path": "champion/poke_1000_steps.zip",
            "score_mean": 10.0,
            "promoted_at": "2026-01-01T00:00:00+00:00",
            "run_id": "old_run",
        },
    )
    ctx = _make_ctx(tmp_path, commit=experiment_commit)
    _write_checkpoint(ctx.run_dir)
    _write_scorecard(ctx.run_dir, _load_scorecard("baseline.json"))
    (repo / "extra.txt").write_text("human edit\n")
    subprocess.check_call(["git", "add", "extra.txt"], cwd=repo, stdout=subprocess.DEVNULL)
    subprocess.check_call(["git", "commit", "-m", "human"], cwd=repo, stdout=subprocess.DEVNULL)
    human_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    assert human_head != experiment_commit
    outcome = ratchet.finalize_job(
        cfg,
        ctx,
        repo_root=repo,
        outcome="success",
        train_ended_at=ctx.train_ended_at,
        dirty_paths_fn=lambda _r: [],
        head_commit_fn=lambda _r: human_head,
        latest_checkpoint_fn=lambda _d: 4096,
    )
    assert outcome.status == "discard-pending"
    assert outcome.reset_performed is False
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    assert head == human_head


def test_probe_no_eval_row(tmp_path):
    cfg = _ratchet_config(tmp_path)
    job = _make_job(eval=SimpleNamespace(enabled=False), run_type="probe")
    ctx = _make_ctx(tmp_path, job=job)
    _write_checkpoint(ctx.run_dir)
    outcome = ratchet.finalize_job(
        cfg,
        ctx,
        repo_root=tmp_path,
        outcome="success",
        train_ended_at=ctx.train_ended_at,
        dirty_paths_fn=lambda _r: [],
        head_commit_fn=lambda _r: ctx.commit,
        latest_checkpoint_fn=lambda _d: 4096,
    )
    assert outcome.status == "no-eval"
    rows = _read_ledger_rows(ratchet.paths_from_config(cfg).ledger)
    assert rows[-1]["status"] == "no-eval"
    assert rows[-1]["score_mean"] == ""
    assert rows[-1]["steps"] == "4096"


def test_crash_row(tmp_path):
    cfg = _ratchet_config(tmp_path)
    ctx = _make_ctx(tmp_path)
    ctx.train_ended_at = None
    outcome = ratchet.finalize_job(
        cfg,
        ctx,
        repo_root=tmp_path,
        outcome="crash",
        train_ended_at=ctx.train_ended_at,
        dirty_paths_fn=lambda _r: [],
        head_commit_fn=lambda _r: ctx.commit,
        latest_checkpoint_fn=lambda _d: 0,
    )
    assert outcome.status == "crash"
    rows = _read_ledger_rows(ratchet.paths_from_config(cfg).ledger)
    assert rows[-1]["status"] == "crash"
    assert rows[-1]["score_mean"] == ""


def test_promote_copies_checkpoint_to_champion_dir(tmp_path):
    cfg = _ratchet_config(tmp_path)
    paths = ratchet.paths_from_config(cfg)
    ctx = _make_ctx(tmp_path)
    ckpt = _write_checkpoint(ctx.run_dir, steps=8192)
    scorecard = _load_scorecard("baseline.json")
    ratchet.promote_champion(paths, ctx, scorecard, ckpt)
    dest = paths.champion_dir / "poke_8192_steps.zip"
    assert dest.is_file()
    assert dest.read_bytes() == b"zip"
    champion = ratchet.load_champion(paths.champion_json)
    assert champion["checkpoint_path"] == "champion/poke_8192_steps.zip"
    assert champion["run_id"] == ctx.run_dir.name
