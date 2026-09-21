"""The static HTML report: the sponsor's summary first, the engineer's evidence after.

Two readers, in that order (PRD §2, R9). Bruno Maréchal, the pilot sponsor, reads the top of the
page — what this run found that the search the client already has does not, as counts taken off
the run and nothing else. Thomas Lindqvist, lead data engineer, reads everything under it: the
new tender sub-assembly by sub-assembly with the exact difference behind every *reusable*
answer, then every finding with the rule that produced it, that rule's confidence and the rows
of `bom.csv` it was read from.

`string.Template` and inline CSS: one self-contained file, no asset, no script, no network
([A6], docs/ARCHITECTURE.md A8). A template engine is not worth a dependency for one template.

Three properties the module is shaped around:

- **Nothing on the page that this run did not compute.** No time and no money figure, here or
  anywhere (Decision 3). The gap at the top is the naive searches of `baseline.py`, run on the
  same raw rows — a comparison of what each search *finds*, which is a fact about the files, and
  not a score. Scoring needs the labels the dataset was generated with, which no pipeline module
  may read; `bomreuse evaluate` does that, and the page sends the reader there rather than
  letting the gap read as a score.
- **Findings render off the rule catalogue**, grouped by the `rule_id` the findings carry and
  described from `rules.CATALOGUE`, so a rule a later issue adds renders itself.
- **Inconsistencies are counted from the `checks.*` findings**, never from the total. A component
  whose rows disagree produces two findings — `resolution.group_conflict`, which says the merge
  held, and a `checks.*` one, which says which value moved where — and that is one anomaly, not
  two. The conflict is listed once, with the resolution finding under it as evidence.
"""

import html
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Final

from bomreuse import baseline
from bomreuse.checks import CONFLICT_RULES, conflicting_parts, conflicts_by_component
from bomreuse.model import (
    REPORT_FILE,
    RUN_ARTIFACTS,
    Attribute,
    Backtest,
    Finding,
    GroupVerdict,
    NormalizedDataset,
    Prediction,
    RawDataset,
    Resolution,
    ReuseClass,
    SignatureItem,
    SubAssemblySignature,
)
from bomreuse.rules import CATALOGUE, CATALOGUE_VERSION, GROUP_CONFLICT

_TITLE: Final[str] = "Sub-assembly reuse across train variants"

#: The order the rule sections appear in: the catalogue's own, then anything it does not know,
#: by id. Two runs write the same page, and a reviewer reads the rules in the order they are declared.
_RULE_ORDER: Final[Mapping[str, int]] = {rule_id: index for index, rule_id in enumerate(CATALOGUE)}


@dataclass(frozen=True, slots=True)
class _Read:
    """One run's artifacts, indexed the way the page reads them.

    Built once by `render`, so no section walks a tuple looking for an id and the page cannot
    show two different readings of the same artifact.
    """

    raw: RawDataset
    dataset: NormalizedDataset
    resolution: Resolution
    findings: tuple[Finding, ...]
    result: Backtest
    #: sub-assembly id -> its designations, its canonical components, its unread BOM lines
    names: Mapping[str, str]
    contents: Mapping[str, tuple[str, ...]]
    left_out: Mapping[str, int]
    #: canonical component id -> how to call it in a sentence
    parts: Mapping[str, str]
    #: canonical component id -> the attributes its rows disagree on
    conflicts: Mapping[str, tuple[Attribute, ...]]


