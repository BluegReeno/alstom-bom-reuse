"""Note extraction: what a free-text note asserts about a component, in the note's own words.

One task, and one only (docs/ARCHITECTURE.md A6): turn a note into zero or more `NoteFact`s —
a replacement, an obsolescence, a restriction — each citing the note it was read from. Nothing
here matches a reference against the BOM: the facts carry the **raw** string the note writes,
and `link.py` is the only module that turns one into a canonical component (A7).

Two readers implement the same protocol:

- `KeywordReader`, below, is what makes CLAUDE.md rule 5 hold: the whole pipeline runs with no
  network at all. It is the default, and it is not a degraded mode — it is the offline path.
- `ModelReader` reads the same notes through one local model. It is opt-in, because a tool whose
  demo needs a server running is a tool that does not demo.

**The lexicon below was written from the note patterns the brief and `CONTEXT.md` quote** —
*remplacé par…*, *obsolete since…*, *ne pas utiliser sur…*, *do not use on 4-car* — and from
nothing else. `data/raw/notes.csv` and the generator's note catalogue were not opened while
writing it, deliberately: a lexicon fitted to the forty synthetic notes would score whatever the
build asked of it and would measure nothing. What it misses on the committed dataset is a
result, reported in the README, not a bug to patch.

What it cannot do is the honest part of the answer to "where does an LLM earn its place?". It
reads cue phrases and reference-shaped tokens; it does not read a sentence. A note citing a part
next to a stock phrase while asserting nothing — a proposal that was refused, a question still
open — looks exactly like a note asserting it.
"""

import hashlib
import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, ValidationError

from bomreuse.model import FactKind, Note, NoteFact

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Reading:
    """What a reader made of one note.

    `invalid_outputs` counts what the reader produced and could not use. It is zero for a reader
    that cannot produce anything unusable, and the point of the field is the one that can.
    """

    facts: tuple[NoteFact, ...]
    invalid_outputs: int


class NoteReader(Protocol):
    """One note per call (A6). A batch that a single invalid output poisons loses the other thirty-nine."""

    #: How the reader is named in the artifact and on a finding: a reviewer must know which one ran.
    name: str

    def read(self, note: Note) -> Reading: ...


@dataclass(frozen=True, slots=True)
class Extraction:
    """Every fact the reader found in the notes, and what it cost to find them."""

    reader: str
    notes_read: int
    invalid_outputs: int
    facts: tuple[NoteFact, ...]


def extract(notes: Iterable[Note], reader: NoteReader) -> Extraction:
    """Read every note, one call at a time, and keep what each one asserts."""
    facts: list[NoteFact] = []
    invalid = 0
    read = 0
    for note in notes:
        read += 1
        reading = reader.read(note)
        facts.extend(reading.facts)
        invalid += reading.invalid_outputs
    return Extraction(reader=reader.name, notes_read=read, invalid_outputs=invalid, facts=tuple(facts))


# --- the FR/EN keyword fallback ------------------------------------------------------------------

#: The cue phrases of each kind, French and English side by side in one list per kind: a note may
#: switch language inside one sentence, so there is no language to detect and nothing to branch on.
_CUES: Final[dict[FactKind, tuple[str, ...]]] = {
    FactKind.REPLACEMENT: (
        "remplacé par",
        "remplacée par",
        "remplacés par",
        "remplacées par",
        "remplacer par",
        "remplacement par",
        "replaced by",
        "replaced with",
        "superseded by",
    ),
    FactKind.OBSOLESCENCE: (
        "obsolète",
        "obsolete",
        "ne plus utiliser",
        "ne plus commander",
        "ne plus approvisionner",
        "fin de vie",
        "discontinued",
        "end of life",
        "no longer available",
        "no longer ordered",
    ),
    FactKind.RESTRICTION: (
        "ne pas utiliser",
        "ne pas monter",
        "interdit sur",
        "interdite sur",
        "do not use",
        "not to be used",
        "must not be used",
        "not allowed on",
    ),
}

#: Each cue as a pattern over the raw text, so a match keeps the offsets of the characters the
#: note actually holds — the references a fact carries are raw, and an offset into a case-folded
#: copy would not point at them. A space in a cue matches any run of whitespace: an export wraps.
_CUE_PATTERNS: Final[dict[FactKind, re.Pattern[str]]] = {
    kind: re.compile("|".join(re.escape(cue).replace(r"\ ", r"\s+") for cue in cues), re.IGNORECASE)
    for kind, cues in _CUES.items()
}

