"""The LLM adapter, driven by a fake backend. No test here calls a model or the network.

`OllamaBackend` is exercised on its transport only — a local HTTP server that answers what the
test tells it to — because what has to be proven about it is the timeout, the retry and the one
POST, not what a 12B model says. What the *adapter* does with an answer is proven against
`FakeBackend`, whose canned outputs include the ones a real model produced during spike S2.
"""

import json
import logging
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import pytest

from bomreuse.model import FactKind, Note, RawDate
from bomreuse.notes import DEFAULT_MODEL, BackendError, ModelReader, OllamaBackend, extract


def a_note(text: str = "Le joint BGI-2031 est remplacé par BGI-2045.", note_id: str = "N001", row_number: int = 1) -> Note:
    return Note(note_id=note_id, row_number=row_number, variant_id="A", date=RawDate(raw="2024-03-01", normalized=date(2024, 3, 1)), text=text)


class FakeBackend:
    """Canned answers, in order, and the prompts it was given."""

    def __init__(self, *answers: str, model: str = "fake-model") -> None:
        self.model = model
        self._answers = list(answers)
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._answers.pop(0) if self._answers else '{"facts": []}'


def answer(*facts: dict[str, Any]) -> str:
    return json.dumps({"facts": list(facts)})


def reader(*answers: str) -> tuple[ModelReader, FakeBackend]:
    backend = FakeBackend(*answers)
    return ModelReader(backend, cache=None), backend


# --- a valid answer ------------------------------------------------------------------------------


def test_a_valid_answer_becomes_facts_citing_the_note() -> None:
    model, _ = reader(answer({"kind": "replacement", "component_ref": "BGI-2031", "replacement_ref": "BGI-2045"}))
    reading = model.read(a_note(note_id="N027", row_number=27))
    assert reading.invalid_outputs == 0
    assert len(reading.facts) == 1
    fact = reading.facts[0]
    assert (fact.note_id, fact.row_number, fact.kind) == ("N027", 27, FactKind.REPLACEMENT)
    assert (fact.component_ref, fact.replacement_ref) == ("BGI-2031", "BGI-2045")


def test_the_reader_names_the_model_it_ran_on() -> None:
    """A finding read off the artifact must say which reader produced the fact behind it."""
    model, _ = reader()
    assert model.name == "llm:fake-model"
    assert ModelReader(FakeBackend(model=DEFAULT_MODEL), cache=None).name == f"llm:{DEFAULT_MODEL}"


def test_the_note_is_the_only_thing_the_prompt_carries() -> None:
    model, backend = reader()
    model.read(a_note("Ne pas utiliser SEAT-RAIL-1 sur les rames 4 caisses.", note_id="N003"))
    assert backend.prompts[0].endswith("Ne pas utiliser SEAT-RAIL-1 sur les rames 4 caisses.\n")
    assert "N003" not in backend.prompts[0], "the note id is the cache key, not something the model is asked about"


def test_one_call_per_note() -> None:
    model, backend = reader()
    extract([a_note(note_id="N001"), a_note(note_id="N002"), a_note(note_id="N003")], model)
    assert len(backend.prompts) == 3


def test_an_answer_asserting_nothing_is_not_an_invalid_answer() -> None:
    model, _ = reader('{"facts": []}')
    assert model.read(a_note()).facts == ()
    assert model.read(a_note()).invalid_outputs == 0


# --- an invalid answer is logged and counted, never dropped ---------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "not json at all",
        "",
        '{"facts": "BGI-2031"}',
        '{"result": []}',
        "[]",
        '{"facts": [{"kind": "replacement", "component_ref": "BGI-2031"}',
    ],
)
def test_an_answer_that_is_not_an_extraction_is_counted(bad: str, caplog: pytest.LogCaptureFixture) -> None:
    model, _ = reader(bad)
    with caplog.at_level(logging.WARNING, logger="bomreuse.notes"):
        reading = model.read(a_note())
    assert (reading.facts, reading.invalid_outputs) == ((), 1)
    assert caplog.records, "an answer thrown away without a log line is an answer dropped in silence"


