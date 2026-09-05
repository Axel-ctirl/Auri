# Making Bread write and code well

Two things decide how good a fine-tuned Bread is: what goes into the training
data, and whether you measure what comes out. This page covers both.

## The defect this replaced

The first version of Bread's collector built training pairs like this:

```
user:      Here is inventory.py. Explain what it does, then restate the file.
assistant: inventory.py is a python file. <the entire file, verbatim>
```

Training on thousands of those teaches one skill: copying the input. A model
fine-tuned on it answers every question by reproducing whatever you showed it,
and it is worse than no fine-tune at all. That is now fixed, and a test guards
against it returning.

## Where good training pairs actually come from

Good code already contains the pairing you need. A docstring is a human's
English description of what a function does, sitting next to the function that
does it. One documented function yields three real tasks, and a project's tests
yield a fourth:

| Task | Prompt | Answer |
| --- | --- | --- |
| `implement` | signature and description | the function body |
| `explain` | the code | the description |
| `document` | the code with its docstring removed | the description |
| `test` | a function | a test from the repo that calls it |

Every example is written by a person. Nothing is synthesised, which is why the
English stays good: the model learns from the docstrings your project already
has.

Python is parsed with the real `ast` module. Java, JavaScript, TypeScript, C#,
Go, Rust, C, C++, PHP, Kotlin, Lua and Luau are matched by doc-comment style.

## What gets rejected, and why

A docstring only becomes training data if it is worth learning from. Running the
collector over Bread's own source shows the filter working:

```
units_found      695
units_accepted   100
rejections:
  no docstring                              558
  docstring quality below threshold          12
  docstring too short                        16
  docstring is reference markup, not prose    1
  function too long to learn from             8
```

Fourteen percent acceptance is the filter doing its job. The rejection counts
appear in every dataset manifest, so you can see what your corpus is losing.