#: What a reference looks like in running text: a hyphenated or underscored token (`BGI-2031`,
#: `HVAC-GRILLE-12`, `BRK-CTRL-VALVE`), or letters run into digits (`SA0101`, `BGI 2031`).
#: The second branch is uppercase-only on purpose: `mars 2024` has the shape of the first and is
#: a date. A lower-cased reference written with a space is out of reach, and stays out of reach.
_REFERENCE: Final[re.Pattern[str]] = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)+\b|\b[A-Z]{2,}[ ]?[0-9]{2,}\b")

#: Where a sentence ends, for the fragment a restriction is quoted with.
_SENTENCE_END: Final[re.Pattern[str]] = re.compile(r"[.;!?\n]")

#: How much of that sentence is quoted. Long enough for "sur les rames 4 caisses", short enough
#: that the fragment stays a label on a row rather than the note pasted twice.
_SCOPE_LIMIT: Final[int] = 120


class KeywordReader:
    """Cue phrases and reference-shaped tokens, and no interpretation beyond that.

    One fact per kind at most, per note. The subject of an obsolescence or a restriction is the
    **first** reference the note names, and the subject of a replacement is the last reference
    before the cue, its replacement the first one after: that is the whole of the reasoning, and
    saying more about it would be describing a sentence parser this is not.

    A token that only looks like a reference — a hyphenated French word carrying a digit — costs
    nothing: `link.py` finds it in no BOM and the fact is kept unlinked, which is visible in the
    artifact. What does cost is a note that cites a real part while asserting nothing.
    """

    name: str = "keyword"

    def read(self, note: Note) -> Reading:
        references = [match for match in _REFERENCE.finditer(note.text) if _reference_shaped(match.group())]
        facts = [fact for kind in FactKind if (fact := self._fact(note, kind, references)) is not None]
        return Reading(facts=tuple(facts), invalid_outputs=0)

    def _fact(self, note: Note, kind: FactKind, references: list[re.Match[str]]) -> NoteFact | None:
        cue = _CUE_PATTERNS[kind].search(note.text)
        if cue is None or not references:
            return None
        if kind is FactKind.REPLACEMENT:
            return _replacement(note, cue, references)
        scope = _sentence_around(note.text, cue.start()) if kind is FactKind.RESTRICTION else ""
        return NoteFact(
            note_id=note.note_id,
            row_number=note.row_number,
            kind=kind,
            component_ref=references[0].group(),
            replacement_ref="",
            scope=scope,
        )


def _replacement(note: Note, cue: re.Match[str], references: list[re.Match[str]]) -> NoteFact | None:
    """`X remplacé par Y`: the part is what stands before the cue, the replacement what follows it.

    No reference before the cue means the note names no part to replace, and a fact whose subject
    had to be guessed is worse than no fact.
    """
    before = [match for match in references if match.end() <= cue.start()]
    after = [match for match in references if match.start() >= cue.end()]
    if not before:
        return None
    return NoteFact(
        note_id=note.note_id,
        row_number=note.row_number,
        kind=FactKind.REPLACEMENT,
        component_ref=before[-1].group(),
        replacement_ref=after[0].group() if after else "",
        scope="",
    )


def _reference_shaped(token: str) -> bool:
    """A digit somewhere, or nothing but capitals: enough to keep `sous-ensemble` out of the catalogue."""
    return any(character.isdigit() for character in token) or token == token.upper()


def _sentence_around(text: str, position: int) -> str:
    """The sentence the cue sits in, whitespace collapsed, for a human to read on the finding."""
    end = _SENTENCE_END.search(text, position)
    start = max((match.end() for match in _SENTENCE_END.finditer(text, 0, position)), default=0)
    sentence = " ".join(text[start : end.start() if end else len(text)].split())
    return sentence if len(sentence) <= _SCOPE_LIMIT else sentence[: _SCOPE_LIMIT - 1].rstrip() + "…"


# --- the model reader ----------------------------------------------------------------------------

#: The one backend this build wires: the local model, which is the on-prem path (Decision 6, as
#: amended by 29). The id is a constructor argument, so a second model is a flag rather than a
#: rewrite — and this build scores neither.
DEFAULT_MODEL: Final[str] = "gemma4:12b-mlx"

#: The only outbound call this tool ever makes (docs/ARCHITECTURE.md, Boundaries).
DEFAULT_ENDPOINT: Final[str] = "http://localhost:11434/api/generate"

