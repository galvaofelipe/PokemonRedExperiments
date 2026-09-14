"""Lineage machinery for the v2 checkpoint/resume system (ticket 19).

Pure logic only (no torch/pyboy imports) so the unit tests stay fast:

- checkpoint sidecars (`poke_<N>_steps.json` next to every zip),
- checkpoint selection for `--extend` (newest sidecar <= from-step),
- share fallback resolution via $POKERED_DATA (zip+sidecar+tfevents copied
  down to the local lineage dir before training),
- physical-env resolution (flag > V2_PHYSICAL_ENVS > per-host default),
- the append-only lineage ledger (`lineage.jsonl`).

Naming convention: a lineage named `<name>` (e.g. `t16_acc64_s0`, also the
share dir name and the `--backup` name) lives locally in session dir
`runs_<name>` relative to the v2/ cwd. `normalize_lineage` accepts both
forms.
"""

import json
import os
import shutil
import socket
import sys
from datetime import datetime
from pathlib import Path

SIDECAR_GLOB = "poke_*_steps.json"

# Per-host default physical env caps (ticket 19, frozen design item 1).
# Keyed by lowercase hostname (substring match).
HOST_PHYSICAL_ENVS = {
    "p2kh1a2oie9": 16,  # AM18 (WSL2)
    "am18": 16,
    "mac-mini": 8,
}


def normalize_lineage(name: str) -> str:
    """Map a lineage reference to its canonical name (strip runs_ prefix)."""
    name = str(name).strip().rstrip("/")
    if name.startswith("runs_"):
        name = name[len("runs_"):]
    return name


def local_lineage_dir(lineage: str) -> Path:
    """Local session dir for a lineage, relative to the v2/ cwd."""
    return Path(f"runs_{normalize_lineage(lineage)}")


def share_lineage_dir(lineage: str, pokered_data: str | None) -> Path | None:
    """Share dir for a lineage; None when POKERED_DATA is unset."""
    if not pokered_data:
        return None
    return Path(pokered_data) / "pokered" / "runs" / "v2" / normalize_lineage(lineage)


def ledger_path() -> Path:
    """Lineage ledger path (env override is for tests/scratch runs)."""
    return Path(os.environ.get("V2_LINEAGE_LEDGER", "lineage.jsonl"))


def write_sidecar(path: Path, global_step: int, info: dict) -> dict:
    """Write the checkpoint sidecar. `info` carries lineage, num_envs,
    n_steps, accumulation_rounds, seed, env_config (JSON-ready), parent."""
    sidecar = {
        "lineage": info["lineage"],
        "global_step": int(global_step),
        "num_envs": int(info["num_envs"]),
        "n_steps": int(info["n_steps"]),
        "accumulation_rounds": int(info["accumulation_rounds"]),
        "seed": int(info["seed"]),
        "env_config": info["env_config"],
        "parent": info.get("parent"),
        "hostname": socket.gethostname(),
        "saved_at": datetime.now().astimezone().isoformat(),
    }
    Path(path).write_text(json.dumps(sidecar, indent=2) + "\n")
    return sidecar


def read_sidecars(sess_dir: Path) -> list[dict]:
    """All parseable sidecars in a dir, each augmented with `_path`."""
    out = []
    sess_dir = Path(sess_dir)
    if not sess_dir.is_dir():
        return out
    for path in sorted(sess_dir.glob(SIDECAR_GLOB)):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"warning: skipping unreadable sidecar {path}: {exc}", file=sys.stderr)
            continue
        if "global_step" not in data:
            print(f"warning: sidecar {path} has no global_step; skipping", file=sys.stderr)
            continue
        data["_path"] = path
        out.append(data)
    return out


def select_sidecar(candidates: list[dict], from_step: int | None = None) -> dict | None:
    """Newest sidecar with global_step <= from_step (default: newest)."""
    eligible = [c for c in candidates if from_step is None or c["global_step"] <= from_step]
    if not eligible:
        return None
    return max(eligible, key=lambda c: c["global_step"])


def _zip_for_sidecar(sidecar: dict, base_dir: Path) -> Path:
    return Path(base_dir) / (sidecar["_path"].stem + ".zip")


