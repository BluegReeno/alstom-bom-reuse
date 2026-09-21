"""`bomreuse` — the one entry point.

Every sub-command takes the paths it reads and writes as arguments. In particular the
ground-truth path is never a constant, here or anywhere in `src/`: `generate` writes it where
told, `evaluate` (#5) will read it where told, and the pipeline's entry function has no
parameter that could carry it (docs/ARCHITECTURE.md A5). `normalize` follows the rule from the
other side: it takes the raw directory and an output directory, neither with a default, and no
option through which anything else could reach the pipeline. `run` — the whole pipeline, and the
one command a client would be shown — takes those two, and the dataset spec it reads the reuse
threshold from: a file the run classifies by, so the run says which one it used rather than
finding one next to its own source.
"""

import argparse
import sys
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path

from bomreuse.catalogue import CatalogueError
from bomreuse.checks import CONFLICT_RULES, check, conflicts_by_component
from bomreuse.generate import DEFAULT_SEED, GenerationError, OutputPathError, generate
from bomreuse.ingest import IngestError, read_raw
from bomreuse.model import (
    NORMALIZED_FILE,
    RUN_ARTIFACTS,
    Attribute,
    Backtest,
    Finding,
    GroupVerdict,
    ModelError,
    NormalizedDataset,
    Prediction,
    Resolution,
    ReuseClass,
    SignatureItem,
    SubAssemblySignature,
    dump_backtest,
    dump_dataset,
    dump_findings,
    dump_resolution,
    dump_signatures,
    load_backtest,
    load_dataset,
    load_findings,
    load_resolution,
    load_signatures,
)
from bomreuse.normalize import normalize
from bomreuse.resolve import resolve
from bomreuse.signatures import backtest, build_signatures
from bomreuse.spec import DEFAULT_SPEC_PATH, SpecError, load_spec

Handler = Callable[[argparse.Namespace], int]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bomreuse", description="Cross-variant sub-assembly reuse finder.")
    commands = parser.add_subparsers(dest="command", required=True)
    _add_generate(commands)
    _add_normalize(commands)
    _add_run(commands)

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
    refusal = _refusal([artifact], raw_dir)
    if refusal is not None:
        print(f"error: {refusal}", file=sys.stderr)
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
    _print_issues(dataset)
    print(f"normalized        {artifact}")
    return 0


# --- run -----------------------------------------------------------------------------------


def _add_run(commands: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = commands.add_parser("run", help="run the pipeline: normalize, resolve references, write the findings")
    parser.add_argument("--raw", type=Path, required=True, help="directory holding variants.csv, bom.csv and notes.csv; read, never written")
    parser.add_argument("--out", type=Path, required=True, help="directory the artifacts are written to; never inside --raw")
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC_PATH, help="the dataset spec the reuse threshold is read from (default: the committed contract)")
    parser.set_defaults(handler=_run)


