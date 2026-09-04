"""The generate-check-repair loop, and the memory notes it produces."""

from __future__ import annotations

from app.services.inference.base import ChatTurn, GenerationParams, InferenceBackend, StopSignal
from app.services.quality import repair


class ScriptedBackend(InferenceBackend):
    """A backend that reads its answers off a list, so the loop is deterministic."""

    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)
        self.prompts: list[list[ChatTurn]] = []

    def generate(self, turns, params, stop_signal=None):  # type: ignore[override]
        self.prompts.append(list(turns))
        return self.answers[min(len(self.prompts) - 1, len(self.answers) - 1)]

    def stream(self, turns, params, stop_signal=None):  # type: ignore[override]
        yield self.generate(turns, params, stop_signal)

    def count_tokens(self, text: str) -> int:
        return max(len(text) // 4, 1)

    def status(self):  # type: ignore[override]
        raise NotImplementedError

    def load(self, **kwargs):  # type: ignore[override]
        raise NotImplementedError

    def unload(self) -> None:
        return None


BROKEN = """Here you go.

```python
import itertools

def chunk(items):
    return itertools.batched_chunks(items, 3)
```
"""

FIXED = """Corrected.

```python
import itertools

def chunk(items):
    iterator = iter(items)
    return iter(lambda: list(itertools.islice(iterator, 3)), [])
```
"""

WORSE = """Corrected.

```python
import itertools

def chunk(items):
    return itertools.batched_chunks(nope(items), 3)
```
"""


def _params() -> GenerationParams:
    return GenerationParams(temperature=0.2, top_p=0.9, max_new_tokens=256)


def _turns() -> list[ChatTurn]:
    return [ChatTurn(role="user", content="Chunk a list into threes.")]


def test_a_clean_answer_costs_one_generation():
    backend = ScriptedBackend([FIXED])
    result = repair.generate_verified(backend, _turns(), _params())
    assert len(backend.prompts) == 1
    assert result.repaired is False
    assert result.problems_remaining == 0


def test_a_broken_answer_is_repaired():
    backend = ScriptedBackend([BROKEN, FIXED])
    result = repair.generate_verified(backend, _turns(), _params())
    assert len(backend.prompts) == 2
    assert result.repaired is True
    assert result.problems_remaining == 0
    assert "itertools.islice(" in result.answer


def test_the_model_is_shown_the_problem_it_has_to_fix():
    backend = ScriptedBackend([BROKEN, FIXED])
    repair.generate_verified(backend, _turns(), _params())
    followup = backend.prompts[1][-1].content
    assert "batched_chunks" in followup
    assert "will not run" in followup


def test_a_repair_that_makes_things_worse_is_discarded():
    backend = ScriptedBackend([BROKEN, WORSE])
    result = repair.generate_verified(backend, _turns(), _params())
    # The first attempt had one problem, the second has two. Keep the first.
    assert result.answer == BROKEN
    assert result.repaired is False


def test_the_loop_gives_up_after_the_attempt_budget():
    backend = ScriptedBackend([BROKEN])
    result = repair.generate_verified(backend, _turns(), _params(), max_attempts=2)
    assert len(backend.prompts) == 2
    assert result.problems_remaining == 1


def test_prose_without_code_is_not_a_code_problem():
    backend = ScriptedBackend(["A linear equation has degree one in every variable."])
    result = repair.generate_verified(backend, _turns(), _params())
    assert len(backend.prompts) == 1
    assert result.problems_remaining == 0


def test_a_stop_signal_ends_the_loop():
    backend = ScriptedBackend([BROKEN, FIXED])
    signal = StopSignal()
    signal.stop()
    result = repair.generate_verified(backend, _turns(), _params(), stop_signal=signal)
    assert backend.prompts == []
    assert result.answer == ""


def test_a_fixed_mistake_becomes_something_to_remember():
    backend = ScriptedBackend([BROKEN, FIXED])
    result = repair.generate_verified(backend, _turns(), _params())
    notes = repair.memory_notes(result)
    assert notes
    assert "batched_chunks" in notes[0]


def test_the_summary_reports_what_happened():
    backend = ScriptedBackend([BROKEN, FIXED])
    summary = repair.generate_verified(backend, _turns(), _params()).as_dict()
    assert summary["repaired"] is True
    assert summary["problems_at_first_attempt"] == 1
    assert summary["problems_remaining"] == 0
    assert len(summary["attempts"]) == 2
