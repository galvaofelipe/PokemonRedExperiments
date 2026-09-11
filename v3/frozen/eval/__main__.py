import argparse
from pathlib import Path

from frozen.eval.runner import run_eval


def parse_args():
    p = argparse.ArgumentParser(description="Run frozen eval suite and emit a Scorecard.")
    p.add_argument("--checkpoint", required=True, help="PPO checkpoint path (with or without .zip)")
    p.add_argument("--session-path", type=Path, required=True, help="Output directory for telemetry + scorecard")
    p.add_argument("--max-steps", type=int, default=None, help="Override suite step_cap (smokes)")
    p.add_argument("--gb-path", type=Path, default=Path("../PokemonRed.gb"))
    p.add_argument("--state-filter", default=None, help="Run a single suite state by name")
    p.add_argument("--seed-filter", type=int, default=None, help="Run a single seed index (0..seeds_per_state-1)")
    p.add_argument("--suite-path", type=Path, default=None, help="Override suite.json path")
    return p.parse_args()


def main():
    args = parse_args()
    scorecard = run_eval(
        args.checkpoint,
        args.session_path,
        gb_path=args.gb_path,
        max_steps=args.max_steps,
        state_filter=args.state_filter,
        seed_filter=args.seed_filter,
        suite_path=args.suite_path,
    )
    mean = scorecard["score"]["mean"]
    mx = scorecard["score"]["max"]
    n_ep = len(scorecard["episodes"])
    out = args.session_path / "scorecard.json"
    print(f"eval complete: episodes={n_ep} score_mean={mean:.4f} score_max={mx:.4f}")
    print(f"scorecard: {out.resolve()}")


if __name__ == "__main__":
    main()
