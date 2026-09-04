# Architecture

Bread is three pieces that share one library: a FastAPI server, a React
interface, and a set of command-line scripts. The scripts import the same
dataset and training code the API uses, so behaviour cannot drift between the
button and the terminal.

```
┌───────────────┐         ┌────────────────────────────────────────┐
│  React + TS   │  HTTP   │             FastAPI backend            │
│  (Vite, 5173) │ ──────► │                (8000)                  │
└───────────────┘   SSE   │                                        │
                          │  routers/    system models chat …      │
┌───────────────┐         │  services/   inference rag datasets    │
│ bread CLI,    │ ──────► │              training prompts memory   │
│ scripts/      │ import  │              quality gpu               │
└───────────────┘         │                                        │
                          └───────┬──────────────┬─────────────────┘
                                  │              │
                          ┌───────▼──────┐  ┌────▼─────────────────┐
                          │ SQLite       │  │ data/                │
                          │ bread.db     │  │  uploads/ vectors/   │
                          │              │  │  datasets/ runs/     │
                          └──────────────┘  └──────────────────────┘
```

## Configuration

`backend/app/config.py` builds one `Settings` object, layered lowest priority
first:

1. Defaults declared on the model.
2. A YAML profile named by `BREAD_CONFIG_FILE` (see `configs/`).
3. Environment variables, including a local `.env`.

Environment always wins over YAML. That ordering is deliberate: a profile file
is a starting point you commit, and an environment variable is the override you
type. The settings object is cached; `/api/settings` mutates it and persists the
change to the `settings` table so it survives a restart.

## Inference backends

`services/inference/` defines one contract, `InferenceBackend`, with four
implementations:

| Backend | Use it when |
| --- | --- |
| `mock` | Developing the UI, running tests, trying Bread with nothing downloaded |
| `transformers` | You have PyTorch with CUDA and want 4-bit or full-precision inference |
| `llama_cpp` | You have a GGUF file and would rather not install the PyTorch stack |
| `openai_compat` | You already run llama-server, vLLM, LM Studio or Ollama |

Every backend yields plain text deltas from `stream()`. The HTTP layer turns
those into Server-Sent Events, so adding a backend never touches a router.

`ModelRegistry` holds exactly one live backend and tracks in-flight streams so
`POST /api/chat/stop` can cancel one. Cancellation is cooperative: a `StopSignal`
that generation loops check between tokens, plus a `StoppingCriteria` for the
Transformers path.

Heavy imports (`torch`, `transformers`, `llama_cpp`) happen inside methods, not
at module scope. A machine with none of them installed still starts the server,
browses the interface and runs the tests.

## Request path for a chat turn

```
POST /api/chat/stream
  → registry.get_or_autoload()        cheap backends load on demand,
                                      real ones must be loaded explicitly
  → chat_service.resolve_conversation()
  → chat_service.retrieve_context()   embed the question, search the space
  → chat_service.build_turns()        system prompt + preset + memory
                                      + history + retrieved context
                                      + question, trimmed to the window
  → backend.stream()                  yields deltas
  → SSE: meta → token* → done
  → persist the assistant message with its citations
```

The prompt is trimmed by dropping the oldest exchanges. The system message and
the newest user message are never dropped: without them the request stops
meaning what the caller asked.

The streaming generator finishes after the request-scoped session may already be
closed, so it opens its own session to write the assistant message.

Recall has a side effect: it counts a use, which is what `memory stats` ranks by.
So `build_turns_with_memory()` returns the entries it recalled rather than
letting a caller recall them a second time to find out what they were.

The buffered `POST /api/chat` can also route generation through
`quality/repair.py`, which generates, checks the answer's Python against the
installed libraries, feeds provable problems back, and keeps the cleanest
attempt. The streaming endpoint cannot: a repair is only knowable after a whole
answer exists, and tokens already sent cannot be taken back.

## Retrieval

`services/rag/` is four small modules:

- `loaders.py` reads a stored file into text, and owns the safety rules:
  filenames rebuilt from a sanitised basename, containment checked against the
  uploads directory, extension allowlist, no execution ever.
- `chunking.py` cuts on line boundaries so citations can name real line numbers,
  and pulls the cut back to a definition boundary in source files.
- `embeddings.py` prefers `sentence-transformers` and falls back to a hashing
  encoder when the model is not cached. The active encoder is always reported.
- `store.py` persists vectors. The default is a NumPy matrix per knowledge
  space; `VECTOR_BACKEND=chroma` swaps in ChromaDB's persistent client.

