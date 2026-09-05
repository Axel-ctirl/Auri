"""English scoring, code-task extraction and the two evaluators.

These are the pieces that decide what goes into training and how a model is
measured coming out. They need to be right, because a bad filter quietly
degrades every model built afterwards.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.services.datasets.code_tasks import (
    build_tasks,
    build_test_tasks,
    extract_generic_units,
    extract_python_units,
    extract_units,
    is_worth_training_on,
)
from app.services.datasets.records import RecordMeta
from app.services.quality.coding_eval import (
    evaluate_answers,
    extract_code,
    run_snippet,
)
from app.services.quality.english import (
    clean_docstring,
    looks_like_prose,
    score_prose,
)
from app.services.quality.prose_eval import evaluate_prose, prose_only

REPO_ROOT = Path(__file__).resolve().parents[2]

WELL_WRITTEN = (
    "Return the number of units to order so stock reaches the target level. "
    "Returns zero when current stock is already at or above the reorder point."
)

PYTHON_SOURCE = '''
"""Inventory helpers."""


def restock_quantity(current_stock: int, reorder_point: int, target: int) -> int:
    """Return how many units to order so stock reaches the target level.

    Returns zero when current stock is at or above the reorder point.

    Args:
        current_stock: units on hand
    """

    if current_stock >= reorder_point:
        return 0
    return max(target - current_stock, 0)


def undocumented(a, b):
    return a + b


def test_restock_quantity():
    """Check the reorder threshold is respected."""

    assert restock_quantity(2, 5, 20) == 18
    assert restock_quantity(9, 5, 20) == 0
'''


# --------------------------------------------------------------------- english
def test_good_prose_scores_well():
    score = score_prose(WELL_WRITTEN)
    assert score.is_good
    assert score.score > 0.9
    assert score.problems == []


def test_filler_is_penalised():
    score = score_prose(
        "Basically, it is important to note that this function will, in order to "
        "work correctly, essentially just compute the total."
    )
    assert not score.is_good
    assert "basically" in score.filler_hits
    assert any("filler" in problem for problem in score.problems)


def test_very_long_sentences_are_penalised():
    rambling = "This function " + "which does a thing and " * 20 + "returns a value."
    score = score_prose(rambling)
    assert not score.is_good
    assert any("average" in problem for problem in score.problems)


def test_heavy_passive_voice_is_penalised():
    score = score_prose(
        "The value is computed. The result is returned. The cache is updated. "
        "The error is logged."
    )
    assert score.passive_ratio > 0.5
    assert not score.is_good


def test_too_short_is_rejected():
    assert not score_prose("Adds two.").is_good


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Return the restock quantity. Zero when stock is sufficient enough.", True),
        (":param a: first\n:param b: second\n:return: sum\n:rtype: int", False),
        ("short", False),
        ("=====\n-----\n=====", False),
    ],
)
def test_prose_detection(text, expected):
    assert looks_like_prose(text) is expected


def test_clean_docstring_keeps_only_the_prose():
    cleaned = clean_docstring(
        "Return the mean of values.\n\n"
        "    Handles the empty case by raising.\n\n"
        "    Args:\n        values: the numbers\n    Returns:\n        the mean\n"
    )
    assert cleaned == "Return the mean of values.\n\nHandles the empty case by raising."
    assert "Args" not in cleaned


# ------------------------------------------------------------------ extraction
def test_python_extraction_finds_documented_functions():
    units = {unit.name: unit for unit in extract_python_units(PYTHON_SOURCE, "inv.py")}
    assert "restock_quantity" in units
    assert "undocumented" in units

    documented = units["restock_quantity"]
    assert documented.kind == "function"
    assert "Return how many units" in documented.docstring
    assert documented.signature.startswith("def restock_quantity(")
    assert "-> int" in documented.signature
    assert units["test_restock_quantity"].is_test is True


def test_undocumented_functions_are_rejected():
    units = {unit.name: unit for unit in extract_python_units(PYTHON_SOURCE)}
    accepted, reason = is_worth_training_on(units["undocumented"])
    assert not accepted
    assert reason == "no docstring"


def test_reference_only_docstrings_are_rejected():
    source = '''
def add(a, b):
    """:param a: first
    :param b: second
    :return: the sum
    :rtype: int
    """

    return a + b
'''
    unit = extract_python_units(source)[0]
    accepted, reason = is_worth_training_on(unit)
    assert not accepted
    assert "markup" in reason or "words" in reason


def test_tasks_do_not_restate_the_file():
    """The defect this module exists to fix.

    The old collector asked the model to repeat a file back, which trains
    copying. Every task here must differ from its answer.
    """

    unit = next(
        unit for unit in extract_python_units(PYTHON_SOURCE) if unit.name == "restock_quantity"
    )
    meta = RecordMeta(source="local_code", license="MIT", language="python")
    records = build_tasks(unit, meta)

    assert len(records) == 3
    kinds = {record["meta"]["source"].split("/")[-1] for record in records}
    assert kinds == {"implement", "explain", "document"}

    for record in records:
        user = record["messages"][1]["content"]
        assistant = record["messages"][2]["content"]
        assert user.strip() != assistant.strip()
        assert assistant.strip()


def test_implement_task_asks_for_code_and_answers_with_code():
    unit = next(
        unit for unit in extract_python_units(PYTHON_SOURCE) if unit.name == "restock_quantity"
    )
    records = build_tasks(unit, RecordMeta(source="local_code"), kinds=("implement",))
    user = records[0]["messages"][1]["content"]
    assistant = records[0]["messages"][2]["content"]

    assert "def restock_quantity(" in user  # the signature is given
    assert "Return how many units" in user  # the description is given
    assert "return max(target - current_stock, 0)" in assistant  # the body is not
    assert "return max(target - current_stock, 0)" not in user


def test_explain_task_answers_with_english_not_code():
    unit = next(
        unit for unit in extract_python_units(PYTHON_SOURCE) if unit.name == "restock_quantity"
    )
    records = build_tasks(unit, RecordMeta(source="local_code"), kinds=("explain",))
    assistant = records[0]["messages"][2]["content"]

    assert "```" not in assistant
    assert score_prose(assistant).is_good


def test_test_tasks_pair_a_function_with_its_test():
    units = extract_python_units(PYTHON_SOURCE)
    records = build_test_tasks(units, RecordMeta(source="local_code"))

    assert len(records) == 1
    user = records[0]["messages"][1]["content"]
    assistant = records[0]["messages"][2]["content"]
    assert "Write a unit test" in user
    assert "def restock_quantity" in user
    assert "def test_restock_quantity" in assistant


def test_javascript_doc_comments_are_extracted():
    source = """