The English filter scores prose between 0 and 1 and rejects anything below 0.6.
It penalises filler ("basically", "in order to", "it is important to note
that"), sentences averaging over 34 words, heavy passive voice, openers that
delay the answer, and text that stops mid-thought. A docstring that is mostly
`:param:` lines is documentation and not prose, so it never trains the voice.

The point is narrow and worth stating: the model's writing style is learned from
the assistant side of its training data, one sentence at a time. Every hedge and
filler phrase you leave in is one it will hand back to you later.

## Measuring what comes out

```bash
python scripts/eval_bread.py --model-id <model> --run-code --save-answers answers.json
```

**Coding is scored objectively.** Twelve tasks, each with a test the model never
sees. Its code is extracted, run in a subprocess, and either passes or fails.
The tasks are ordinary working problems rather than puzzles: parsing a duration
string, merging intervals, an LRU cache, sanitising a filename, fixing a
deliberately broken function. A test asserts every task is solvable, so a
failure is the model's and not the benchmark's.

**English is scored against a rubric,** because prose has no test to run. The
rubric measures form: does the answer lead with the answer, avoid filler, keep
sentences readable, include code when code was asked for, and decline to invent
facts it cannot know. Three of the eight tasks exist only to catch confabulation:
one asks about a FastAPI option that does not exist, one asks for a version
number the model cannot know, and one asks to optimise code that was never
provided. Saying "I do not know" is the passing answer.

A high English score means well-formed writing. It says nothing about whether
the content is true, which is why the runner prints the answers. Read them.

## Catching invented APIs without running anything

The characteristic failure of a small coding model is not bad logic. It is
fluent, well-structured code that calls something which does not exist. Asked
for a disnake bot, the 1.5B model produced code that used `discord.timedelta`
in a file that never imported `discord`, and called a keyword-only method
positionally. Both are deterministic mistakes, and neither needs the code to be
run to find.

```bash
python scripts/check_code.py --answer answer.md
python scripts/check_code.py --file bot.py
cat answer.md | python scripts/check_code.py
```

Three checks, in increasing order of what they need to know:

| Check | Finds | Needs |
| --- | --- | --- |
| `undefined` | a name used but never imported, assigned or built in | nothing |
| `attribute` | a module or class lacking the member taken from it | the library installed |
| `keyword` | a call with a keyword the signature refuses, or too many positional arguments | the library installed |

Findings carry a confidence, and the two are kept apart on purpose. **Certain**
means provably wrong. **Suspected** means an attribute is missing from a class
that could still set it at runtime, so it is worth checking rather than worth
trusting. Only certain findings fail the check and set the exit code, which
makes the script usable in a pre-commit hook.

Reporting a suspicion as a fact is the same failure the model makes. The
checker does not do it.

On the disnake answer it found two certain problems and produced no findings at
all on the corrected version. It does not catch everything: `bot.run(token,
intents=...)` is wrong, and `Bot.run` accepts `**kwargs`, so no static check can
prove it. The report says which libraries it inspected and which were not
installed, so the gaps are visible.

The evaluator runs this over every coding answer, giving a third number
alongside the pass rate: how many answers referenced something that does not
exist.

Nothing from the checked code is executed. The libraries it imports are
imported, so their real signatures can be read. Pass `--no-import` for a purely
syntactic pass that touches nothing.

## Mistakes a name check cannot see

Code can pass every name and signature check and still not work, because the
mistake is in how a library is wired together rather than in what it is called.
A Discord bot that reads `message.content` without the message content intent
resolves perfectly and receives empty strings. A cog that is defined and never
loaded resolves perfectly and never runs.

These are the errors a small model actually makes, they come from a handful of
libraries, and each one is decidable from the syntax tree, so each is a rule in
`quality/frameworks.py` rather than a hope that the model knows better.

| Rule | What it catches |
| --- | --- |
| `message content intent` | `message.content` read while intents are built without it, so the content arrives empty |
| `cog never loaded` | a cog nothing registers, including a `setup(bot)` in an answer that never loads it |
| `Client cannot host commands` | `Client` used where `commands.Bot` is needed |
| `blocking call in async` | `time.sleep`, `requests`, or `subprocess.run` inside `async def`, which stalls the whole loop |
| `on_message without a bot check` | a listener that reacts to its own messages, reported as a suspicion |
| `echo without allowed mentions` | user text repeated back verbatim, which is how a bot gets made to ping everyone |

One more check needs the prose as well as the code. An answer that writes
`from dotenv import load_dotenv` and then says to run `pip install disnake`
fails on its first line, and neither half is wrong on its own. `quality/packaging.py`
compares the imports against the answer's own install command, using a written
table of import-name to distribution-name, and says nothing about a module it
does not have a mapping for rather than guessing.

Two fixes to how code is pulled out of an answer came from the same failure.
Fenced blocks are now matched line by line instead of with one regular
expression, because a regex cannot tell an opening fence from a closing one and
paired a shell block's closing fence with the next opening fence, returning
prose as code. And a block indented inside a numbered step is dedented, because
joining two of them otherwise produced an `IndentationError` and the whole
answer was reported unparseable instead of checked.

On the answer that motivated all of this, a bot that recorded messages and
quoted one back, the checker went from zero findings to five, each one a defect
that stopped the code running.

## Repairing what the checker finds

A model that invents an API does not know it did, and will correct the mistake
when shown it. That makes the failure recoverable rather than fatal, so Bread
closes the loop: generate, check, hand the provable problems back, generate
again.

```bash
bread ask "Write a disnake cog that times a member out"
bread ask "..." --attempts 5 --remember-fixes
```

The same loop runs behind `POST /api/chat` when a request sets
`"verify_code": true`, and the response reports how many attempts it took.

Two rules keep the loop from doing harm.

**Only certain findings are fed back.** A suspicion is shown to you and never
sent to the model, because asking it to fix a guess invites it to break working
code. This is the same distinction the checker draws, carried through to the
repair.

**The cleanest attempt wins, not the last.** A repair that introduces more
problems than it fixes is discarded and the earlier answer is what you get.
Without that rule, a model that misreads the correction makes the answer worse
with every round.

The loop stops early when an answer is clean, when it contains no code at all, or
at the attempt budget. Each round costs one generation, which is why the HTTP API
leaves it off by default while the CLI turns it on.

`--remember-fixes` writes the corrections into memory as `correction` entries, so
the same invented API is not offered to you a second time. See
[CLI.md](CLI.md).

## Running generated code

The coding evaluation executes text a model produced, which is the one thing
Bread refuses to do anywhere else. It is fenced in:

- Nothing runs without `--run-code` on the command line.
- Each snippet runs in a separate subprocess with a timeout, in a temporary
  directory that is deleted afterwards.
- None of it is reachable from the HTTP API.

A subprocess is isolation, not a sandbox. A hostile payload still has your
user's permissions. Evaluate models and task files you trust.

## Using the numbers

Run the evaluation before you fine-tune and after. The comparison is what tells
you whether the run helped:

```bash
python scripts/eval_bread.py --model-id Qwen/Qwen2.5-Coder-7B-Instruct --run-code
python scripts/eval_bread.py --model-id Qwen/Qwen2.5-Coder-7B-Instruct \
  --adapter data/runs/qlora-7b/adapter --run-code
```

What to expect. A fine-tune on your own code should hold the coding score and
improve the English score, because it teaches style rather than capability. If
the coding score drops, the run has damaged the model: raise the mix ratio,
lower the learning rate, or use fewer epochs. That is the failure mode worth
watching for, and without this evaluation you would not see it.

## Adding your own tasks

Both task files are plain YAML under `prompts/evals/`. A coding task needs a
prompt and a test that checks behaviour rather than implementation. An English
task needs a prompt and at least one thing to check: `require_prose`,
`require_code`, `require_any`, `forbid` or `max_words`.

Tasks drawn from your own work are worth more than any generic benchmark,
because they measure the thing you actually need the model to do.