@pytest.mark.parametrize(
    "bad_fact",
    [
        {"kind": "rumour", "component_ref": "BGI-2031"},
        {"kind": "replacement"},
        {"component_ref": "BGI-2031"},
        {"kind": "replacement", "component_ref": ""},
        {"kind": "replacement", "component_ref": 2031},
    ],
)
def test_a_fact_that_is_not_one_is_counted_and_the_others_survive(bad_fact: dict[str, Any], caplog: pytest.LogCaptureFixture) -> None:
    """One bad item must not cost the good ones: that is why the envelope is validated item by item."""
    good = {"kind": "obsolescence", "component_ref": "BGI-2045"}
    model, _ = reader(answer(bad_fact, good))
    with caplog.at_level(logging.WARNING, logger="bomreuse.notes"):
        reading = model.read(a_note("BGI-2031 remplacé par BGI-2045, qui est obsolete since 2025."))
    assert [fact.component_ref for fact in reading.facts] == ["BGI-2045"]
    assert reading.invalid_outputs == 1
    assert caplog.records


def test_a_fact_about_a_part_the_note_never_names_is_refused() -> None:
    """The one check a program can make on free text: the evidence must be in the note."""
    model, _ = reader(answer({"kind": "obsolescence", "component_ref": "BGI-9999"}))
    reading = model.read(a_note("Le joint BGI-2031 est remplacé par BGI-2045."))
    assert (reading.facts, reading.invalid_outputs) == ((), 1)


def test_a_reference_the_model_tidied_up_is_refused_like_an_invented_one() -> None:
    """`Bgi-2031` is the spelling the finding will be checked against; `BGI-2031` is a different string."""
    model, _ = reader(answer({"kind": "obsolescence", "component_ref": "BGI-2031"}))
    reading = model.read(a_note("Le joint Bgi-2031 est en fin de vie."))
    assert (reading.facts, reading.invalid_outputs) == ((), 1)


def test_an_invented_replacement_is_dropped_alone_and_the_fact_is_kept() -> None:
    """Observed in spike S2: the model writes `none` into the field rather than leaving it out."""
    model, _ = reader(answer({"kind": "restriction", "component_ref": "BRK-CTRL-VALVE", "replacement_ref": "none", "scope": "4-car"}))
    reading = model.read(a_note("Do not use BRK-CTRL-VALVE on 4-car trainsets."))
    assert len(reading.facts) == 1
    assert reading.facts[0].replacement_ref == ""
    assert reading.invalid_outputs == 1, "kept, but counted: nothing the model produced disappears unremarked"


def test_a_field_the_adapter_does_not_know_does_not_cost_the_fact() -> None:
    model, _ = reader(answer({"kind": "obsolescence", "component_ref": "BGI-2031", "certainty": "high"}))
    reading = model.read(a_note("BGI-2031 is obsolete."))
    assert len(reading.facts) == 1 and reading.invalid_outputs == 0


# --- the cache -------------------------------------------------------------------------------------


def test_an_answer_is_cached_per_model_prompt_and_note(tmp_path: Path) -> None:
    backend = FakeBackend(answer({"kind": "obsolescence", "component_ref": "BGI-2031"}))
    model = ModelReader(backend, cache=tmp_path)
    note = a_note("BGI-2031 is obsolete since 2023.", note_id="N042")

    first = model.read(note)
    second = model.read(note)

    assert first == second
    assert len(backend.prompts) == 1, "the second read came from the cache"
    entry = next(iter(tmp_path.iterdir()))
    assert entry.name.startswith("fake-model-N042-")


