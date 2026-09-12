#!/usr/bin/env python3
"""Host-side Ratchet: Ledger, Milestones, Champion promotion (Human-owned)."""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

DELTA = 2.0

LEDGER_COLUMNS = [
    "commit",
    "tag",
    "score_mean",
    "score_max",
    "badges",
    "events",
    "dex_caught",
    "maps",
    "steps",
    "sps",
    "train_min",
    "status",
    "description",
    "run_type",
    "score_version",
    "eval_suite_version",
    "init_states",
]

V3_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class RatchetPaths:
    ledger: Path
    milestones: Path
    champion_json: Path
    champion_dir: Path


@dataclass
class RatchetOutcome:
    status: str
    promoted: bool = False
    reset_performed: bool = False


def _resolve_path(v3_root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return v3_root / path


def paths_from_config(config: Any, v3_root: Path = V3_ROOT) -> RatchetPaths:
    return RatchetPaths(
        ledger=_resolve_path(v3_root, config.ledger_path),
        milestones=_resolve_path(v3_root, config.milestones_path),
        champion_json=_resolve_path(v3_root, config.champion_json),
        champion_dir=_resolve_path(v3_root, config.champion_dir),
    )


def _sanitize_tsv(value: str) -> str:
    return value.replace("\t", " ").replace("\n", " ").replace("\r", " ")


def _format_cell(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        return f"{value:.6g}"
    if isinstance(value, int):
        return str(value)
    return _sanitize_tsv(str(value))


def train_elapsed_seconds(started_at: datetime, train_ended_at: datetime | None) -> float:
    end = train_ended_at or datetime.now(timezone.utc)
    return max(0.0, (end - started_at).total_seconds())


def build_ledger_row(
    ctx: Any,
    *,
    scorecard: dict[str, Any] | None,
    status: str,
    train_elapsed_s: float,
    steps: int,
) -> dict[str, str]:
    sps = (steps / train_elapsed_s) if train_elapsed_s > 0 and steps > 0 else ""
    train_min = (train_elapsed_s / 60.0) if train_elapsed_s > 0 else ""

    row: dict[str, str] = {
        "commit": ctx.commit,
        "tag": _format_cell(ctx.job.tag),
        "score_mean": "",
        "score_max": "",
        "badges": "",
        "events": "",
        "dex_caught": "",
        "maps": "",
        "steps": _format_cell(steps) if steps > 0 else "",
        "sps": _format_cell(sps) if sps != "" else "",
        "train_min": _format_cell(train_min) if train_min != "" else "",
        "status": status,
        "description": _format_cell(ctx.job.description),
        "run_type": ctx.job.run_type,
        "score_version": "",
        "eval_suite_version": "",
        "init_states": "",
    }

    if scorecard is not None:
        score = scorecard.get("score", {})
        components = scorecard.get("components_mean", {})
        row["score_mean"] = _format_cell(score.get("mean"))
        row["score_max"] = _format_cell(score.get("max"))
        row["badges"] = _format_cell(components.get("badges"))
        row["events"] = _format_cell(components.get("events"))
        row["dex_caught"] = _format_cell(components.get("dex_caught"))
        row["maps"] = _format_cell(components.get("unique_maps"))
        row["score_version"] = _format_cell(scorecard.get("score_version"))
        row["eval_suite_version"] = _format_cell(scorecard.get("eval_suite_version"))
        init_states = scorecard.get("init_states") or []
        names = [s.get("name", "") for s in init_states if s.get("name")]
        row["init_states"] = _sanitize_tsv(",".join(names))
    elif ctx.job.init_state:
        row["init_states"] = _sanitize_tsv(ctx.job.init_state)

    return row


def append_ledger_row(path: Path, row: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.is_file() or path.stat().st_size == 0
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_COLUMNS, delimiter="\t", lineterminator="\n")
        if write_header:
            writer.writeheader()
        writer.writerow({col: row.get(col, "") for col in LEDGER_COLUMNS})


def load_champion(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def save_champion(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=False) + "\n"
    tmp = path.parent / f".{path.name}.tmp"
    tmp.write_text(payload)
    tmp.replace(path)


def load_recorded_splits(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    seen: set[str] = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        split = entry.get("split")
        if split:
            seen.add(split)
    return seen


def record_milestones(path: Path, scorecard: dict[str, Any], run_id: str) -> list[str]:
    splits = scorecard.get("splits") or {}
    achieved = splits.get("achieved") or []
    if not achieved:
        return []

    seen = load_recorded_splits(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    recorded: list[str] = []
    now = datetime.now(timezone.utc).isoformat()
    with path.open("a") as f:
        for entry in achieved:
            name = entry.get("name")
            if not name or name in seen:
                continue
            payload = {
                "split": name,
                "run_id": run_id,
                "first_hit_step": entry.get("first_hit_step"),
                "game_time": entry.get("game_time"),
                "recorded_at": now,
            }
            f.write(json.dumps(payload, sort_keys=True) + "\n")
            seen.add(name)
            recorded.append(name)
    return recorded


def should_promote(score_mean: float, champion: dict[str, Any] | None) -> bool:
    if champion is None:
        return True
    return score_mean > float(champion["score_mean"]) + DELTA


def _latest_checkpoint_path(run_dir: Path) -> Path | None:
    best = 0
    for p in run_dir.glob("poke_*_steps.zip"):
        name = p.name
        if name.startswith("poke_") and name.endswith("_steps.zip"):
            try:
                steps = int(name[len("poke_") : -len("_steps.zip")])
            except ValueError:
                continue
            best = max(best, steps)
    if best <= 0:
        return None
    return run_dir / f"poke_{best}_steps.zip"


def promote_champion(
    paths: RatchetPaths,
    ctx: Any,
    scorecard: dict[str, Any],
    checkpoint_path: Path,
) -> None:
    paths.champion_dir.mkdir(parents=True, exist_ok=True)
    for old in paths.champion_dir.glob("poke_*_steps.zip"):
        old.unlink()
    dest_name = checkpoint_path.name
    dest = paths.champion_dir / dest_name
    shutil.copy2(checkpoint_path, dest)

    rel_checkpoint = f"{paths.champion_dir.name}/{dest_name}"
    save_champion(
        paths.champion_json,
        {
            "commit": ctx.commit,
            "checkpoint_path": rel_checkpoint,
            "score_mean": scorecard["score"]["mean"],
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "run_id": ctx.run_dir.name,
        },
    )


def try_discard_reset(
    repo_root: Path,
    job_commit: str,
    champion_commit: str,
    dirty_paths_fn: Any,
    head_commit_fn: Any,
) -> tuple[bool, str]:
    if dirty_paths_fn(repo_root):
        return False, "dirty tree"
    if head_commit_fn(repo_root) != job_commit:
        return False, "head moved"
    subprocess.check_call(
        ["git", "-C", str(repo_root), "reset", "--hard", champion_commit],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    return True, "reset"


def _read_scorecard(run_dir: Path) -> dict[str, Any]:
    return json.loads((run_dir / "scorecard.json").read_text())


def finalize_job(
    config: Any,
    ctx: Any,
    *,
    repo_root: Path,
    outcome: Literal["success", "crash"],
    train_ended_at: datetime | None,
    dirty_paths_fn: Any | None = None,
    head_commit_fn: Any | None = None,
    latest_checkpoint_fn: Any | None = None,
    v3_root: Path = V3_ROOT,
) -> RatchetOutcome:
    if dirty_paths_fn is None:
        from runner import dirty_tracked_paths as dirty_paths_fn  # noqa: WPS433
    if head_commit_fn is None:
        from runner import git_head_commit as head_commit_fn  # noqa: WPS433
    if latest_checkpoint_fn is None:
        from runner import latest_checkpoint_steps as latest_checkpoint_fn  # noqa: WPS433

    paths = paths_from_config(config, v3_root)
    train_elapsed_s = train_elapsed_seconds(ctx.started_at, train_ended_at)
    steps = latest_checkpoint_fn(ctx.run_dir) or 0

    result = RatchetOutcome(status="crash", promoted=False, reset_performed=False)
    scorecard: dict[str, Any] | None = None

    if outcome == "crash":
        result.status = "crash"
    elif not ctx.job.eval.enabled:
        result.status = "no-eval"
    else:
        scorecard = _read_scorecard(ctx.run_dir)
        record_milestones(paths.milestones, scorecard, ctx.run_dir.name)
        champion = load_champion(paths.champion_json)
        score_mean = float(scorecard["score"]["mean"])
        checkpoint = _latest_checkpoint_path(ctx.run_dir)

        if should_promote(score_mean, champion):
            result.status = "keep"
            if checkpoint is not None:
                promote_champion(paths, ctx, scorecard, checkpoint)
                result.promoted = True
        else:
            ok, _reason = try_discard_reset(
                repo_root,
                ctx.commit,
                champion["commit"],
                dirty_paths_fn,
                head_commit_fn,
            )
            if ok:
                result.status = "discard"
                result.reset_performed = True
            else:
                result.status = "discard-pending"

    row = build_ledger_row(
        ctx,
        scorecard=scorecard,
        status=result.status,
        train_elapsed_s=train_elapsed_s,
        steps=steps,
    )
    append_ledger_row(paths.ledger, row)
    return result