def render(
    raw: RawDataset,
    dataset: NormalizedDataset,
    resolution: Resolution,
    findings: tuple[Finding, ...],
    signatures: tuple[SubAssemblySignature, ...],
    result: Backtest,
) -> str:
    """The whole page, as text. It reads the artifacts of one run and opens no file."""
    read = _Read(
        raw=raw,
        dataset=dataset,
        resolution=resolution,
        findings=findings,
        result=result,
        names={signature.sub_assembly_id: " / ".join(signature.designations) for signature in signatures},
        contents={signature.sub_assembly_id: tuple(item.component for item in signature.signature.items) for signature in signatures},
        left_out={signature.sub_assembly_id: signature.lines_left_out for signature in signatures},
        parts=_parts(resolution),
        conflicts=conflicts_by_component(findings),
    )
    return _PAGE.substitute(
        title=_esc(_TITLE),
        css=_CSS,
        lead=_lead(read),
        summary=_summary(read),
        answer=_answer(read),
        inconsistencies=_inconsistencies(read),
        findings=_findings(read),
        provenance=_provenance(read),
    )


def dump_report(page: str, path: Path) -> None:
    """Write the page, with the line endings the JSON artifacts are written with."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8", newline="\n")


# --- the sponsor's half --------------------------------------------------------------------


def _lead(read: _Read) -> str:
    if not read.result.target_variant_id:
        return '<p class="lead">No variant carries a readable design date, so none could be played as a new tender.</p>'
    older = ", ".join(_variant(read, variant_id) for variant_id in read.result.ancestor_variant_ids)
    return (
        f'<p class="lead">{_esc(_variant(read, read.result.target_variant_id))} is read as a new tender against the '
        f"{len(read.result.ancestor_variant_ids)} variants designed before it: {_esc(older)}.</p>"
    )


def _summary(read: _Read) -> str:
    """The first thing on the page: what the run found, and what a naive search finds instead.

    Every number here is counted off this run's own answers, and the three searches answer the
    same question about the same sub-assemblies. What is compared is *what each search finds* —
    whether it is right is a question this page does not answer, and the last paragraph says
    where it is answered.
    """
    counted = Counter(prediction.reuse_class for prediction in read.result.predictions)
    already = counted[ReuseClass.REUSED] + counted[ReuseClass.REUSABLE]
    total = len(read.result.predictions)

    exact = _found_by(read, baseline.exact_reference)
    by_name = _found_by(read, baseline.same_name)
    unfound = [prediction.sub_assembly_id for prediction in _reuses(read) if not exact.get(prediction.sub_assembly_id, False)]
    named_but_specific = sum(1 for prediction in read.result.predictions if prediction.reuse_class is ReuseClass.SPECIFIC and by_name.get(prediction.sub_assembly_id, False))
    named_but_changed = sum(1 for prediction in read.result.predictions if prediction.reuse_class is ReuseClass.REUSABLE and by_name.get(prediction.sub_assembly_id, False))

    counts = _conflict_counts(read.findings)
    flagged = sum(1 for prediction in _reuses(read) if conflicting_parts(read.contents[prediction.sub_assembly_id], read.conflicts))
    searches = _table(
        ("How the question is asked", "Says the sub-assembly already exists"),
        [
            (_esc("the content of the sub-assembly, part by part — this tool"), f"<strong>{already}</strong> of {total}"),
            (_esc("the reference, character for character"), f"{sum(exact.values())} of {total}"),
            (_esc("the designation, case and spacing aside"), f"{sum(by_name.values())} of {total}"),
        ],
    )
    missed = ", ".join(f"{_esc(read.names[sub_assembly_id])} ({_esc(sub_assembly_id)})" for sub_assembly_id in unfound)
    return f"""<section id="summary">
