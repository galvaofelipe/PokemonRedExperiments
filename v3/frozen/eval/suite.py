import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from frozen.scorer import load_baseline

_EVAL_DIR = Path(__file__).resolve().parent
_DEFAULT_SUITE_PATH = _EVAL_DIR / "suite.json"
_STATES_DIR = _EVAL_DIR / "states"


@dataclass(frozen=True)
class EvalState:
    name: str
    file: str
    sha256: str
    baseline: str
    path: Path


@dataclass(frozen=True)
class EvalSuite:
    eval_suite_version: str
    step_cap: int
    seeds_per_state: int
    states: tuple[EvalState, ...]
    suite_path: Path


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_eval_suite(path: Path | None = None) -> EvalSuite:
    suite_path = _DEFAULT_SUITE_PATH if path is None else Path(path)
    with open(suite_path) as f:
        data = json.load(f)

    states = []
    for entry in data["states"]:
        state_path = _STATES_DIR / entry["file"] if path is None else suite_path.parent / "states" / entry["file"]
        if not state_path.is_file():
            raise FileNotFoundError(f"eval state file not found: {state_path}")
        digest = _sha256_file(state_path)
        if digest != entry["sha256"]:
            raise ValueError(
                f"eval state {entry['name']} sha256 mismatch: "
                f"expected {entry['sha256']}, got {digest}"
            )
        load_baseline(entry["baseline"])
        states.append(
            EvalState(
                name=entry["name"],
                file=entry["file"],
                sha256=entry["sha256"],
                baseline=entry["baseline"],
                path=state_path.resolve(),
            )
        )

    return EvalSuite(
        eval_suite_version=data["eval_suite_version"],
        step_cap=data["step_cap"],
        seeds_per_state=data["seeds_per_state"],
        states=tuple(states),
        suite_path=suite_path.resolve(),
    )
