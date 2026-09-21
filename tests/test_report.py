"""The static HTML report: one self-contained file, the sponsor's summary first, the evidence after.

The acceptance criteria of issue #7, as tests: the page opens on its own with no asset and no
network, the summary is the first thing on it and carries only figures this run computed, every
finding shows its rows, its rule and its confidence, and every *reusable* answer shows its
ancestor and its exact difference.

Two of them are about what the page must *not* do. It must not count anomalies from the total
number of findings — a component whose rows disagree emits two findings and is one anomaly — and
it must not need editing when a later issue adds a rule: the sections are built from the
catalogue, and a rule put into it renders itself.
"""

import html
import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pytest

from bomreuse import baseline, rules
from bomreuse.checks import CONFLICT_RULES, check, check_notes, conflicts_by_component, flagged_parts, notes_by_component
from bomreuse.cli import main
from bomreuse.ingest import read_raw
from bomreuse.link import link
from bomreuse.model import (
    REPORT_FILE,
    Backtest,
    Finding,
    Prediction,
    RawDataset,
    ReuseClass,
    SourceRow,
)
from bomreuse.notes import KeywordReader, extract
from bomreuse.normalize import normalize
from bomreuse.report import render
from bomreuse.resolve import resolve
from bomreuse.rules import CATALOGUE, Rule
from bomreuse.signatures import backtest, build_signatures
from bomreuse.spec import load_spec

ROOT = Path(__file__).resolve().parents[1]
COMMITTED_RAW = ROOT / "data" / "raw"

#: A naive search of `baseline.py`, as `evaluate` and the report both call one.
Search = Callable[[RawDataset, str, tuple[str, ...]], tuple[Prediction, ...]]


class Run:
    """One pipeline run on the committed dataset, and the page rendered from it."""

    def __init__(self) -> None:
        self.raw = read_raw(COMMITTED_RAW)
        self.dataset = normalize(self.raw)
        self.resolution, findings = resolve(self.dataset)
        # The notes read through the same fallback `run` uses by default, so the page this fixture
        # renders is the one the written report holds.
        note_facts = link(extract(self.dataset.notes, KeywordReader()), self.resolution)
        self.findings = findings + check(self.dataset, self.resolution) + check_notes(self.dataset, self.resolution, note_facts)
        self.signatures = build_signatures(self.dataset, self.resolution)
        self.result = backtest(self.signatures, self.dataset.variants, load_spec().thresholds)

    def page(self, findings: tuple[Finding, ...] | None = None, result: Backtest | None = None) -> str:
        return render(
            self.raw,
            self.dataset,
            self.resolution,
            self.findings if findings is None else findings,
            self.signatures,
            self.result if result is None else result,
        )


@pytest.fixture(scope="module")
def run() -> Run:
    return Run()


@pytest.fixture(scope="module")
def page(run: Run) -> str:
    return run.page()


def section(page: str, name: str) -> str:
    found = re.search(rf'<section id="{name}">(.*?)</section>', page, re.S)
    assert found is not None, f"the page has no {name} section"
    return found.group(1)