#: Per call, and generous: the first call of a session loads the model into memory.
DEFAULT_TIMEOUT: Final[float] = 120.0

#: A local accelerator, not a deliverable: gitignored, and only ever created by this reader.
DEFAULT_CACHE_DIR: Final[Path] = Path(".cache") / "bomreuse-notes"

#: What the note is asked for. Written to be read by a 12B model: the kinds are defined in one
#: line each, and the two rules that matter — copy references exactly, assert nothing the note
#: does not — are stated rather than implied. `_validated` enforces the first one; nothing can
#: enforce the second, which is the honest limit of the layer.
PROMPT: Final[str] = """You read one technical note about railway components, written in French or English, sometimes both in one sentence.

Extract only the facts the note ASSERTS about a component:
- replacement: a component is replaced by another one.
- obsolescence: a component is obsolete, discontinued, or no longer to be ordered.
- restriction: a component must not be used on some variant or configuration.

Rules:
- Copy every component reference exactly as the note writes it, character for character.
- A question, a proposal or a refusal asserts nothing: return an empty list.
- Do not infer, do not translate, do not repair a reference.

Note:
{text}
"""


class BackendError(RuntimeError):
    """The model could not be reached, or answered with something that is not an answer."""


class Backend(Protocol):
    """Where a prompt is sent. `model` names it, and is half of the cache key."""

    model: str

    def generate(self, prompt: str) -> str: ...