/**
 * Return how many units to order so stock reaches the target level.
 * Returns zero when current stock is at or above the reorder point.
 */
function restockQuantity(currentStock, reorderPoint, target) {
  if (currentStock >= reorderPoint) {
    return 0;
  }
  return Math.max(target - currentStock, 0);
}
"""
    units = extract_generic_units(source, "javascript", "inv.js")
    assert len(units) == 1
    assert units[0].name == "restockQuantity"
    assert "Math.max" in units[0].source
    assert is_worth_training_on(units[0])[0]


def test_extract_units_dispatches_by_language():
    assert extract_units(PYTHON_SOURCE, "python")
    assert extract_units("int main() { return 0; }", "brainfuck") == []


# --------------------------------------------------------------- coding eval
def test_extract_code_handles_prose_and_fences():
    assert "def a" in extract_code("Here you go:\n\n```python\ndef a():\n    pass\n```\n")
    assert extract_code("def a():\n    pass").startswith("def a")
    assert extract_code("I cannot help with that.") == ""


def test_extract_code_joins_multiple_blocks():
    code = extract_code("```python\ndef a(): pass\n```\nand\n```python\ndef b(): pass\n```")
    assert "def a" in code and "def b" in code


def test_execution_is_refused_without_explicit_permission():
    with pytest.raises(PermissionError, match="allow_execution"):
        run_snippet("x = 1", "assert x == 1")


def test_a_correct_snippet_passes_and_a_wrong_one_fails():
    passed, _reason, _detail = run_snippet(
        "def add(a, b):\n    return a + b", "assert add(2, 3) == 5", allow_execution=True
    )
    assert passed

    failed, reason, detail = run_snippet(
        "def add(a, b):\n    return a - b", "assert add(2, 3) == 5", allow_execution=True
    )
    assert not failed
    assert reason == "assertion"
    assert "AssertionError" in detail or "assert" in detail.lower()


def test_broken_syntax_is_reported_as_syntax():
    passed, reason, _detail = run_snippet(
        "def add(a, b)\n    return a + b", "assert True", allow_execution=True
    )
    assert not passed
    assert reason == "syntax"


def test_an_endless_loop_is_stopped_by_the_timeout():
    passed, reason, _detail = run_snippet(
        "while True:\n    pass", "assert True", timeout=2, allow_execution=True
    )
    assert not passed
    assert reason == "timeout"


def test_every_shipped_coding_task_is_solvable():
    """Each task must pass with a correct solution, or the benchmark is broken."""

    tasks = yaml.safe_load(
        (REPO_ROOT / "prompts" / "evals" / "coding_tasks.yaml").read_text(encoding="utf-8")
    )["tasks"]
    assert len(tasks) >= 10

    solutions = {
        "restock_quantity": "def restock_quantity(c, r, t):\n    return 0 if c >= r else max(t - c, 0)",
        "safe_average": (
            "def safe_average(v):\n"
            "    if not v:\n        raise ValueError('need values')\n"
            "    return sum(v) / len(v)"
        ),
        "chunk_list": (
            "def chunk_list(items, size):\n"
            "    if size < 1:\n        raise ValueError('size')\n"
            "    return [items[i:i+size] for i in range(0, len(items), size)]"
        ),
        "parse_duration": (
            "import re\n"
            "def parse_duration(t):\n"
            "    if not t or not re.fullmatch(r'(\\d+[hms])+', t):\n"
            "        raise ValueError(t)\n"
            "    f = {'h': 3600, 'm': 60, 's': 1}\n"
            "    return sum(int(n) * f[u] for n, u in re.findall(r'(\\d+)([hms])', t))"
        ),
        "merge_intervals": (
            "def merge_intervals(iv):\n"
            "    out = []\n"
            "    for s, e in sorted(iv):\n"
            "        if out and s <= out[-1][1]:\n"
            "            out[-1] = (out[-1][0], max(out[-1][1], e))\n"
            "        else:\n            out.append((s, e))\n"
            "    return out"
        ),
        "word_frequency": (
            "import re\nfrom collections import Counter\n"
            "def word_frequency(text, limit):\n"
            '    c = Counter(re.findall(r"[a-z0-9\']+", text.lower()))\n'
            "    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]"
        ),
        "retry_with_backoff": (
            "def retry(operation, attempts, on_error=None):\n"
            "    last = None\n"
            "    for _ in range(attempts):\n"
            "        try:\n            return operation()\n"
            "        except Exception as e:\n            last = e\n"
            "    raise last"
        ),
        "flatten_nested": (
            "def flatten(n):\n    out = []\n"
            "    for i in n:\n"
            "        out.extend(flatten(i)) if isinstance(i, list) else out.append(i)\n"
            "    return out"
        ),
        "sanitize_filename": (
            "import re\n"
            "def sanitize_filename(name):\n"
            "    b = (name or '').replace('\\\\', '/').split('/')[-1]\n"
            "    c = re.sub(r'[^A-Za-z0-9._-]', '_', b).strip('._')\n"
            "    return c or 'unnamed'"
        ),
        "lru_cache_class": (
            "from collections import OrderedDict\n"
            "class LRUCache:\n"
            "    def __init__(self, capacity):\n"
            "        self.capacity = capacity\n        self._d = OrderedDict()\n"
            "    def get(self, key):\n"
            "        if key not in self._d:\n            return None\n"
            "        self._d.move_to_end(key)\n        return self._d[key]\n"
            "    def put(self, key, value):\n"
            "        if key in self._d:\n            self._d.move_to_end(key)\n"
            "        self._d[key] = value\n"
            "        if len(self._d) > self.capacity:\n"
            "            self._d.popitem(last=False)"
        ),
        "group_by_key": (
            "def group_by(rows, key):\n    g = {}\n"
            "    for r in rows:\n"
            "        if key in r:\n            g.setdefault(r[key], []).append(r)\n"
            "    return g"
        ),
        "fix_the_bug": (
            "def second_largest(values):\n"
            "    d = sorted(set(values))\n"
            "    return d[-2] if len(d) >= 2 else None"
        ),
    }

    answers = {task_id: f"```python\n{code}\n```" for task_id, code in solutions.items()}
    missing = {str(task["id"]) for task in tasks} - set(answers)
    assert not missing, f"no reference solution for {missing}"

    card = evaluate_answers(tasks, answers, allow_execution=True)
    assert card.pass_rate == 1.0, [f.as_dict() for f in card.failures()]


def test_a_missing_answer_scores_as_no_code():
    tasks = [{"id": "x", "test": "assert True", "difficulty": "easy"}]
    card = evaluate_answers(tasks, {}, allow_execution=True)
    assert card.pass_rate == 0.0
    assert card.results[0].reason == "no_code"
    assert card.results[0].had_code is False


# ---------------------------------------------------------------- prose eval
def test_prose_only_strips_code():
    assert "def" not in prose_only("Here:\n```python\ndef a(): pass\n```\nThat is it.")


def test_the_rubric_separates_honest_from_overclaiming_answers():
    tasks = yaml.safe_load(
        (REPO_ROOT / "prompts" / "evals" / "english_tasks.yaml").read_text(encoding="utf-8")
    )["tasks"]
    subset = [task for task in tasks if task["id"] in {"admit_uncertainty", "no_invented_version"}]

    honest = {
        "admit_uncertainty": "I do not believe FastAPI has an option by that name, and "
        "I would rather say so than invent one.",
        "no_invented_version": "I cannot tell you reliably; my knowledge has a cutoff. "
        "Run `npm view react version` for the current one.",
    }
    overclaiming = {
        "admit_uncertainty": "The `parallel_dispatch` option enables concurrent handling.",
        "no_invented_version": "The latest version is 19.2.1, released recently.",
    }

    assert evaluate_prose(subset, honest).passed == 2
    assert evaluate_prose(subset, overclaiming).passed == 0


def test_an_empty_answer_fails_cleanly():
    card = evaluate_prose([{"id": "x", "require_prose": True}], {"x": ""})
    assert card.passed == 0
    assert card.results[0].notes == ["empty answer"]


def test_every_english_task_has_something_to_check():
    tasks = yaml.safe_load(
        (REPO_ROOT / "prompts" / "evals" / "english_tasks.yaml").read_text(encoding="utf-8")
    )["tasks"]
    for task in tasks:
        assert task.get("prompt", "").strip()
        assert any(
            key in task
            for key in ("require_prose", "require_any", "require_code", "forbid", "max_words")
        ), f"{task['id']} checks nothing"


# ------------------------------------------------------------- api checking
def test_an_undefined_name_is_caught():
    from app.services.quality.api_check import check_code

    report = check_code("import datetime\nx = discord.timedelta(minutes=5)\n")
    assert not report.ok
    assert report.certain[0].kind == "undefined"
    assert report.certain[0].symbol == "discord"


def test_names_bound_in_every_ordinary_way_are_not_flagged():
    """The false-positive guard. A checker that cries wolf gets switched off."""

    from app.services.quality.api_check import check_code

    code = """