<h2>What this run found</h2>
<p class="headline">Of the new tender's <strong>{total}</strong> sub-assemblies, <strong>{already}</strong> already exist in a variant
designed earlier — <strong>{counted[ReuseClass.REUSED]}</strong> identical and <strong>{counted[ReuseClass.REUSABLE]}</strong> with a
difference this report lists part by part — and <strong>{counted[ReuseClass.SPECIFIC]}</strong> are this variant's own.</p>
{searches}
<ul class="reading">
<li><strong>{len(unfound)}</strong> of the sub-assemblies placed in an older variant are not found by the reference search:
{missed or "none"}.</li>
<li>The designation search claims an older source for <strong>{named_but_specific}</strong> sub-assembl{_plural(named_but_specific, "y", "ies")}
the tool finds nowhere, and for <strong>{named_but_changed}</strong> whose content differs from that older one: a namesake does not
tell identical from changed.</li>
<li><strong>{sum(counts.values())}</strong> components carry values that disagree between variants ({_listed(counts)}); {flagged} of the
{already} reuse proposals contain at least one of them, and say so on their row.</li>
</ul>
<p class="caveat">Every figure on this page was computed by the run that wrote it. No time or money figure appears anywhere in this
report: those are defined with the client. How many of these answers are <em>right</em> is not measured here —
<code>bomreuse evaluate</code> scores them against the labels the dataset was generated with, which this pipeline never reads, and
the README quotes what it prints.</p>
</section>"""


def _found_by(read: _Read, search: Callable[[RawDataset, str, tuple[str, ...]], tuple[Prediction, ...]]) -> dict[str, bool]:
    """Which of the new tender's sub-assemblies a naive search says already exist, named as the tool names them.

    A baseline names a sub-assembly by the raw reference the file carries and the tool by the
    folded key, and one sub-assembly may be spelled several ways: it counts as found when any of
    its spellings is. Reconciling the two identities is what lets the summary put the three
    searches in one table; `evaluate.Predictor` does the same for the score.
    """
    answers = {prediction.sub_assembly_id: prediction for prediction in search(read.raw, read.result.target_variant_id, read.result.ancestor_variant_ids)}
    naive_id = baseline.sub_assembly_ids(read.raw)
    found: dict[str, bool] = {}
    for group in read.dataset.sub_assemblies:
        if group.variant_id != read.result.target_variant_id:
            continue
        spellings = [naive_id[key] for reference in group.raw_references if (key := (group.variant_id, reference)) in naive_id]
        found[group.id] = any(answers[naive].reuse_class is ReuseClass.REUSED for naive in spellings if naive in answers)
    return found


def _reuses(read: _Read) -> list[Prediction]:
    """The predictions that propose a reuse: the rows a conflict has to be checked against."""
    return [prediction for prediction in read.result.predictions if prediction.reuse_class is not ReuseClass.SPECIFIC]


# --- the engineer's half -------------------------------------------------------------------


def _answer(read: _Read) -> str:
    """The new tender, sub-assembly by sub-assembly: the class, the older one it rests on, the difference."""
    rows = []
    for prediction in read.result.predictions:
        ancestor = _named(read.names.get(prediction.ancestor_id, ""), prediction.ancestor_id) if prediction.ancestor_id else "&mdash;"
        rows.append(
            (
                _named(read.names[prediction.sub_assembly_id], prediction.sub_assembly_id),
                f'<span class="badge {prediction.reuse_class}">{_esc(prediction.reuse_class)}</span>',
                ancestor,
                _difference(read, prediction) + _partial(read, prediction),
                _flags(read, prediction),
            )
        )
    return f"""<section id="answer">