class OllamaBackend:
    """One POST to localhost, `format` set to the schema, a timeout and one retry.

    `urllib.request` from the standard library: a single POST to localhost does not justify a
    client library (docs/ARCHITECTURE.md A6). The retry covers the one failure this call really
    has — the model was not loaded yet and the first request timed out — and not a second one.
    """

    def __init__(self, model: str = DEFAULT_MODEL, endpoint: str = DEFAULT_ENDPOINT, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.model = model
        self._endpoint = endpoint
        self._timeout = timeout

    def generate(self, prompt: str) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "format": _RESPONSE_SCHEMA,
                "stream": False,
                # Extraction is not a creative task, and two runs of a demo should say the same thing.
                "options": {"temperature": 0},
            }
        ).encode("utf-8")
        request = Request(self._endpoint, data=body, headers={"Content-Type": "application/json"})
        try:
            return self._ask(request)
        except (OSError, ValueError, KeyError) as exc:
            logger.warning("%s at %s failed (%s); retrying once", self.model, self._endpoint, exc)
        try:
            return self._ask(request)
        except (OSError, ValueError, KeyError) as exc:
            raise BackendError(f"{self.model} at {self._endpoint} did not answer: {exc}") from exc

    def _ask(self, request: Request) -> str:
        """The POST itself. A body that is not an Ollama answer raises like a refused connection does."""
        with urlopen(request, timeout=self._timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return str(payload["response"])


class ModelReader:
    """One note per call, validated at the boundary, and cached on disk.

    The output is the second of the two places data arrives from outside this tool, so it is the
    second of the two places pydantic guards (DECISIONS.md 19). Everything the model returns is
    suspect: the shape, by validation, and the references, by the one check a program can make on
    free text — **a reference a fact carries must appear verbatim in the note**. A model that
    tidies `Bgi-2031` into `BGI-2031`, or names a part the note never mentions, has invented the
    evidence the finding would rest on.

    Nothing is dropped in silence: every answer that fails, and every fact rejected inside a
    valid answer, is logged and counted into `Reading.invalid_outputs`.
    """

    def __init__(self, backend: Backend, cache: Path | None = DEFAULT_CACHE_DIR) -> None:
        self.name = f"llm:{backend.model}"
        self._backend = backend
        self._cache = cache

    def read(self, note: Note) -> Reading:
        prompt = PROMPT.format(text=note.text)
        answer = self._cached(note, prompt)
        if answer is None:
            answer = self._backend.generate(prompt)
            self._store(note, prompt, answer)
        return _validated(note, answer)

    # The cache is keyed by (model, prompt hash, note id), and a cache that cannot be read or
    # written is not an error: it is an accelerator, and the model is the source of truth.

    def _cached(self, note: Note, prompt: str) -> str | None:
        path = self._entry(note, prompt)
        if path is None:
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    def _store(self, note: Note, prompt: str, answer: str) -> None:
        path = self._entry(note, prompt)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(answer, encoding="utf-8")
        except OSError as exc:
            logger.warning("the note cache at %s cannot be written (%s); running without it", path.parent, exc)

    def _entry(self, note: Note, prompt: str) -> Path | None:
        if self._cache is None:
            return None
        digest = hashlib.sha256(f"{self._backend.model}\n{prompt}".encode()).hexdigest()
        return self._cache / f"{_slug(self._backend.model)}-{_slug(note.note_id)}-{digest[:16]}.json"


class _ModelFact(BaseModel):
    """The shape one extracted fact must have. `extra="ignore"`: a field too many is not a reason to lose the fact."""

    model_config = ConfigDict(extra="ignore")

    kind: FactKind
    component_ref: str
    replacement_ref: str = ""
    scope: str = ""


class _ModelResponse(BaseModel):
    """The envelope. Its items are validated one by one, so one bad fact does not cost the others.

    `facts` is required: an answer that does not carry the key is an answer that ignored the
    schema, and reading it as "this note says nothing" would let a model that never answers
    correctly look like a model that found nothing.
    """

    model_config = ConfigDict(extra="ignore")

    facts: list[Any]


def _wire_schema() -> dict[str, Any]:
    """What Ollama is asked to constrain its answer to, generated from the model that validates a fact.

    One schema, so the two cannot drift. It is built here rather than taken from `_ModelResponse`
    because that one accepts anything in the list on purpose, while the server must still be told
    what a fact looks like. pydantic puts the enum it references in a `$defs` block, and a `$ref`
    resolves against the root of the document: the block travels to the root with it.
    """
    fact = _ModelFact.model_json_schema()
    return {
        "type": "object",
        "$defs": fact.pop("$defs", {}),
        "properties": {"facts": {"type": "array", "items": fact}},
        "required": ["facts"],
    }


_RESPONSE_SCHEMA: Final[dict[str, Any]] = _wire_schema()


def _validated(note: Note, answer: str) -> Reading:
    """The model's answer, turned into facts or counted as unusable."""
    try:
        response = _ModelResponse.model_validate_json(answer)
    except ValidationError as exc:
        logger.warning("note %s: the model's answer is not an extraction (%s)", note.note_id, _short(exc))
        return Reading(facts=(), invalid_outputs=1)

    facts: list[NoteFact] = []
    invalid = 0
    for item in response.facts:
        fact, rejected = _fact_of(note, item)
        invalid += rejected
        if fact is not None:
            facts.append(fact)
    return Reading(facts=tuple(facts), invalid_outputs=invalid)


def _fact_of(note: Note, item: Any) -> tuple[NoteFact | None, int]:
    """One item of the answer, and how much of it had to be thrown away.

    The two references are not worth the same. `component_ref` is what the fact is *about*: a
    reference the note does not contain means the model invented the subject, and the fact goes.
    `replacement_ref` is an extra the finding quotes — the observed failure is a model writing
    `none` into it — so it is dropped alone rather than costing a restriction that was right.
    Either way the count records it: nothing the model produced disappears unremarked.
    """
    try:
        extracted = _ModelFact.model_validate(item)
    except ValidationError as exc:
        logger.warning("note %s: a fact the model returned is not one (%s)", note.note_id, _short(exc))
        return None, 1
    if not extracted.component_ref:
        logger.warning("note %s: the model returned a fact about no component", note.note_id)
        return None, 1
    if extracted.component_ref not in note.text:
        logger.warning("note %s: the model cites %r, which the note does not contain", note.note_id, extracted.component_ref)
        return None, 1

    replacement, rejected = extracted.replacement_ref, 0
    if replacement and replacement not in note.text:
        logger.warning("note %s: the replacement %r is not in the note; the fact is kept without it", note.note_id, replacement)
        replacement, rejected = "", 1
    return (
        NoteFact(
            note_id=note.note_id,
            row_number=note.row_number,
            kind=extracted.kind,
            component_ref=extracted.component_ref,
            replacement_ref=replacement,
            scope=extracted.scope,
        ),
        rejected,
    )


def _slug(value: str) -> str:
    """A file name from a model id or a note id, which may hold a colon or a slash."""
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in value)


def _short(exc: ValidationError) -> str:
    """The first error pydantic found: the log line is a signal, the artifact carries the count."""
    errors = exc.errors()
    return f"{errors[0]['loc']}: {errors[0]['msg']}" if errors else str(exc)