import os
from pathlib import Path as P

TOTAL = 1

def outer(argument, *rest, keyword=None, **extra):
    local = argument + TOTAL
    for item in rest:
        local += item
    try:
        pass
    except ValueError as error:
        print(error)
    return [x for x in range(local)], P, os, keyword, extra

class Thing:
    def method(self):
        return self

print(outer, Thing, __name__)
"""
    assert check_code(code).ok, [f.message for f in check_code(code).findings]


def test_a_missing_module_attribute_is_caught():
    from app.services.quality.api_check import check_code

    report = check_code(
        "import itertools\nresult = itertools.batched_chunks([1], 2)\n", allow_import=True
    )
    assert not report.ok
    assert any("batched_chunks" in finding.message for finding in report.certain)


def test_a_real_module_attribute_is_not_flagged():
    from app.services.quality.api_check import check_code

    report = check_code(
        "import itertools\nresult = list(itertools.chain([1], [2]))\n", allow_import=True
    )
    assert report.ok, [f.message for f in report.findings]


def test_a_bad_keyword_argument_is_caught():
    from app.services.quality.api_check import check_code

    report = check_code("import os\nos.makedirs('/tmp/x', exist_okay=True)\n", allow_import=True)
    assert any(finding.kind == "keyword" for finding in report.certain)
    assert any("exist_okay" in finding.message for finding in report.certain)


def test_a_function_taking_kwargs_is_left_alone():
    """`json.dumps(**kw)` accepts anything, so no keyword can be proven wrong."""

    from app.services.quality.api_check import check_code

    report = check_code("import json\njson.dumps({}, indentation=2)\n", allow_import=True)
    assert report.ok


def test_a_keyword_only_method_called_positionally_is_caught():
    """The disnake defect: `member.timeout(end_time)` on a keyword-only method."""

    disnake = pytest.importorskip("disnake")

    from app.services.quality.api_check import check_code

    code = (
        "import disnake\n"
        "async def go(member: disnake.Member):\n"
        "    await member.timeout(600)\n"
    )
    report = check_code(code, allow_import=True)
    assert any("positional" in finding.message for finding in report.certain)
    assert disnake is not None


def test_the_same_method_called_correctly_is_not_flagged():
    pytest.importorskip("disnake")

    from app.services.quality.api_check import check_code

    code = (
        "import disnake\n"
        "async def go(member: disnake.Member):\n"
        "    await member.timeout(duration=600, reason='spam')\n"
    )
    assert check_code(code, allow_import=True).ok


def test_an_unprovable_attribute_is_reported_as_a_suspicion_not_a_fact():
    """Confidence levels exist so a suspicion never reads as a certainty."""

    pytest.importorskip("disnake")

    from app.services.quality.api_check import check_code

    code = (
        "import disnake\n"
        "async def go(inter: disnake.ApplicationCommandInteraction):\n"
        "    return inter.message\n"
    )
    report = check_code(code, allow_import=True)
    assert report.ok  # suspicions do not fail the check
    assert report.likely
    assert report.likely[0].confidence == "likely"
    assert "may be set at runtime" in report.likely[0].message


def test_syntax_errors_are_reported_rather_than_raised():
    from app.services.quality.api_check import check_code

    report = check_code("def broken(\n")
    assert not report.ok
    assert report.syntax_error and "line" in report.syntax_error


def test_nothing_is_imported_unless_asked():
    from app.services.quality.api_check import check_code

    report = check_code("import itertools\nitertools.nope()\n", allow_import=False)
    assert report.modules_checked == []
    assert report.ok  # the syntactic pass alone finds nothing wrong here


def test_an_uninstalled_module_is_noted_not_blamed():
    from app.services.quality.api_check import check_code

    report = check_code(
        "import definitely_not_installed_xyz\ndefinitely_not_installed_xyz.go()\n",
        allow_import=True,
    )
    assert "definitely_not_installed_xyz" in report.modules_unavailable
    assert report.ok  # absence of the library is not evidence against the code


def test_check_answer_pulls_code_out_of_prose():
    from app.services.quality.api_check import check_answer

    report = check_answer("Here you go:\n\n```python\nx = undefined_thing\n```\n")
    assert any(finding.symbol == "undefined_thing" for finding in report.certain)

    empty = check_answer("I cannot help with that.")
    assert empty.syntax_error == "no code block in the answer"


def test_a_name_annotated_two_ways_is_not_guessed_at():
    """The false positive found by pointing the checker at its own source.

    A visitor class annotates the same parameter name as a different type in
    every method. Resolving it to whichever came last invented a dozen problems
    that did not exist.
    """

    from app.services.quality.api_check import check_code

    code = """