<h2>The new tender, sub-assembly by sub-assembly</h2>
<p>Each sub-assembly of the newest variant against the variants designed before it, compared on the multiset of parts it contains.
<em>reused</em> means an older sub-assembly holds exactly the same parts in the same quantities; <em>reusable</em> that it is within
the threshold written in <code>data/dataset_spec.toml</code>, and the difference is the one shown; <em>specific</em> that neither was
the case.</p>
{_table(("Sub-assembly", "Class", "Already exists as", "Difference to check", "Parts whose data disagrees"), rows)}
</section>"""


def _difference(read: _Read, prediction: Prediction) -> str:
    """What the new tender adds to, drops from and changes in the older sub-assembly it is read against."""
    if prediction.diff is None:
        return "&mdash;"
    diff = prediction.diff
    items = (
        [f'<li class="added">adds {_part(read, item)}</li>' for item in diff.added]
        + [f'<li class="removed">drops {_part(read, item)}</li>' for item in diff.removed]
        # Both amounts are shown: a part whose unit alone moved is a quantity difference too.
        + [f'<li class="changed">{_label(read, change.component)} {_amount(change.left)} &rarr; {_amount(change.right)}</li>' for change in diff.quantity_changed]
    )
    return f'<ul class="diff">{"".join(items)}</ul>' if items else "&mdash;"


def _partial(read: _Read, prediction: Prediction) -> str:
    """What this answer could not see, on the row that makes it.

    A line the pipeline could not read shortens a signature, and a shorter signature is a smaller
    sub-assembly to the comparison: a reader must be able to tell a *reused* resting on the whole
    sub-assembly from one resting on the lines of it that parsed.
    """
    unread = read.left_out[prediction.sub_assembly_id] + read.left_out.get(prediction.ancestor_id, 0)
    if not unread:
        return ""
    return f'<p class="warn">{unread} BOM line{_plural(unread, "", "s")} of this comparison could not be read.</p>'


def _flags(read: _Read, prediction: Prediction) -> str:
    """The parts of a proposed reuse whose rows disagree somewhere in the dataset.

    The rule is `checks.conflicting_parts`, the one the stdout summary flags with; what each
    disagreement is, variant by variant, is in *Where the data disagrees* below.
    """
    if prediction.reuse_class is ReuseClass.SPECIFIC:
        return "&mdash;"
    flagged = conflicting_parts(read.contents[prediction.sub_assembly_id], read.conflicts)
    if not flagged:
        return "&mdash;"
    listed = "".join(f'<li>{_label(read, component)} <span class="attr">{_esc(", ".join(attributes))}</span></li>' for component, attributes in flagged)
    return f'<ul class="flags">{listed}</ul>'


def _inconsistencies(read: _Read) -> str:
    """Every component whose rows disagree, once each, with the resolution finding as its evidence.

    One disagreement, two findings: a `checks.*` one saying which value moved where, and
    `resolution.group_conflict` saying the merge held despite it. Counting both would read as two
    anomalies where the data has one, so the count and the rows come from the `checks.*` side.
    """
    key_of = {component.id: component.reference_key for group in read.resolution.groups for component in group.components}
    held: dict[str, list[Finding]] = defaultdict(list)
    for finding in read.findings:
        if finding.rule_id == GROUP_CONFLICT.id:
            held[finding.subject].append(finding)

    conflicts = [finding for finding in read.findings if finding.rule_id in CONFLICT_RULES]
    rows = []
    for finding in conflicts:
        merged = held.get(key_of.get(finding.subject, ""), ())
        evidence = f'<p class="evidence">{_esc(merged[0].message)} <span class="id">{_esc(GROUP_CONFLICT.id)}</span></p>' if merged else ""
        rows.append(
            (
                _named(read.parts.get(finding.subject, ""), finding.subject),
                _esc(CONFLICT_RULES[finding.rule_id]),
                f"{_esc(finding.message)}{evidence}",
                _rule_cell(finding),
                _rows_cell(finding),
            )
        )
    return f"""<section id="inconsistencies">