def test_another_model_does_not_read_the_first_one_s_cache(tmp_path: Path) -> None:
    note = a_note("BGI-2031 is obsolete since 2023.")
    ModelReader(FakeBackend(answer({"kind": "obsolescence", "component_ref": "BGI-2031"}), model="one"), cache=tmp_path).read(note)
    other = FakeBackend(answer({"kind": "restriction", "component_ref": "BGI-2031"}), model="two")
    assert ModelReader(other, cache=tmp_path).read(note).facts[0].kind is FactKind.RESTRICTION
    assert len(other.prompts) == 1


def test_a_cache_that_cannot_be_written_does_not_stop_the_run(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """It is an accelerator, not a deliverable: the model stays the source of truth."""
    blocked = tmp_path / "file"
    blocked.write_text("not a directory", encoding="utf-8")
    model = ModelReader(FakeBackend(answer({"kind": "obsolescence", "component_ref": "BGI-2031"})), cache=blocked / "cache")
    with caplog.at_level(logging.WARNING, logger="bomreuse.notes"):
        assert len(model.read(a_note("BGI-2031 is obsolete.")).facts) == 1
    assert caplog.records


def test_a_model_id_with_a_colon_becomes_a_file_name(tmp_path: Path) -> None:
    ModelReader(FakeBackend(model="gemma4:12b-mlx"), cache=tmp_path).read(a_note())
    assert next(iter(tmp_path.iterdir())).name.startswith("gemma4_12b-mlx-N001-")


# --- the transport, against a local server that is not a model --------------------------------------


class _Handler(BaseHTTPRequestHandler):
    replies: list[tuple[int, str]] = []
    seen: list[dict[str, Any]] = []

    def do_POST(self) -> None:  # noqa: N802 — the name http.server dispatches on
        self.seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        status, body = self.replies.pop(0) if self.replies else (200, json.dumps({"response": '{"facts": []}'}))
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *args: Any) -> None:
        """Quiet: the test's output is its assertions."""


@pytest.fixture
def server() -> Any:
    _Handler.replies, _Handler.seen = [], []
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd
    httpd.shutdown()


def endpoint(httpd: HTTPServer) -> str:
    return f"http://127.0.0.1:{httpd.server_address[1]}/api/generate"


def test_the_backend_posts_the_prompt_the_model_and_the_schema(server: HTTPServer) -> None:
    OllamaBackend(model="test-model", endpoint=endpoint(server)).generate("read this note")
    sent = _Handler.seen[0]
    assert (sent["model"], sent["prompt"], sent["stream"]) == ("test-model", "read this note", False)
    assert sent["format"]["properties"]["facts"]["items"]["required"] == ["kind", "component_ref"]
    assert sent["options"]["temperature"] == 0, "two runs of a demo should say the same thing"


def test_the_backend_retries_once_and_then_gives_up(server: HTTPServer) -> None:
    _Handler.replies = [(500, "overloaded"), (200, json.dumps({"response": '{"facts": []}'}))]
    assert OllamaBackend(endpoint=endpoint(server)).generate("x") == '{"facts": []}'
    assert len(_Handler.seen) == 2

    _Handler.replies = [(500, "overloaded"), (500, "overloaded")]
    with pytest.raises(BackendError, match="did not answer"):
        OllamaBackend(endpoint=endpoint(server)).generate("x")


def test_an_answer_that_is_not_an_ollama_answer_is_a_backend_error(server: HTTPServer) -> None:
    _Handler.replies = [(200, "{}"), (200, "{}")]
    with pytest.raises(BackendError):
        OllamaBackend(endpoint=endpoint(server)).generate("x")


def test_a_backend_nobody_is_listening_to_is_a_backend_error() -> None:
    """The offline case, from the other side: `bomreuse run` defaults to the fallback for this reason."""
    with pytest.raises(BackendError, match="did not answer"):
        OllamaBackend(endpoint="http://127.0.0.1:1/api/generate", timeout=1.0).generate("x")
