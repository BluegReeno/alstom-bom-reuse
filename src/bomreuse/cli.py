"""`bomreuse` — the one entry point.

Every sub-command takes the paths it reads and writes as arguments. In particular the
ground-truth path is never a constant, here or anywhere in `src/`: `generate` writes it where
told, `evaluate` (#5) will read it where told, and the pipeline's entry function has no
parameter that could carry it (docs/ARCHITECTURE.md A5). `normalize` follows the rule from the
other side: it takes the raw directory and an output directory, neither with a default, and no
option through which anything else could reach the pipeline.
"""

import argparse
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from bomreuse.catalogue import CatalogueError
from bomreuse.generate import DEFAULT_SEED, GenerationError, OutputPathError, generate
from bomreuse.ingest import IngestError, read_raw
from bomreuse.model import NORMALIZED_FILE, dump_dataset
from bomreuse.normalize import normalize
from bomreuse.spec import DEFAULT_SPEC_PATH, SpecError, load_spec

Handler = Callable[[argparse.Namespace], int]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bomreuse", description="Cross-variant sub-assembly reuse finder.")
    commands = parser.add_subparsers(dest="command", required=True)
    _add_generate(commands)
    _add_normalize(commands)

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


# --- normalize -----------------------------------------------------------------------------


def _add_normalize(commands: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = commands.add_parser("normalize", help="read the raw CSV files and write the normalized dataset")
    parser.add_argument("--raw", type=Path, required=True, help="directory holding variants.csv, bom.csv and notes.csv; read, never written")
    parser.add_argument("--out", type=Path, required=True, help=f"directory {NORMALIZED_FILE} is written to; never inside --raw")
    parser.set_defaults(handler=_normalize)


def _normalize(args: argparse.Namespace) -> int:
    raw_dir: Path = args.raw
    out_dir: Path = args.out
    artifact = out_dir / NORMALIZED_FILE
    # Refused before anything is read or written: inputs are read-only (CLAUDE.md rule 3).
    try:
        refused = _writes_into(artifact, raw_dir)
    except (OSError, RuntimeError) as exc:  # a symlink loop, a name too long: unknown is not safe
        print(f"error: {artifact} cannot be checked against the raw directory ({raw_dir}): {exc}", file=sys.stderr)
        return 2
    if refused:
        print(f"error: {artifact} would be written inside the raw directory ({raw_dir}), or over one of its files: inputs are read-only", file=sys.stderr)
        return 2
    try:
        dataset = normalize(read_raw(raw_dir))
    except IngestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    try:
        dump_dataset(dataset, artifact)
    except OSError as exc:  # --out is a file, a read-only directory, a full disk
        print(f"error: {artifact} cannot be written: {exc.strerror or exc}", file=sys.stderr)
        return 1

    print(f"raw files         {raw_dir}")
    print(f"  BOM lines       {len(dataset.lines)}")
    print(f"  notes           {len(dataset.notes)}")
    print(f"  variants        {len(dataset.variants)} ({', '.join(variant.id for variant in dataset.variants)})")
    print(f"components        {len(dataset.components)} (candidate groups, one per reference key)")
    print(f"sub-assemblies    {len(dataset.sub_assemblies)}")
    print(f"suppliers         {len(dataset.suppliers)}")
    # Unreadable values are data, not a failure: the rows are kept, and the count is shown.
    print(f"issues            {len(dataset.issues)}")
    breakdown = Counter((issue.source_file, issue.field, issue.reason) for issue in dataset.issues)
    for (source_file, field, reason), count in sorted(breakdown.items()):
        print(f"  {source_file} {field}: {reason}  {count}")
    print(f"normalized        {artifact}")
    return 0


def _writes_into(target: Path, directory: Path) -> bool:
    """Whether writing `target` would write inside `directory`, or over one of its files.

    Files are compared by identity (`samefile`: device and inode), never by spelling. On a
    case-insensitive filesystem `RAW/sub` is inside `raw` and `Path.resolve()` does not say so;
    and resolving the *file*, not only its directory, is what sees a symlink left where the
    artifact goes. A hard link has no path to resolve: only the inode tells.
    """
    if not directory.is_dir():
        return False  # nothing to protect, and ingest says what is wrong with it
    resolved = target.resolve()
    if any(ancestor.exists() and ancestor.samefile(directory) for ancestor in resolved.parents):
        return True
    return resolved.exists() and any(resolved.samefile(path) for path in directory.rglob("*") if path.is_file())


if __name__ == "__main__":
    raise SystemExit(main())
