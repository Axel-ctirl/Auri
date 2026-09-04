# The command line

Bread's browser interface and its command line are two front doors onto the same
backend. A model loaded in one is loaded in the other, memory written in one is
read by the other, and both write to the same local SQLite file.

```
 ______                               __
|_   _ \                             |  ]
  | |_) | _ .--.  .---.  ,--.    .--.| |
  |  __'.[ `/'`\]/ /__\\`'_\ : / /'`\' |
 _| |__) || |    | \__.,// | |,| \__/  |
|_______/[___]    '.__.'\'-;__/ '.__.;__]
```

## Running it

No installation step. The launcher puts `backend/` on `PYTHONPATH` and runs the
module:

```bash
./bread                 # Linux, macOS
bread.cmd               # Windows
python -m app.cli       # from backend/, if you prefer
```

Add the repository directory to your `PATH` and `bread` works from any project.
It uses `.venv/bin/python` when the repository has a virtual environment,
otherwise whatever `python3` resolves to. Set `BREAD_PYTHON` to override that.

## Commands

| Command | What it does |
| --- | --- |
| `bread` | The wordmark and the command list |
| `bread ask "..."` | One question, answered and verified |
| `bread chat` | An interactive session |
| `bread check FILE` | Find invented APIs in a file, without running it |
| `bread memory ...` | Manage what Bread remembers |
| `bread models list/load/unload` | Which model is loaded |
| `bread serve` | Start the API and the web interface |
| `bread doctor` | What is installed, what is missing, what to do |
| `bread status` | One line: version, backend, model, CUDA |
| `bread init-db` | Create the database without starting the server |
| `bread create-key` | Mint an API key for LAN mode |
| `bread system-prompt` | Print the prompt Bread is actually using |

## Asking a question

```bash
bread ask "Why does this handler leak file descriptors?"
bread ask "Write a disnake cog that times a member out" --project .
bread ask "..." --raw                 # plain text, for piping
bread ask "..." --no-verify           # skip the code check
bread ask "..." --attempts 5          # allow more repair rounds
```

Prose and code are rendered separately, so code comes out syntax-highlighted and
copy-pasteable.

## Verifying the code it writes

By default `ask` and `chat` check the Python in an answer before showing it to
you. Every name, module attribute and call signature is resolved against the
libraries actually installed on this machine. Nothing is imported that the answer
does not already import, and nothing is executed.

When the check finds a provable problem, Bread hands it back to the model and
asks for a correction, up to three rounds. Two rules keep this from doing harm:

- **Only provable problems trigger a repair.** A suspicion (an attribute on a
  type Bread cannot resolve) is reported to you but never fed back, because
  asking a model to fix a guess invites it to break working code.
- **The cleanest attempt wins, not the last one.** If a repair introduces more
  problems than it fixes, the earlier answer is what you get.

`--remember-fixes` stores the corrections as memory entries, so the same
invented API is not offered to you twice.

Verification costs one extra generation per round, which is why the HTTP API
leaves it off unless a request asks for it (`"verify_code": true`, or
`VERIFY_CODE_DEFAULT=true`).

## Checking a file you already have

```bash
bread check src/handler.py
```

Same checker, pointed at a file rather than an answer. It exits non-zero when it
finds something provable, which makes it usable in a pre-commit hook or CI step.
It is a static check: it never imports or runs the file.

## An interactive session

```bash
bread chat --project .
```

| In-session command | Effect |
| --- | --- |
| `/remember TEXT` | Store something without leaving the session |
| `/memory` | Show what is remembered here |
| `/clear` | Forget this conversation, keep long-term memory |
| `/help` | The command list |
| `/exit` | Leave |

History lives in the session. Memory outlives it.

## Memory

```bash
bread memory add "Answers stay short" --kind preference --pin
bread memory add "This project pins disnake 2.12.1" --project .
bread memory list
bread memory list --project .
bread memory forget 3cdcf0dd
bread memory stats
```

**Kinds.** `fact`, `preference`, `convention`, `correction`. The kind groups
entries under a heading in the prompt, and corrections rank slightly higher when
Bread picks what to include, because a correction earned its place by being
wrong once already.

**Scope.** An entry is global, or bound to a project directory with `--project`.
Project entries only reach prompts for that directory. The directory is stored as
a SHA-256 prefix with the folder name in front of it, so `bread memory list` does
not print your folder layout to whoever is looking at your screen.

**Pinning.** `--pin` includes an entry in every prompt regardless of relevance.
Everything else is ranked by word overlap with the question, with common words
ignored, and only the top few reach the model. `MEMORY_RECALL_LIMIT` sets how
many.

**What is remembered stays legible.** Entries are rows in the same SQLite file as
everything else, in plain text, and `bread memory forget` really deletes them.
Bread does not infer memories from your conversations: an entry exists because
you asked for it.

Memory is on by default. `MEMORY_ENABLED=false` switches it off without deleting
anything.

## Over HTTP

Every memory operation has an endpoint, so the web interface and other local
tools see the same entries:

```
GET    /api/memory              list, filterable by scope, kind and project_path
POST   /api/memory              remember something
GET    /api/memory/stats        totals, and what actually gets used
DELETE /api/memory/{id}         forget one entry
```

A chat request takes `use_memory`, `project_path` and `verify_code`, and the
response reports `memory_used` and, when verification ran, a `verification`
summary of how many attempts it took and what remained.

## What the CLI does not do

It does not run the code it writes, install packages, edit your files, or send
anything off this machine. Downloads still need their explicit flag, the same as
they do everywhere else in Bread.