import ast

class Visitor:
    def visit_Call(self, node: ast.Call):
        return node.func

    def visit_Name(self, node: ast.Name):
        return node.id
"""
    report = check_code(code, allow_import=True)
    assert report.ok
    assert report.findings == []


def test_fields_declared_but_set_on_instances_are_not_flagged():
    """AST nodes, dataclasses and pydantic models set attributes on instances."""

    from app.services.quality.api_check import check_code

    code = "import ast\ndef go(call: ast.Call):\n    return call.func, call.args, call.keywords\n"
    assert check_code(code, allow_import=True).ok


def test_relative_imports_are_not_treated_as_top_level_modules():
    from app.services.quality.api_check import check_code

    report = check_code("from .sibling import helper\nresult = helper()\n", allow_import=True)
    assert report.modules_unavailable == []
    assert report.ok


def test_the_checker_is_clean_on_its_own_source():
    """A checker that flags known-good code gets switched off and stops helping."""

    from app.services.quality.api_check import check_code

    source = (REPO_ROOT / "backend" / "app" / "services" / "quality" / "api_check.py").read_text(
        encoding="utf-8"
    )
    report = check_code(source, allow_import=True)
    assert report.ok, [f.message for f in report.certain]
    assert not report.likely, [f.message for f in report.likely]


def test_lambda_parameters_are_bound():
    """A lambda's parameter is defined inside it, the same as a def's."""

    from app.services.quality.api_check import check_code

    report = check_code("pairs = [(1, 2)]\nordered = sorted(pairs, key=lambda pair: pair[1])\n")
    assert report.ok, [f.message for f in report.certain]


def test_names_bound_by_a_match_statement_are_not_flagged():
    from app.services.quality.api_check import check_code

    source = """
