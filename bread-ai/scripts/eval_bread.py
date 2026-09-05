#!/usr/bin/env python
"""Score a model on coding ability and written English.

    python scripts/eval_bread.py --model-id Qwen/Qwen2.5-Coder-7B-Instruct --run-code
    python scripts/eval_bread.py --answers answers.json --run-code
    python scripts/eval_bread.py --model-id data/models/bread-coder-7b --adapter data/runs/x/adapter --run-code

Two halves, scored differently because they can be.

**Coding** is objective. The model is given a task, its code is extracted and run
against a test it never saw, and it either passes or it does not.

**English** is not objective, so the rubric scores what can be measured
honestly: whether the answer leads with the answer, avoids filler, keeps
sentences readable, includes code when asked, and declines to invent facts it
cannot know. It says nothing about whether the content is true, which is why the
runner prints the answers.

Running generated code
----------------------
``--run-code`` is required before any generated code executes, and without it
the coding half is skipped. Each snippet runs in a separate subprocess with a
timeout, in a temporary directory. That is isolation, not a sandbox: a hostile
payload still has your user's permissions. Evaluate models and task files you
trust.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from _bootstrap import REPO_ROOT, print_header, print_table
from app.services.quality.api_check import check_answer
from app.services.quality.coding_eval import evaluate_answers
from app.services.quality.prose_eval import evaluate_prose

CODING_TASKS = REPO_ROOT / "prompts" / "evals" / "coding_tasks.yaml"
ENGLISH_TASKS = REPO_ROOT / "prompts" / "evals" / "english_tasks.yaml"
FRAMEWORK_TASKS = REPO_ROOT / "prompts" / "evals" / "framework_tasks.yaml"
SYSTEM_PROMPT_PATH = REPO_ROOT / "prompts" / "system_default.md"


def load_tasks(path: Path) -> list[dict[str, Any]]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return list(payload.get("tasks", []))


def generate_answers(
    model_id: str,
    tasks: list[dict[str, Any]],
    *,
    adapter: str | None,
    max_new_tokens: int,
    temperature: float,
    load_in_4bit: bool,
    device: str,
) -> dict[str, str]:
    """Ask the model every task prompt and collect its answers."""

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model_kwargs: dict[str, Any] = {"device_map": device}
    if load_in_4bit:
        from transformers import BitsAndBytesConfig

        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
    else:
        model_kwargs["dtype"] = torch.float32 if device == "cpu" else torch.bfloat16

    model = AutoModelForCausalLM.from_pretrained(model_id, **model_kwargs)
    if adapter:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, adapter)
    model.eval()

    system_prompt = (
        SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
        if SYSTEM_PROMPT_PATH.exists()
        else "You are Bread, a local coding assistant."
    )

    answers: dict[str, str] = {}
    for index, task in enumerate(tasks, start=1):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": str(task["prompt"]).strip()},
        ]
        text = (
            tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            if getattr(tokenizer, "chat_template", None)
            else f"{system_prompt}\n\n{task['prompt']}\n\n"
        )
        encoded = tokenizer(text, return_tensors="pt").to(model.device)
        with torch.no_grad():
            generated = model.generate(
                **encoded,
                max_new_tokens=max_new_tokens,
                do_sample=temperature > 0,
                temperature=max(temperature, 1e-4),
                top_p=0.95,
                pad_token_id=tokenizer.pad_token_id,
            )
        answer = tokenizer.decode(
            generated[0][encoded["input_ids"].shape[1] :], skip_special_tokens=True
        )
        answers[str(task["id"])] = answer.strip()
        print(f"  [{index}/{len(tasks)}] {task['id']}", flush=True)

    return answers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--model-id", default=None, help="Model to evaluate.")
    parser.add_argument("--adapter", default=None, help="Optional LoRA adapter.")
    parser.add_argument(
        "--answers",
        default=None,
        help="Score a JSON file of {task_id: answer} instead of generating.",
    )
    parser.add_argument(
        "--run-code",
        action="store_true",
        help="Required to execute generated code. Without it the coding half is skipped.",
    )
    parser.add_argument("--max-new-tokens", type=int, default=600)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--no-4bit", dest="load_in_4bit", action="store_false", default=True)
    parser.add_argument("--save-answers", default=None, help="Write the answers to a file.")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--skip-english", action="store_true")
    parser.add_argument("--skip-coding", action="store_true")
    parser.add_argument(
        "--skip-frameworks",
        action="store_true",
        help="Leave out the tasks that drive a real library's handlers.",
    )
    args = parser.parse_args(argv)

    if not args.model_id and not args.answers:
        parser.error("give --model-id to generate, or --answers to score existing output")

    coding_tasks = [] if args.skip_coding else load_tasks(CODING_TASKS)
    if not args.skip_coding and not args.skip_frameworks:
        # Framework tasks are scored the same way, so they join the coding set.
        # What sets them apart is the test: it drives the answer's own handlers
        # rather than calling one function, which is the only way to see whether
        # a bot counts warnings per member or per server.
        coding_tasks += load_tasks(FRAMEWORK_TASKS)
    english_tasks = [] if args.skip_english else load_tasks(ENGLISH_TASKS)
    all_tasks = coding_tasks + english_tasks

    if args.answers:
        answers = json.loads(Path(args.answers).expanduser().read_text(encoding="utf-8"))
        source = str(args.answers)
    else:
        print_header(f"Generating answers with {args.model_id}")
        print_table(
            {
                "adapter": args.adapter or "(none)",
                "tasks": len(all_tasks),
                "max new tokens": args.max_new_tokens,
                "temperature": args.temperature,
            }
        )
        print()
        try:
            answers = generate_answers(
                args.model_id,
                all_tasks,
                adapter=args.adapter,
                max_new_tokens=args.max_new_tokens,
                temperature=args.temperature,
                load_in_4bit=args.load_in_4bit,
                device=args.device,
            )
        except ImportError as exc:
            print(f"error: {exc}. pip install -r requirements-inference.txt", file=sys.stderr)
            return 3
        source = args.model_id

    if args.save_answers:
        Path(args.save_answers).expanduser().write_text(
            json.dumps(answers, indent=2), encoding="utf-8"
        )

    report: dict[str, Any] = {"model": source}

    # ------------------------------------------------------------- coding
    if coding_tasks:
        if not args.run_code:
            print(
                "\n  Skipping the coding evaluation: it executes generated code and\n"
                "  needs --run-code. Read the note at the top of this script first.\n"
            )
            report["coding"] = {"skipped": "needs --run-code"}
        else:
            card = evaluate_answers(
                coding_tasks, answers, timeout=args.timeout, allow_execution=True
            )
            report["coding"] = card.as_dict()

            if not args.as_json:
                print_header("Coding: does the generated code actually run")
                summary = {
                    "passed": f"{card.passed} of {card.total}",
                    "pass rate": f"{card.pass_rate:.0%}",
                }
                if card.skipped:
                    summary["skipped"] = (
                        f"{len(card.skipped)} (library not installed, not counted either way)"
                    )
                print_table(summary)
                for difficulty, counts in sorted(card.by_difficulty().items()):
                    print(f"  {difficulty:<8} {counts['passed']}/{counts['total']}")
                if card.failures():
                    print("\n  Failures")
                    for failure in card.failures():
                        print(
                            f"    {failure.task_id:<22} {failure.reason:<10} {failure.detail[:70]}"
                        )

    # --------------------------------------------------- invented API check
    # Runs on every answer, whether or not the code was executed, because it
    # needs neither a test nor permission to run anything.
    api_findings: dict[str, list[dict[str, Any]]] = {}
    for task in coding_tasks:
        task_id = str(task["id"])
        answer = answers.get(task_id, "")
        if not answer.strip():
            continue
        api_report = check_answer(answer, allow_import=True)
        problems = [finding.as_dict() for finding in api_report.certain]
        if problems:
            api_findings[task_id] = problems

    if coding_tasks:
        api_summary = {
            "answers_with_invented_apis": len(api_findings),
            "answers_checked": sum(
                1 for task in coding_tasks if answers.get(str(task["id"]), "").strip()
            ),
            "findings": api_findings,
        }
        report["api_check"] = api_summary

        if not args.as_json:
            print_header("References: does every name and signature resolve")
            print_table(
                {
                    "answers checked": api_summary["answers_checked"],
                    "answers with a broken reference": len(api_findings),
                }
            )
            for task_id, problems in api_findings.items():
                for problem in problems[:3]:
                    print(f"    {task_id:<22} {problem['message'][:78]}")

    # ------------------------------------------------------------ english
    if english_tasks:
        prose_card = evaluate_prose(english_tasks, answers)
        report["english"] = prose_card.as_dict()

        if not args.as_json:
            print_header("English: is the writing well formed and honest")
            print_table(
                {
                    "passed": f"{prose_card.passed} of {prose_card.total}",
                    "mean score": f"{prose_card.mean_score:.2f}",
                }
            )
            if prose_card.failures():
                print("\n  Failures")
                for failure in prose_card.failures():
                    print(f"    {failure.task_id:<22} {'; '.join(failure.notes[:2])[:80]}")
                    print(f"      answer: {failure.answer_preview[:100]}")

    # ------------------------------------------------------------- verdict
    if args.as_json:
        print(json.dumps(report, indent=2))
        return 0

    coding = report.get("coding", {})
    english = report.get("english", {})
    overall_parts = []
    if isinstance(coding, dict) and "pass_rate" in coding:
        overall_parts.append(f"code {coding['pass_rate']:.0%}")
    if english:
        overall_parts.append(f"english {english['pass_rate']:.0%}")

    print_header("Scorecard")
    print_table({"model": source, "result": "  ".join(overall_parts) or "nothing scored"})
    print(
        "\n  The coding number is objective: the code ran or it did not.\n"
        "  The English number measures form, not truth. Read the answers."
    )

    if not args.save_answers:
        print("\n  Pass --save-answers answers.json to keep the raw output for reading.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