def _run(args: argparse.Namespace) -> int:
    """The whole pipeline, offline, in the order docs/ARCHITECTURE.md draws it.

    Each stage reads the previous stage's artifact rather than the object still in memory, so
    running the stages one by one from the command line gives what this does — and a stale or
    hand-edited `normalized.json` is refused here by `ModelError`, not met three frames later.
    """
    raw_dir: Path = args.raw
    out_dir: Path = args.out
    artifacts = [out_dir / name for name in RUN_ARTIFACTS]
    refusal = _refusal(artifacts, raw_dir)
    if refusal is not None:
        print(f"error: {refusal}", file=sys.stderr)
        return 2

    normalized, resolution_file, findings_file, signatures_file, predictions_file = artifacts
    try:
        # Read before anything is written: a spec the last stage cannot read must not leave four
        # artifacts of a run that failed behind it.
        thresholds = load_spec(args.spec).thresholds
        dataset = normalize(read_raw(raw_dir))
        dump_dataset(dataset, normalized)
        read_back = load_dataset(normalized)
        resolution, findings = resolve(read_back)
        dump_resolution(resolution, resolution_file)
        # The checks read the resolution back like the signatures do: they run on the canonical
        # components it wrote, split parts included, and their findings join the same artifact.
        findings += check(read_back, load_resolution(resolution_file))
        dump_findings(findings, findings_file)
        dump_signatures(build_signatures(read_back, load_resolution(resolution_file)), signatures_file)
        dump_backtest(backtest(load_signatures(signatures_file), read_back.variants, thresholds), predictions_file)
    except (IngestError, ModelError, SpecError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:  # --out is a file, a read-only directory, a full disk
        print(f"error: {out_dir} cannot be written: {exc.strerror or exc}", file=sys.stderr)
        return 1

    _print_run_summary(raw_dir, dataset, resolution, findings)
    written_findings = load_findings(findings_file)
    _print_backtest(dataset, load_signatures(signatures_file), load_backtest(predictions_file), conflicts_by_component(written_findings))
    _print_inconsistencies(written_findings)
    for artifact in artifacts:
        print(f"written           {artifact}")
    return 0


def _print_run_summary(raw_dir: Path, dataset: NormalizedDataset, resolution: Resolution, findings: tuple[Finding, ...]) -> None:
    """What the run read and what it made of it, above the answer `_print_backtest` gives."""
    print(f"raw files         {raw_dir}")
    print(f"  BOM lines       {len(dataset.lines)}")
    print(f"  variants        {len(dataset.variants)} ({', '.join(variant.id for variant in dataset.variants)})")
    print(f"references        {len(resolution.groups)} candidate groups -> {len(resolution.components)} canonical components")
    # Always the three lines, in the order of the A2 table: "reject 0" is an answer, and a
    # client reading two runs side by side should not have to notice a missing line.
    verdicts = Counter(group.verdict for group in resolution.groups)
    for verdict in GroupVerdict:
        print(f"  {verdict:<16}{verdicts[verdict]}")
    print(f"findings          {len(findings)}")
    for rule_id, count in sorted(Counter(finding.rule_id for finding in findings).items()):
        print(f"  {rule_id:<32}{count}")
    _print_issues(dataset)


def _print_issues(dataset: NormalizedDataset) -> None:
    """Unreadable values are data, not a failure: the rows are kept, and the count is shown.

    Every stage after `normalize` drops them on the stated ground that they are already counted
    here, and that reasoning only holds while the count is on the screen the reader is looking at.
    """
    print(f"issues            {len(dataset.issues)}")
    breakdown = Counter((issue.source_file, issue.field, issue.reason) for issue in dataset.issues)
    for (source_file, field, reason), count in sorted(breakdown.items()):
        print(f"  {source_file} {field}: {reason}  {count}")


def _print_backtest(
    dataset: NormalizedDataset,
    signatures: tuple[SubAssemblySignature, ...],
    result: Backtest,
    conflicts: Mapping[str, tuple[Attribute, ...]],
) -> None:
    """The answer to the client's question, on stdout.

    The demo is this table, not the HTML report of #7 (Decision 29): a sub-assembly of the
    newest variant per line, its class, the older sub-assembly the answer rests on, and — when
    it is *reusable* — what would have to change. Every ratio a reader could compute from it has
    its counts underneath; scoring the table against the ground truth is `evaluate`'s job (#5).

    A *reused* or *reusable* row whose parts carry a conflict says so on the row: that is the
    one a design engineer must see before trusting the reuse, and a separate block further down
    is one they could skip.
    """
    if not result.target_variant_id:
        print("backtest          no variant carries a readable design date: nothing to play as a new tender")
        return

    target = next(variant for variant in dataset.variants if variant.id == result.target_variant_id)
    designed = target.design_date.normalized
    print(f"backtest          {target.id} ({target.name.normalized}, designed {designed}) against {', '.join(result.ancestor_variant_ids)}")
    print(f"  {'sub-assembly':<14}{'designation':<32}{'class':<10}{'from':<14}difference")

    designations = {signature.sub_assembly_id: " / ".join(signature.designations) for signature in signatures}
    left_out = {signature.sub_assembly_id: signature.lines_left_out for signature in signatures}
    components = {signature.sub_assembly_id: [item.component for item in signature.signature.items] for signature in signatures}
    for prediction in result.predictions:
        warning = _unsafe(prediction, components[prediction.sub_assembly_id], conflicts)
        detail = " ".join(part for part in (_difference(prediction), _partial(prediction, left_out), warning) if part)
        print(
            f"  {prediction.sub_assembly_id:<14}{designations[prediction.sub_assembly_id]:<32}"
            f"{prediction.reuse_class:<10}{prediction.ancestor_id:<14}{detail}".rstrip()
        )
    # Always the three lines, in the order of the A1 table: "specific 0" is an answer too.
    counted = Counter(prediction.reuse_class for prediction in result.predictions)
    for reuse_class in ReuseClass:
        print(f"  {reuse_class:<16}{counted[reuse_class]}")


def _difference(prediction: Prediction) -> str:
    """What the newest variant adds to, drops from and changes in the ancestor it is read against."""
    if prediction.diff is None:
        return ""
    diff = prediction.diff
    return ", ".join(
        [f"+{item.component} {_amount(item)}" for item in diff.added]
        + [f"-{item.component} {_amount(item)}" for item in diff.removed]
        # Both units are printed: a component whose unit alone moved is a quantity difference too.
        + [f"{change.component} {_amount(change.left)} -> {_amount(change.right)}" for change in diff.quantity_changed]
    )


def _unsafe(prediction: Prediction, components: list[str], conflicts: Mapping[str, tuple[Attribute, ...]]) -> str:
    """Which parts of a reuse carry a conflict, on the row that proposes the reuse.

    The parts are those of the newest variant's sub-assembly: they are what the new tender would
    take over. A *specific* row proposes no reuse, so there is nothing to warn it against.
    """
    if prediction.reuse_class is ReuseClass.SPECIFIC:
        return ""
    flagged = [f"{component} ({'/'.join(conflicts[component])})" for component in components if component in conflicts]
    return f"[check: {', '.join(flagged)}]" if flagged else ""


#: How many findings of each conflict type the summary shows; the rest are in the artifact.
_EXAMPLES: int = 3


def _print_inconsistencies(findings: tuple[Finding, ...]) -> None:
    """The second half of the question: components whose rows disagree, by type, a few examples each.

    Always the three lines, in the order the checks run: "cost 0" is an answer too. Every
    finding is in `findings.json`; this block says how many and shows the first ones.
    """
    by_attribute: dict[Attribute, list[Finding]] = {attribute: [] for attribute in CONFLICT_RULES.values()}
    for finding in findings:
        if finding.rule_id in CONFLICT_RULES:
            by_attribute[CONFLICT_RULES[finding.rule_id]].append(finding)
    print(f"inconsistencies   {sum(len(found) for found in by_attribute.values())} components whose rows disagree")
    for attribute, found in by_attribute.items():
        print(f"  {attribute:<16}{len(found)}")
        for finding in found[:_EXAMPLES]:
            print(f"    {finding.message}")
        if len(found) > _EXAMPLES:
            print(f"    ... and {len(found) - _EXAMPLES} more in the findings artifact")


def _partial(prediction: Prediction, left_out: Mapping[str, int]) -> str:
    """What this answer could not see, on the row that makes it.

    A line the pipeline could not read shortens a signature, and a shorter signature is a
    smaller sub-assembly to the comparison: without this the reader cannot tell a *reused*
    resting on the whole sub-assembly from one resting on the two lines of it that parsed. The
    `issues` count above says how dirty the file is, not which answer is affected by it.
    """
    unread = left_out[prediction.sub_assembly_id] + left_out.get(prediction.ancestor_id, 0)
    if not unread:
        return ""
    return f"[{unread} line{'s' if unread > 1 else ''} not read]"


def _amount(item: SignatureItem) -> str:
    return f"{item.quantity:g} {item.unit}"


# --- the read-only guard ---------------------------------------------------------------------


def _refusal(artifacts: list[Path], raw_dir: Path) -> str | None:
    """Why these artifacts may not be written, or `None`. Checked before anything is read or written.

    Inputs are read-only (CLAUDE.md rule 3), and a check that cannot be made is a refusal too.
    """
    for artifact in artifacts:
        try:
            refused = _writes_into(artifact, raw_dir)
        except (OSError, RuntimeError) as exc:  # a symlink loop, a name too long: unknown is not safe
            return f"{artifact} cannot be checked against the raw directory ({raw_dir}): {exc}"
        if refused:
            return f"{artifact} would be written inside the raw directory ({raw_dir}), or over one of its files: inputs are read-only"
    return None


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