<h2>Where the data disagrees</h2>
<p><strong>{len(conflicts)}</strong> components carry values that differ from one variant to the next ({_listed(_conflict_counts(read.findings))}),
after normalization: <code>1000 mm</code> against <code>1 m</code>, or <code>12,50</code> against <code>12.50</code>, is agreement.
The part stays one part and stays in the signatures — a supplier that moves is not a different product — and the disagreement is what
a human has to settle. Each one is listed once; the line under it is the resolution finding, the evidence that the merge held in
spite of it.</p>
{_table(("Component", "Disagrees on", "What the rows say", "Rule", "Source rows"), rows)}
</section>"""


def _findings(read: _Read) -> str:
    """Every finding of the run, grouped by the rule that produced it.

    Nothing here names a rule: the sections are built from the `rule_id` values the findings
    carry and described from the catalogue, so a rule a later issue adds renders itself.
    """
    by_rule: dict[str, list[Finding]] = defaultdict(list)
    for finding in read.findings:
        by_rule[finding.rule_id].append(finding)

    blocks = []
    for rule_id in sorted(by_rule, key=lambda rule_id: (_RULE_ORDER.get(rule_id, len(_RULE_ORDER)), rule_id)):
        found = by_rule[rule_id]
        rule = CATALOGUE.get(rule_id)
        rows = [(_esc(finding.subject), _esc(finding.message), _rows_cell(finding)) for finding in found]
        blocks.append(
            f'<h3>{_esc(rule_id)}<span class="count">{len(found)} finding{_plural(len(found), "", "s")}</span>'
            f'<span class="confidence">confidence {found[0].confidence:g}</span></h3>'
            f'{f"<p>{_esc(rule.description)}</p>" if rule is not None else ""}'
            f"{_table(('Subject', 'What the rule read', 'Source rows'), rows)}"
        )
    total = len(read.findings)
    return f"""<section id="findings">
<h2>Every finding, with its evidence</h2>
<p><strong>{total}</strong> findings in all &mdash; which is not {total} data problems: a component whose rows disagree produces one
finding for the disagreement and one saying the merge held, and both are listed here. The count of anomalies is the one in
<em>Where the data disagrees</em> above.</p>
{"".join(blocks) or "<p>This run produced no finding.</p>"}
</section>"""


def _provenance(read: _Read) -> str:
    """What the run read and what it made of it: the page says where its own figures come from."""
    verdicts = Counter(group.verdict for group in read.resolution.groups)
    rows = [
        ("BOM lines read", str(len(read.dataset.lines))),
        ("Variants", _esc(", ".join(_variant(read, variant.id) for variant in read.dataset.variants))),
        ("References", f"{len(read.resolution.groups)} candidate groups &rarr; {len(read.resolution.components)} canonical components"),
        ("Group verdicts", _esc(", ".join(f"{verdict} {verdicts[verdict]}" for verdict in GroupVerdict))),
        ("Values that could not be read", str(len(read.dataset.issues))),
        ("Findings", str(len(read.findings))),
        ("Rule catalogue", _esc(f"version {CATALOGUE_VERSION}")),
    ]
    # The siblings are read from the one place they are named, so an artifact a later issue adds
    # is listed here without this paragraph being edited.
    siblings = ", ".join(f"<code>{_esc(name)}</code>" for name in RUN_ARTIFACTS if name != REPORT_FILE)
    return f"""<section id="provenance">
