"""`bomreuse` — the one entry point.

Every sub-command takes the paths it reads and writes as arguments. In particular the
ground-truth path is never a constant, here or anywhere in `src/`: `generate` writes it where
told, `evaluate` (#5) will read it where told, and the pipeline's entry function has no
parameter that could carry it (docs/ARCHITECTURE.md A5).
"""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from bomreuse.catalogue import CatalogueError
from bomreuse.generate import DEFAULT_SEED, GenerationError, OutputPathError, generate
from bomreuse.spec import DEFAULT_SPEC_PATH, SpecError, load_spec

Handler = Callable[[argparse.Namespace], int]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bomreuse", description="Cross-variant sub-assembly reuse finder.")
    commands = parser.add_subparsers(dest="command", required=True)
    _add_generate(commands)

    args = parser.parse_args(argv)
    handler: Handler = args.handler
    return handler(args)


# --- generate ------------------------------------------------------------------------------


def _add_generate(commands: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = commands.add_parser("generate", help="write the synthetic dataset and its ground truth")
    parser.add_argument("--out", type=Path, required=True, help="directory for the raw CSV files (the pipeline's only input)")
    parser.add_argument("--ground-truth", type=Path, required=True, help="file the ground truth is written to; never inside --out")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"seed of the dirt (default: {DEFAULT_SEED}); the story does not depend on it")
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC_PATH, help="the dataset spec (default: the committed contract)")
    parser.set_defaults(handler=_generate)


def _generate(args: argparse.Namespace) -> int:
    try:
        summary = generate(load_spec(args.spec), args.seed, args.out, args.ground_truth)
    except OutputPathError as exc:  # a usage error, like a missing argument
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (SpecError, CatalogueError, GenerationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    per_variant = ", ".join(f"{variant} {count}" for variant, count in summary.lines_per_variant.items())
    defects = ", ".join(f"{defect_type} {count}" for defect_type, count in summary.defects.items())
    print(f"seed          {summary.seed}")
    print(f"raw files     {summary.raw_dir}")
    print(f"  BOM lines   {summary.bom_lines} ({per_variant})")
    print(f"  notes       {summary.notes}")
    print(f"ground truth  {summary.ground_truth_path}")
    print(f"  components  {summary.components}")
    print(f"  defects     {defects}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