def _copy_tree_files(src_root: Path, dst_root: Path, pred, what: str) -> int:
    """Copy files under src_root matching pred into dst_root, keeping layout."""
    n = 0
    for path in sorted(Path(src_root).rglob("*")):
        if not path.is_file() or not pred(path):
            continue
        target = Path(dst_root) / path.relative_to(src_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        n += 1
    if n:
        print(f"extend: copied {n} {what} file(s) from {src_root}")
    return n


def resolve_extend(
    lineage: str,
    from_step: int | None = None,
    cwd: Path = Path("."),
    pokered_data: str | None = None,
) -> tuple[Path, str, dict]:
    """Resolve the checkpoint an --extend leg resumes from.

    Returns (session_dir, checkpoint_stem_without_.zip, sidecar). Looks in
    the local lineage dir first (sidecar + matching zip); if nothing usable,
    falls back to $POKERED_DATA/pokered/runs/v2/<lineage>/ and copies the
    selected zip+sidecar plus all tfevents down to the local dir. Hard-fails
    (SystemExit) when nothing resolves — never silently starts fresh.
    """
    lineage = normalize_lineage(lineage)
    sess = Path(cwd) / local_lineage_dir(lineage)

    def usable(base_dir: Path) -> list[dict]:
        return [sc for sc in read_sidecars(base_dir) if _zip_for_sidecar(sc, base_dir).exists()]

    chosen = select_sidecar(usable(sess), from_step)
    if chosen is None:
        share = share_lineage_dir(lineage, pokered_data)
        if share is None or not share.is_dir():
            where = f"step <= {from_step}" if from_step is not None else "any step"
            raise SystemExit(
                f"--extend {lineage}: no usable checkpoint+sidecar at {where} in {sess} "
                f"and no share dir (POKERED_DATA {'unset' if share is None else 'has no ' + str(share)}). "
                "Refusing to start a fresh run under an existing lineage name."
            )
        share_chosen = select_sidecar(usable(share), from_step)
        if share_chosen is None:
            where = f"step <= {from_step}" if from_step is not None else "any step"
            raise SystemExit(
                f"--extend {lineage}: no usable checkpoint+sidecar at {where}, "
                f"neither in {sess} nor on the share ({share}). "
                "Refusing to start a fresh run under an existing lineage name."
            )
        sess.mkdir(parents=True, exist_ok=True)
        for src in (share_chosen["_path"], _zip_for_sidecar(share_chosen, share)):
            shutil.copy2(src, sess / src.name)
            print(f"extend: copied {src.name} down from share {share}")
        _copy_tree_files(share, sess, lambda p: "tfevents" in p.name, "tfevents")
        chosen = dict(share_chosen)
        chosen["_path"] = sess / share_chosen["_path"].name

    stem = str(_zip_for_sidecar(chosen, sess).with_suffix(""))
    return sess, stem, chosen


# CLI flag dest -> where the frozen value lives in the sidecar. Physical envs
# and streaming are machine properties and intentionally absent.
SIDECAR_FLAG_FIELDS = {
    "num_envs": ("root", "num_envs"),
    "n_steps": ("root", "n_steps"),
    "seed": ("root", "seed"),
    "max_steps": ("env_config", "max_steps"),
    "action_freq": ("env_config", "action_freq"),
    "init_state": ("env_config", "init_state"),
    "gb_path": ("env_config", "gb_path"),
    "headless": ("env_config", "headless"),
    "save_final_state": ("env_config", "save_final_state"),
    "early_stop": ("env_config", "early_stop"),
    "early_stop_survival": ("env_config", "early_stop_survival"),
    "print_rewards": ("env_config", "print_rewards"),
    "save_video": ("env_config", "save_video"),
    "fast_video": ("env_config", "fast_video"),
    "debug": ("env_config", "debug"),
    "reward_scale": ("env_config", "reward_scale"),
    "explore_weight": ("env_config", "explore_weight"),
}


def explicit_flag_dests(parser, argv: list[str]) -> set[str]:
    """Dests of flags actually present on the command line."""
    optmap = {}
    for action in parser._actions:
        for opt in action.option_strings:
            optmap[opt] = action.dest
    return {
        optmap[tok.split("=", 1)[0]]
        for tok in argv
        if tok.split("=", 1)[0] in optmap and optmap[tok.split("=", 1)[0]] != "help"
    }


def check_contradictions(args, explicit_dests: set[str], sidecar: dict) -> list[str]:
    """Explicit CLI flags that contradict the frozen sidecar values."""
    errors = []
    for dest in sorted(explicit_dests & SIDECAR_FLAG_FIELDS.keys()):
        section, key = SIDECAR_FLAG_FIELDS[dest]
        frozen = sidecar[key] if section == "root" else sidecar["env_config"][key]
        given = getattr(args, dest)
        if isinstance(frozen, bool):
            given = bool(given)
        if given != frozen:
            flag = "--" + dest.replace("_", "-")
            errors.append(
                f"--extend {sidecar['lineage']}: {flag}={given} contradicts the lineage "
                f"sidecar ({key}={frozen}); legs keep reward/env_config/logical geometry "
                "frozen — start a new lineage (branch) to change them"
            )
    return errors


def resolve_physical_cap(
    flag: int | None,
    env_var: str | None,
    logical_envs: int,
    hostname: str | None = None,
) -> int:
    """Physical env cap: --physical-envs > V2_PHYSICAL_ENVS > per-host default
    > min(logical, cpu_count). Never exceeds the logical stream count."""
    if flag is not None:
        cap = flag
    elif env_var and str(env_var).strip():
        cap = int(env_var)
    else:
        host = (hostname if hostname is not None else socket.gethostname()).lower()
        cap = next((v for k, v in HOST_PHYSICAL_ENVS.items() if k in host), 0)
        if cap <= 0:
            cap = min(logical_envs, os.cpu_count() or 1)
    if cap > logical_envs:
        print(f"physical envs {cap} exceeds logical streams {logical_envs}; capped", file=sys.stderr)
        cap = logical_envs
    return cap


def append_ledger(entry: dict, path: Path | None = None) -> None:
    """Append one JSON line to the lineage ledger. Single O_APPEND write, so
    concurrent writers on POSIX cannot interleave a record."""
    path = Path(path) if path is not None else ledger_path()
    line = json.dumps(entry, sort_keys=True) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode())
    finally:
        os.close(fd)