<h2>What this was read from</h2>
<p>Written by <code>bomreuse run</code> from the raw CSV exports alone. The artifacts beside this file &mdash; {siblings} &mdash;
carry the same content as data.</p>
{_table(("", ""), rows)}
</section>"""


# --- small helpers -------------------------------------------------------------------------


def _parts(resolution: Resolution) -> dict[str, str]:
    """Canonical component id -> how to call it in a sentence: its designation, and a spelling of its reference.

    The id is a folded key (`11GHTCAB1E`), which nobody types and nobody searches the export for;
    the spellings behind it are what `resolution.duplicate_reference` lists.
    """
    labels = {}
    for component in resolution.components:
        reference = component.raw_references[0].strip() if component.raw_references else component.id
        designation = component.designations[0] if component.designations else ""
        labels[component.id] = f"{designation} ({reference})" if designation else reference
    return labels


def _variant(read: _Read, variant_id: str) -> str:
    for variant in read.dataset.variants:
        if variant.id == variant_id:
            return f"{variant.id} ({variant.name.normalized}, designed {variant.design_date.normalized})"
    return variant_id


def _conflict_counts(findings: Iterable[Finding]) -> dict[Attribute, int]:
    """How many components disagree on each attribute, from the `checks.*` findings and nothing else."""
    counted = Counter(CONFLICT_RULES[finding.rule_id] for finding in findings if finding.rule_id in CONFLICT_RULES)
    return {attribute: counted[attribute] for attribute in CONFLICT_RULES.values()}


def _listed(counts: Mapping[Attribute, int]) -> str:
    return ", ".join(f"{count} on {attribute}" for attribute, count in counts.items())


def _plural(count: int, one: str, many: str) -> str:
    return one if count == 1 else many


def _named(name: str, identifier: str) -> str:
    return f'{_esc(name)}<br><span class="id">{_esc(identifier)}</span>'


def _label(read: _Read, component: str) -> str:
    return _esc(read.parts.get(component, component))


def _part(read: _Read, item: SignatureItem) -> str:
    return f"{_label(read, item.component)} {_amount(item)}"


def _amount(item: SignatureItem) -> str:
    return _esc(f"{item.quantity:g} {item.unit}")


def _rule_cell(finding: Finding) -> str:
    return f'<span class="id">{_esc(finding.rule_id)}</span><br><span class="confidence">confidence {finding.confidence:g}</span>'


def _rows_cell(finding: Finding) -> str:
    return "<br>".join(_esc(f"{row.source_file} row {row.row_number} ({row.row_id})") for row in finding.source_rows)


def _table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    """A table from cells that are already HTML: every caller escapes what it puts in them."""
    head = "".join(f"<th>{header}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


# --- the page ------------------------------------------------------------------------------

_CSS: Final[str] = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0 auto; padding: 2rem 1.5rem 4rem; max-width: 64rem; background: #fbfbfa; color: #1d1d1b;
  font: 16px/1.55 -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
header { border-bottom: 3px solid #1d1d1b; padding-bottom: 1rem; margin-bottom: 2rem; }
h1 { font-size: 1.9rem; margin: 0 0 .4rem; }
h2 { font-size: 1.35rem; margin: 2.6rem 0 .6rem; }
h3 { font-size: .95rem; margin: 1.8rem 0 .3rem;
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
p, li { margin: .5rem 0; }
.lead { color: #55554f; margin: 0; }
.headline { font-size: 1.1rem; }
.reading li { margin: .45rem 0; }
.caveat { color: #55554f; font-size: .9rem; border-left: 3px solid #d8d8d2; padding-left: .9rem; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .9rem; }
th, td { text-align: left; vertical-align: top; padding: .45rem .6rem; border-bottom: 1px solid #e3e3dd; }
th { background: #f0f0ea; font-weight: 600; }
#provenance thead { display: none; }
#provenance td:first-child { width: 18rem; color: #55554f; }
.id, .attr, .confidence, .count { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  font-size: .8rem; color: #6a6a62; font-weight: normal; }
.count, .confidence { margin-left: .8rem; }
code { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: .85em;
  background: #f0f0ea; padding: .05rem .3rem; }
.badge { display: inline-block; padding: .1rem .55rem; border-radius: .7rem; font-size: .8rem; font-weight: 600; }
.badge.reused { background: #d9ecd9; color: #1d4d21; }
.badge.reusable { background: #fbedc9; color: #6b4c05; }
.badge.specific { background: #e6e6e0; color: #45453f; }
ul.diff, ul.flags { margin: 0; padding-left: 1.2rem; }
ul.diff li.added::marker { content: "+ "; }
ul.diff li.removed::marker { content: "\\2212  "; }
ul.diff li.changed::marker { content: "~ "; }
.evidence { color: #55554f; font-size: .85rem; margin: .4rem 0 0; }
.warn { color: #8a4b00; font-size: .85rem; margin: .4rem 0 0; }
"""

_PAGE: Final[Template] = Template(
    """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<style>$css</style>
</head>
<body>
<header>
<h1>$title</h1>
$lead
</header>
$summary
$answer
$inconsistencies
$findings
$provenance
</body>
</html>
"""
)