Re-indexing a document deletes its old vectors first, so it is a replace and not
an append. A content hash on each document makes re-indexing skip unchanged
files.

## Datasets

`services/datasets/` is the library both the API and the scripts use:

`records.py` (JSONL shapes and validation), `licenses.py` (detection and
policy), `secrets.py` (credential patterns and entropy), `quality.py` (cleaning,
MinHash near-duplicate removal, reports), `collect.py` (walking local folders,
streaming external datasets), `manifest.py` (provenance).

Collection runs in a worker thread and writes its state to the `dataset_runs`
table, so a long walk over a large tree does not block the event loop.

## Training

Training runs in a **separate process**. A CUDA out-of-memory crash or a hung
dataloader takes down that process and not the web server, and closing the
browser does not kill the run.

The child prints `BREAD_PROGRESS {...}` lines. A log-pump thread parses them,
writes the raw log to `runs/<name>/train.log`, and updates `training_runs` and
`training_checkpoints`. Preflight checks run first and report every problem at
once rather than failing at the first one.

Config paths are resolved and required to live under `configs/`, because that
path becomes `argv` for a subprocess.

## Pretraining from scratch

`backend/app/services/pretrain/` holds a complete pretraining stack: the model
(`model.py`), the tokenizer and packing pipeline (`data.py`), the training loop
(`train.py`) and the exporter (`export.py`).

The model is a conventional decoder-only transformer with RMSNorm, rotary
position embeddings, grouped-query attention and SwiGLU. Its module names and
tensor layout deliberately match `LlamaForCausalLM`, so export is a rename-free
copy plus a config file and the result loads in any standard tooling. A test
requires identical logits from both implementations, which is what proves the
rotary layout and head grouping are right.

Corpora are packed into a flat memory-mapped array of token ids, so training
reads a corpus larger than RAM by paging in only the windows each batch touches.
Batches are drawn at uniform random offsets rather than swept in order.

## Baking Bread's own weights

`prompts/identity.yaml` is a version-controlled corpus of what Bread says it is
and how it answers. `scripts/build_identity_dataset.py` turns it into training
records, mixing in general coding data at a configurable ratio because identity
data on its own causes catastrophic forgetting.

`scripts/bake_bread_model.py` chains build, validate, train and merge, then
writes a model card and a `bread.json` provenance file into the merged weights.
The output is a standalone model directory rather than a base plus an adapter.

Placeholders in the corpus (`{base_model}`, `{base_license}`) are filled by plain
string replacement rather than `str.format`, because the corpus is full of code
examples containing literal braces. A test asserts the substitution happened and
that the braces survived.

## Database

SQLite through SQLModel, in one file under `data/`. Fourteen tables:
`local_profiles`, `conversations`, `messages`, `settings`, `models`,
`knowledge_spaces`, `documents`, `document_chunks`, `dataset_runs`,
`training_runs`, `training_checkpoints`, `api_keys`, `audit_logs`,
`memory_entries`.

`init_db()` is idempotent: it creates tables, seeds the built-in model catalogue
and a default knowledge space, then adds any nullable column a newer Bread
expects on an older file. Anything more invasive than an added nullable column
belongs in an Alembic revision; the environment is set up under
`backend/alembic/` and reads its database URL from Bread's own settings, so a
migration always targets the file the server uses.

Sessions are opened with `expire_on_commit=False`. Bread commits often (audit
rows, counters), and with the default the ORM objects a request is still holding
get expired, after which `model_dump()` returns an empty dict because SQLModel
reads `__dict__` rather than triggering a lazy refresh.

## Frontend

React 18, TypeScript, Vite, Tailwind, React Router and TanStack Query. Server
state lives in the query cache; the one exception is a partially streamed
answer, which is component state because it is not server state and treating it
as such makes it fight with refetches.

`api/client.ts` is the only place that attaches the API key and turns a failed
response into a structured `ApiError`. `api/stream.ts` implements SSE over POST,
because `EventSource` only does GET and a chat turn needs a body.

In development Vite proxies `/api` to port 8000. In production `npm run build`
emits `frontend/dist`, which the backend mounts and serves with an SPA fallback.

## Testing

244 backend tests and 22 frontend tests. The pretraining tests need PyTorch
and skip cleanly without it. The rest run against a
temporary SQLite file with the mock backend and the hashing embedder, so it
needs no GPU, no model weights and no network. It covers the HTTP surface,
retrieval end to end, the security rules, the dataset pipeline from collection
through to a training file, and the units underneath.
