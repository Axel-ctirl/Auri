# API reference

Bread's REST API is how other tools on your machine talk to it: an editor
plugin, a script, a bot. Everything the web interface does goes through these
endpoints.

Interactive documentation is at `/docs` (Swagger) and `/redoc` when the server
is running, generated from the same Pydantic schemas the code uses. Those two
pages load their own JavaScript from a CDN and need an internet connection to
render; the API itself works offline.

Base URL: `http://127.0.0.1:8000`

## Authentication

Optional on localhost, mandatory when Bread is bound anywhere else.

```bash
curl http://127.0.0.1:8000/api/conversations -H "X-API-Key: bread_sk_..."
curl http://127.0.0.1:8000/api/conversations -H "Authorization: Bearer bread_sk_..."
```

Create a key with `python -m app.cli create-key`, `POST /api/api-keys`, or the
Settings page.

## Errors

Every failure returns the same shape, so a client can branch on `code` instead
of parsing prose:

```json
{
  "error": {
    "code": "backend_unavailable",
    "message": "'Qwen/Qwen2.5-Coder-7B-Instruct' is not in the local Hugging Face cache.",
    "hint": "Run scripts/download_model.py --accept-download, or send confirm_download=true.",
    "details": { "model_id": "Qwen/Qwen2.5-Coder-7B-Instruct" }
  }
}
```

Common codes: `not_found`, `validation_failed`, `conflict`, `unauthorized`,
`rate_limited`, `payload_too_large`, `model_not_loaded`, `backend_unavailable`,
`terms_not_accepted`, `path_outside_data_dir`, `config_outside_repo`.

## Health and system

```
GET  /api/health          Liveness. Never requires a key.
GET  /api/system/gpu      CUDA availability, devices, VRAM, driver.
GET  /api/system/status   Everything: model, GPU, dependencies, warnings.
```

## Models

```
GET  /api/models          List the catalogue.
GET  /api/models/status   What is loaded right now.
POST /api/models/load     Load one.
POST /api/models/unload   Release it.
POST /api/models/register Add a custom entry.
```

```bash
curl -X POST http://127.0.0.1:8000/api/models/load \
  -H "Content-Type: application/json" \
  -d '{"backend": "transformers",
       "model_id": "Qwen/Qwen2.5-Coder-7B-Instruct",
       "quantization_mode": "4bit"}'
```

Weights that are not already cached are **not** downloaded unless the request
sets `"confirm_download": true`. Without it you get a `backend_unavailable`
error explaining exactly what to do.

## Chat

```
POST /api/chat          Send a message, wait for the whole reply.
POST /api/chat/stream   Stream the reply as Server-Sent Events.
POST /api/chat/stop     Cancel a stream, a conversation, or everything.
```

```bash
curl -N http://127.0.0.1:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
        "message": "Explain what this Go function does.",
        "temperature": 0.2,
        "max_new_tokens": 1024,
        "rag_enabled": true,
        "knowledge_space_id": null,
        "preset": "rest_api"
      }'
```

The stream emits four event types:

```
event: meta
data: {"conversation_id":"…","stream_id":"…","model_id":"…","backend":"…","sources":[…],"memory_used":[…]}

event: token
data: {"delta":"partial text"}

event: done
data: {"message_id":"…","latency_ms":1420,"stopped_early":false,"characters":880,"error":null}

event: error
data: {"code":"generation_failed","message":"…","hint":"…"}
```

`meta` arrives once, up front, carrying the citations so a client can render
sources before the first token. `done` always arrives, including after an error,
so a client can close its state machine in one place.

Stop a stream with the `stream_id` from `meta`:

```bash
curl -X POST http://127.0.0.1:8000/api/chat/stop \
  -H "Content-Type: application/json" -d '{"stream_id": "…"}'
```

Omit both fields to stop everything.

### Memory and verification on a chat turn

Three request fields change what a turn does:

| Field | Effect |
| --- | --- |
| `use_memory` | Include remembered context in the system prompt. Defaults to `MEMORY_ENABLED`. |
| `project_path` | The working directory this turn belongs to. Project-scoped memory for it is recalled alongside global memory. |
| `verify_code` | Check the Python in the reply for invented APIs and let the model correct itself first. Buffered `/api/chat` only. |

The buffered response reports both back:

```json
{
  "content": "…",
  "memory_used": ["This project pins disnake 2.12.1"],
  "verification": {
    "repaired": true,
    "problems_at_first_attempt": 1,
    "problems_remaining": 0,
    "attempts": [{"attempt": 1, "problems": 1, "findings": [...]}, {"attempt": 2, "problems": 0, "findings": []}]
  }
}
```

`verification` is `null` when the check did not run. Verification costs one extra
generation per repair round, which is why it is opt-in. Nothing in the reply is
executed to check it.

## Memory

```
GET    /api/memory              ?scope=&kind=&project_path=&limit=
POST   /api/memory
GET    /api/memory/stats
DELETE /api/memory/{id}
```