def text(fragment: str) -> str:
    """The fragment as a reader sees it: tags dropped, entities read back, whitespace collapsed."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


# --- self-contained ---------------------------------------------------------------------------


def test_the_page_opens_on_its_own_with_no_asset_and_no_network(page: str) -> None:
    """[A6]: one file, inline CSS, nothing to fetch. A report that needs the internet is not on-prem."""
    assert page.startswith("<!DOCTYPE html>")
    assert "<style>" in page and "</style>" in page
    for forbidden in ("<script", "<link", "<img", "<iframe", " src=", "http://", "https://", "@import", "url("):
        assert forbidden not in page, f"the page reaches outside itself: {forbidden}"


def test_the_written_report_is_the_rendered_page(tmp_path: Path, run: Run, page: str) -> None:
    """`bomreuse run` writes what `render` makes of the artifacts it just wrote, byte for byte."""
    out = tmp_path / "out"
    assert main(["run", "--raw", str(COMMITTED_RAW), "--out", str(out)]) == 0
    assert (out / REPORT_FILE).read_text(encoding="utf-8") == page


# --- the sponsor's half ------------------------------------------------------------------------


def test_the_summary_is_the_first_thing_on_the_page(page: str) -> None:
    """R9 and the issue: Bruno Maréchal reads the top of the page and stops there."""
    order = [re.search(rf'<section id="{name}">', page).start() for name in ("summary", "answer", "inconsistencies", "findings", "provenance")]
    assert order == sorted(order)
    assert page.index('<section id="summary">') < page.index("<h2>")  # the summary owns the first heading


def test_the_summary_counts_are_the_ones_this_run_computed(run: Run, page: str) -> None:
    """The three searches, side by side, each with the count it was read off.

    The baselines are re-run here from `baseline.py` rather than read off the page, so a figure
    the report invented would have nothing behind it.
    """
    counted = Counter(prediction.reuse_class for prediction in run.result.predictions)
    already = counted[ReuseClass.REUSED] + counted[ReuseClass.REUSABLE]
    total = len(run.result.predictions)
    summary = text(section(page, "summary"))

    assert f"{total} sub-assemblies, {already} already exist" in summary
    assert f"{counted[ReuseClass.REUSED]} identical and {counted[ReuseClass.REUSABLE]} with a difference" in summary
    assert f"{counted[ReuseClass.SPECIFIC]} are this variant's own" in summary
    for search in (baseline.exact_reference, baseline.same_name):
        found = _found_by_a_naive_search(run, search)
        assert f"{found} of {total}" in summary
    assert f"{already} of {total}" in summary


def test_the_summary_names_the_sub_assemblies_the_reference_search_does_not_find(run: Run, page: str) -> None:
    """The gap, as the sub-assemblies it is made of: a count nobody can check is not evidence."""
    summary = text(section(page, "summary"))
    exact = {prediction.sub_assembly_id for prediction in baseline.exact_reference(run.raw, run.result.target_variant_id, run.result.ancestor_variant_ids) if prediction.reuse_class is ReuseClass.REUSED}
    naive_id = {(group.variant_id, reference): group.id for group in run.dataset.sub_assemblies for reference in group.raw_references}
    found = {naive_id[(variant, reference)] for variant, reference in (identity.split(":", 1) for identity in exact) if (variant, reference) in naive_id}

    missed = [prediction.sub_assembly_id for prediction in run.result.predictions if prediction.reuse_class is not ReuseClass.SPECIFIC and prediction.sub_assembly_id not in found]
    assert f"{len(missed)} of the sub-assemblies placed in an older variant are not found" in summary
    for sub_assembly_id in missed:
        assert sub_assembly_id in summary


def test_the_summary_promises_no_saving_and_sends_the_reader_to_the_scorer(page: str) -> None:
    """Decision 3: no time or money figure anywhere, and a gap that is not passed off as a score."""
    summary = text(section(page, "summary")).lower()
    for invented in ("hour", "day", "week", "eur", "€", "saving", "saved", "roi"):
        assert invented not in summary
    assert "bomreuse evaluate" in summary


def test_the_page_counts_anomalies_from_the_checks_findings_not_from_the_total(run: Run, page: str) -> None:
    """A component whose rows disagree emits two findings and is one anomaly, not two.

    `checks.*` says which value moved where, `resolution.group_conflict` says the merge held.
    Reading the total would tell the sponsor the export has three times the problems it has.
    """
    conflicts = [finding for finding in run.findings if finding.rule_id in CONFLICT_RULES]
    assert len(conflicts) < len(run.findings), "the dataset must carry both kinds for this to test anything"

    summary = text(section(page, "summary"))
    assert f"{len(conflicts)} components carry values that disagree" in summary
    assert f"{len(run.findings)} components" not in summary
    assert f"{len(conflicts)} components carry values that differ" in text(section(page, "inconsistencies"))


def test_each_disagreement_is_listed_once_with_the_resolution_finding_as_its_evidence(run: Run, page: str) -> None:
    inconsistencies = section(page, "inconsistencies")
    conflicts = [finding for finding in run.findings if finding.rule_id in CONFLICT_RULES]
    assert len(re.findall(r"<tr>", inconsistencies)) == len(conflicts) + 1  # the header row
    for finding in conflicts:
        assert html.escape(finding.message, quote=True) in inconsistencies
    assert "resolution.group_conflict" in inconsistencies, "the merge that held is cited as evidence"


# --- the engineer's half -----------------------------------------------------------------------


def test_every_finding_shows_its_source_rows_its_rule_and_its_confidence(run: Run, page: str) -> None:
    """R11, on the page a reviewer opens rather than in the artifact behind it."""
    assert run.findings
    for finding in run.findings:
        assert html.escape(finding.message, quote=True) in page
        assert finding.rule_id in page
        assert f"confidence {finding.confidence:g}" in page
        for row in finding.source_rows:
            assert f"{row.source_file} row {row.row_number} ({row.row_id})" in page


def test_every_rule_that_fired_is_described_from_the_catalogue(run: Run, page: str) -> None:
    for rule_id in {finding.rule_id for finding in run.findings}:
        assert html.escape(CATALOGUE[rule_id].description, quote=True) in page


def test_a_rule_a_later_issue_adds_renders_without_a_line_changing_here(run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    """The report must not break, or need editing, depending on whether the notes issue landed."""
    invented = Rule(id="link.note_contradicts_bom", description="A note says the opposite of the BOM row.", confidence=0.6)
    monkeypatch.setitem(CATALOGUE, invented.id, invented)
    finding = invented.finding(subject="C:SA0101", message="Note N001 replaces BGI-2031.", source_rows=(SourceRow(source_file="notes.csv", row_number=1, row_id="N001"),))

    page = run.page(findings=run.findings + (finding,))
    assert invented.id in page
    assert html.escape(invented.description, quote=True) in page
    assert "notes.csv row 1 (N001)" in page
    assert "confidence 0.6" in page


def test_every_reusable_answer_shows_its_ancestor_and_its_exact_difference(run: Run, page: str) -> None:
    answer = section(page, "answer")
    spellings = {component.id: component.raw_references for group in run.resolution.groups for component in group.components}
    reusable = [prediction for prediction in run.result.predictions if prediction.reuse_class is ReuseClass.REUSABLE]
    assert reusable, "the committed dataset plants near-reuse: without it this asserts nothing"

    for prediction in reusable:
        assert prediction.ancestor_id in answer
        assert prediction.diff is not None
        for item in (*prediction.diff.added, *prediction.diff.removed):
            assert f"{item.quantity:g} {item.unit}" in answer
            assert any(html.escape(reference.strip(), quote=True) in answer for reference in spellings[item.component])
        for change in prediction.diff.quantity_changed:
            assert f"{change.left.quantity:g} {change.left.unit}" in answer
            assert f"{change.right.quantity:g} {change.right.unit}" in answer


def test_every_reuse_row_flags_the_parts_the_stdout_summary_flags_notes_included(run: Run, page: str) -> None:
    """Decision 34: a part a note speaks against is on the row that proposes the reuse, as on stdout.

    The braking unit is the demo's row — *reused*, and one of its parts declared obsolete by a
    note — so a page flagging value conflicts only would hide the one reuse the README warns about.
    """
    conflicts, notes = conflicts_by_component(run.findings), notes_by_component(run.findings)
    contents = {signature.sub_assembly_id: tuple(item.component for item in signature.signature.items) for signature in run.signatures}
    rows = {found.group(1): found.group(0) for found in re.finditer(r'<tr><td>.*?<span class="id">(.*?)</span>.*?</tr>', section(page, "answer"), re.S)}
    reuses = [prediction for prediction in run.result.predictions if prediction.reuse_class is not ReuseClass.SPECIFIC]

    note_flagged = 0
    for prediction in reuses:
        flags = re.findall(r'<span class="attr">(.*?)</span>', rows[prediction.sub_assembly_id])
        expected = [", ".join(labels) for _, labels in flagged_parts(contents[prediction.sub_assembly_id], conflicts, notes)]
        assert flags == expected, prediction.sub_assembly_id
        note_flagged += any(component in notes for component in contents[prediction.sub_assembly_id])
    assert note_flagged, "the committed dataset plants unsafe reuse: without it this asserts nothing"
    assert f"{note_flagged} of the {len(reuses)} reuse proposals contain a part a note declares" in text(section(page, "summary"))


def test_every_sub_assembly_of_the_new_tender_is_on_the_page_with_its_class(run: Run, page: str) -> None:
    answer = section(page, "answer")
    for prediction in run.result.predictions:
        assert prediction.sub_assembly_id in answer
    for reuse_class in ReuseClass:
        assert f'<span class="badge {reuse_class}">{reuse_class}</span>' in answer


def test_the_provenance_says_what_the_run_read(run: Run, page: str) -> None:
    provenance = text(section(page, "provenance"))
    assert f"{len(run.dataset.lines)}" in provenance
    assert f"{len(run.resolution.groups)} candidate groups" in provenance
    assert f"version {rules.CATALOGUE_VERSION}" in provenance
    for variant in run.dataset.variants:
        assert variant.id in provenance


# --- what the page must survive ------------------------------------------------------------------


def test_a_finding_carrying_markup_is_escaped_not_rendered(run: Run) -> None:
    """The messages are built from cells of a client export: they are text, and they stay text."""
    finding = rules.DUPLICATE_REFERENCE.finding(
        subject="<b>subject</b>",
        message="<script>alert('x')</script> & 'quoted'",
        source_rows=(SourceRow(source_file="bom.csv", row_number=1, row_id="<i>L1</i>"),),
    )
    page = run.page(findings=run.findings + (finding,))
    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page
    assert "<b>subject</b>" not in page


def test_a_dataset_no_variant_can_be_the_new_tender_of_still_renders(run: Run) -> None:
    """`backtest` answers nothing when no design date can be read; the page says so and holds together."""
    page = run.page(result=Backtest(target_variant_id="", ancestor_variant_ids=(), predictions=()))
    assert "no variant carries a readable design date" in page.lower()
    assert page.startswith("<!DOCTYPE html>") and page.rstrip().endswith("</html>")


def test_a_run_with_no_finding_still_renders(run: Run) -> None:
    page = run.page(findings=())
    assert "This run produced no finding." in page
    assert "0 components carry values that disagree" in text(section(page, "summary"))


def _found_by_a_naive_search(run: Run, search: Search) -> int:
    """How many of the new tender's sub-assemblies one naive search says already exist."""
    predictions = search(run.raw, run.result.target_variant_id, run.result.ancestor_variant_ids)
    return sum(1 for prediction in predictions if prediction.reuse_class is ReuseClass.REUSED)