def describe(value):
    match value:
        case [first, *rest]:
            return first, rest
        case {"kind": kind, **extra}:
            return kind, extra
        case ValueError() as error:
            return error
    return None
"""
    report = check_code(source)
    assert report.ok, [f.message for f in report.certain]


def test_the_checker_is_clean_on_the_whole_backend():
    """Every module Bread ships passes its own check, so a finding means something."""

    from app.services.quality.api_check import check_code

    problems: list[str] = []
    for path in sorted((REPO_ROOT / "backend" / "app").rglob("*.py")):
        report = check_code(path.read_text(encoding="utf-8"), allow_import=True)
        problems.extend(
            f"{path.name}:{finding.line} {finding.message}" for finding in report.certain
        )
    assert problems == []


def test_an_unused_import_is_reported_as_a_suspicion():
    """A leftover import is a hint that more was copied over than was meant to be."""

    from app.services.quality.api_check import check_code

    report = check_code("import os\nimport random\n\nprint(os.getcwd())\n")
    assert [finding.symbol for finding in report.likely] == ["random"]
    # A suspicion, so it never fails the check on its own.
    assert report.ok


def test_a_from_import_nobody_uses_is_reported():
    from app.services.quality.api_check import check_code

    report = check_code("from collections import defaultdict, deque\n\nqueue = deque()\n")
    assert [finding.symbol for finding in report.likely] == ["collections.defaultdict"]


def test_a_future_import_is_never_unused():
    from app.services.quality.api_check import check_code

    report = check_code("from __future__ import annotations\n\nvalue: int = 1\n")
    assert report.likely == []


def test_a_module_with_dunder_all_is_a_re_export_surface():
    from app.services.quality.api_check import check_code

    report = check_code('__all__ = ["deque"]\nfrom collections import deque\n')
    assert report.likely == []


def test_an_import_used_only_as_an_annotation_is_not_flagged():
    from app.services.quality.api_check import check_code

    report = check_code(
        "import decimal\n\n\ndef total(value: decimal.Decimal) -> None:\n    pass\n"
    )
    assert report.likely == []