```bash
curl -X POST http://127.0.0.1:8000/api/memory \
  -H "Content-Type: application/json" \
  -d '{"content": "This project pins disnake 2.12.1",
       "kind": "convention",
       "scope": "project",
       "project_path": "/home/you/bots"}'
```

`kind` is one of `fact`, `preference`, `convention`, `correction`. `scope` is
`global` or `project`, and a project entry needs a `project_path`. The stored
`project_key` is a hash with the folder name in front of it, not the path.

Listing with `project_path` returns that project's entries alongside the global
ones, which is what a prompt in that directory would see. Listing with
`scope=project` narrows it to that project alone.

Deleting an entry deletes the row. See [CLI.md](CLI.md) for the same operations
from the command line.

## Conversations

```
GET    /api/conversations                   ?search=&include_archived=&limit=
POST   /api/conversations
GET    /api/conversations/{id}              Includes every message.
PATCH  /api/conversations/{id}              Rename, pin, archive, reconfigure.
DELETE /api/conversations/{id}
POST   /api/conversations/{id}/messages/{message_id}/rollback
```

Rollback drops a message and everything after it, which is how regeneration
works: roll back to the user's message, then send it again.

## Knowledge spaces, documents and retrieval

```
GET    /api/knowledge-spaces
POST   /api/knowledge-spaces
PATCH  /api/knowledge-spaces/{id}
DELETE /api/knowledge-spaces/{id}      Also deletes its documents and vectors.

POST   /api/documents/upload           multipart/form-data
POST   /api/documents/index
GET    /api/documents                  ?knowledge_space_id=
DELETE /api/documents/{id}
POST   /api/rag/search
```

```bash
curl -X POST http://127.0.0.1:8000/api/documents/upload \
  -F "files=@src/main.py" \
  -F "files=@README.md" \
  -F "index_now=true"
```

The response separates `documents` (stored) from `skipped`, each with a reason:
an unsupported extension, a size over the limit, or content already indexed.

## Datasets

```
GET  /api/datasets           Collection runs.
GET  /api/datasets/sources   Sources and their terms URLs.
POST /api/datasets/collect   Start a run.
POST /api/datasets/validate  Validate a JSONL file.
GET  /api/datasets/report    ?path=  Summarise a JSONL file.
```

```bash
curl -X POST http://127.0.0.1:8000/api/datasets/collect \
  -H "Content-Type: application/json" \
  -d '{"name": "my_projects",
       "source": "local_code",
       "input_paths": ["/home/me/projects"],
       "languages": ["python", "java"],
       "max_records": 5000}'
```

External sources return `terms_not_accepted` until the request sets
`"accept_terms": true`. The error carries the terms URL in `details`.

Dataset paths must resolve inside the Bread data directory.

## Training

```
GET  /api/training/runs
GET  /api/training/configs
POST /api/training/start
POST /api/training/stop
GET  /api/training/{id}
GET  /api/training/{id}/logs    ?tail=400
```

```bash
curl -X POST http://127.0.0.1:8000/api/training/start \
  -H "Content-Type: application/json" \
  -d '{"name": "bread-qlora",
       "config_path": "configs/training/qlora_7b.yaml",
       "dataset_path": "data/datasets/bread_sft.jsonl",
       "dry_run": true}'
```

Send `dry_run: true` first. It validates the config, the dataset and the GPU and
returns every problem it finds without starting anything. A real start with
unmet requirements returns `training_preflight_failed` with the same list in
`details.problems`.

Config paths must resolve inside `configs/`.

## Settings and keys

```
GET    /api/settings
PATCH  /api/settings
GET    /api/api-keys
POST   /api/api-keys
DELETE /api/api-keys/{id}
GET    /api/audit-logs          ?limit=  Recent state-changing actions.
GET    /api/prompts/presets
GET    /api/prompts/presets/{name}
```

Settings changes persist to the database and apply immediately. Network settings
(bind address, port, key enforcement) are deliberately not editable over HTTP;
change them in `.env`.

## A minimal client

```python
import json
import httpx

BASE = "http://127.0.0.1:8000"
HEADERS = {"Content-Type": "application/json"}   # add X-API-Key if enforced


def ask(message: str, conversation_id: str | None = None) -> str:
    """Stream one answer and return it, printing tokens as they arrive."""

    body = {"message": message, "conversation_id": conversation_id}
    collected = []

    with httpx.stream("POST", f"{BASE}/api/chat/stream",
                      headers=HEADERS, json=body, timeout=300) as response:
        response.raise_for_status()
        event = None
        for line in response.iter_lines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:") and event == "token":
                delta = json.loads(line[5:])["delta"]
                collected.append(delta)
                print(delta, end="", flush=True)

    return "".join(collected)


if __name__ == "__main__":
    ask("Write a Python function that parses an ISO 8601 duration.")
```
