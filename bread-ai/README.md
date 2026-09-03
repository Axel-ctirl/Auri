# Bread 🍞

A local-first AI coding assistant. It runs an open-weight model on your own
machine, answers questions about your own code, indexes your own documents for
retrieval, and fine-tunes adapters on your own GPU.

Everything stays on your computer. No cloud API, no telemetry, no analytics, no
background uploads. The only outbound requests Bread makes are model or dataset
downloads you explicitly confirm.

---

## What Bread is, and what it is not

**Bread is** a chat interface, a REST API and a training pipeline built around an
existing open-weight coding model such as `Qwen/Qwen2.5-Coder-7B-Instruct`. It
explains code, writes code, debugs stack traces, refactors, reviews, finds
likely bugs, suggests secure alternatives, writes tests and documentation,
translates between languages, and turns plain-English requirements into a
working project skeleton.

**Bread is not** Claude, GPT or any other hosted frontier model, and it does not
match them. It runs a smaller open-weight model and the capability gap is real.

**Bread does not train a language model from scratch**, and neither does any
single consumer GPU. Pretraining a frontier model takes thousands of
accelerators running for weeks over trillions of tokens, plus the data pipeline
and infrastructure to keep them fed. An RTX 5090 with 32 GB is a serious card,
and it is roughly six orders of magnitude short of that.

What one RTX 5090 does very well is **LoRA and QLoRA fine-tuning**: freezing a
pretrained model and training small adapter matrices on top of it. That teaches
the model your conventions, your libraries and the kind of work you actually do.
It is a genuine improvement, and it is a different thing from pretraining.

Bread also ships a tiny from-scratch trainer. It is labelled a toy because it is
one: a few million parameters on a few megabytes of text, there to make the
mechanics of pretraining concrete. It will not produce a useful assistant. See
[docs/LIMITATIONS.md](docs/LIMITATIONS.md) for the full accounting.

---

## Quick start

Bread boots with a **mock backend** that downloads nothing, so you can see the
whole interface working before committing to a 15 GB model download.

### Windows

```powershell
git clone <your-fork> bread-ai
cd bread-ai

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env

# Terminal 1: the API
cd backend
python -m app.cli serve

# Terminal 2: the interface
cd frontend
npm install
npm run dev
```

Open <http://127.0.0.1:5173>.

### Linux and macOS

```bash
git clone <your-fork> bread-ai
cd bread-ai

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

(cd backend && python -m app.cli serve) &
(cd frontend && npm install && npm run dev)
```

### One process instead of two

```bash
cd frontend && npm run build     # emits frontend/dist
cd ../backend && python -m app.cli serve
```

The backend serves the built interface at <http://127.0.0.1:8000>, and the API
docs at `/docs`.

---

## Running a real model

Bread never downloads weights on its own. Fetch them deliberately:

```bash
python scripts/download_model.py \
  --model-id Qwen/Qwen2.5-Coder-7B-Instruct \
  --accept-download
```

Then point Bread at it in `.env`:

```ini
MODEL_BACKEND=transformers
MODEL_ID=Qwen/Qwen2.5-Coder-7B-Instruct
QUANTIZATION_MODE=4bit
```

and load it from the **Models** page, or:

```bash
curl -X POST http://127.0.0.1:8000/api/models/load \
  -H "Content-Type: application/json" \
  -d '{"backend": "transformers", "model_id": "Qwen/Qwen2.5-Coder-7B-Instruct"}'
```

Real inference needs PyTorch with CUDA. See
[docs/WINDOWS_SETUP.md](docs/WINDOWS_SETUP.md) or
[docs/LINUX_SETUP.md](docs/LINUX_SETUP.md); the RTX 5090 in particular needs a
torch build compiled against CUDA 12.8 or newer.

### Which model for 32 GB

| Model | Quantization | VRAM in use | Notes |
| --- | --- | --- | --- |
| Qwen2.5-Coder-1.5B-Instruct | none (bf16) | ~4 GB | Fast, good for completions, weak at reasoning |
| Qwen2.5-Coder-7B-Instruct | 4-bit NF4 | ~6 GB | Recommended default; leaves room to train |
| Qwen2.5-Coder-14B-Instruct | 4-bit NF4 | ~11 GB | Better answers, roughly half the speed |
| A 32B model | 4-bit NF4 | ~20 GB | Fits, but long contexts get tight |

Bread's model choice is configurable, not hardcoded. Five ready profiles live in
[`configs/`](configs): plain Transformers, 4-bit QLoRA-ready, GGUF through
llama.cpp, an OpenAI-compatible local server, and the mock backend.

---

## Retrieval over your own documents

Upload code, notes or PDFs into a **knowledge space**, and Bread cites them when
it answers. Twenty-six file types are supported, from `.py` and `.java` through
`.luau` and `.sql` to `.pdf`.

Answers cite the source filename, the chunk number and the line range. Uploaded
code is read as data: Bread never imports or executes it. Filenames from the
browser are rebuilt from a sanitised basename, so nothing escapes the uploads
directory.

Retrieval works with no model cache at all, using a built-in hashing encoder as a
fallback, and Bread tells you when that is what is running. See
[docs/RAG.md](docs/RAG.md).

---

## Building a training dataset

The recommended source is code you already own:

```bash
python scripts/collect_local_code.py \
  --path "C:/dev/minecraft-plugins" \
  --path "~/projects" \
  --languages python java typescript lua luau \
  --max-records 5000

python scripts/clean_dataset.py    --input data/datasets/local_code.jsonl
python scripts/validate_dataset.py --input data/datasets/local_code.clean.jsonl
python scripts/dataset_report.py   --input data/datasets/local_code.clean.jsonl
python scripts/build_sft_dataset.py \
  --input data/datasets/local_code.clean.jsonl \
  --output data/datasets/bread_sft.jsonl
```

The collector reads each project's LICENSE, skips anything it cannot identify,
skips files that look like they hold credentials, removes exact and near
duplicates, and writes a manifest recording where every record came from.

External sources (CodeSearchNet, The Stack, FineWeb-Edu, OpenWebText) exist too
and require `--accept-terms` before Bread will download anything. Bread never
scrapes websites. See [docs/DATASETS.md](docs/DATASETS.md), and read the licenses
before you redistribute data or publish weights trained on it.

---

## Fine-tuning on an RTX 5090

```bash
pip install -r requirements-train.txt

# Check the config, the dataset and the GPU without launching anything.
python scripts/train_qlora.py --config configs/training/qlora_7b.yaml --dry-run

python scripts/train_qlora.py --config configs/training/qlora_7b.yaml
```

Then point Bread at the adapter:

```ini
MODEL_ID=Qwen/Qwen2.5-Coder-7B-Instruct
ADAPTER_PATH=data/runs/qlora-7b/adapter
```

Four configs ship with Bread: 7B QLoRA (the default), 14B QLoRA, a 1.5B LoRA
fallback for 8-12 GB cards, and the toy from-scratch trainer. The Training page
runs the same scripts and tails their logs. See
[docs/TRAINING.md](docs/TRAINING.md).

---

## The API

Bread's REST API is how other tools on this machine talk to it: an editor
plugin, a script, a Discord bot.

```bash
curl -N http://127.0.0.1:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Write a Go function that reads a CSV into a struct slice."}'
```

Full reference at `/docs` when the server is running, or
[docs/API.md](docs/API.md).

---

## Security

Bread binds to `127.0.0.1` by default, where an API key is optional. Bind it
anywhere else and key checks turn on automatically, with a warning in the CLI, a
banner in the interface and a note in `/api/system/status`. There is no
transport encryption without a reverse proxy in front. See
[docs/SECURITY.md](docs/SECURITY.md).

Bread never executes code it generated and never executes code you uploaded.

---

## Project layout

```
bread-ai/
├── backend/app/          FastAPI application
│   ├── routers/          One module per endpoint group
│   └── services/         Inference backends, RAG, datasets, training
├── backend/tests/        99 pytest tests, no GPU required
├── frontend/src/         React + TypeScript interface
├── scripts/              Dataset collection, cleaning, training, evaluation
├── configs/              Model profiles, training configs, license policy
├── prompts/              System prompt and eleven task presets
├── docs/                 Architecture, training, datasets, RAG, security
└── data/                 Everything Bread stores (gitignored)
```

## Development

```bash
pip install -r requirements-dev.txt
pytest                       # backend
ruff check . && black --check .
cd frontend && npm test && npm run typecheck
```

## Requirements

| | Minimum | Recommended |
| --- | --- | --- |
| GPU | 8 GB VRAM (1.5B LoRA) | RTX 5090, 32 GB |
| System RAM | 16 GB | 64 GB |
| Disk | 20 GB | 100 GB free |
| Python | 3.11 | 3.11 |
| Node | 18 | 22 |

Bread runs with no GPU at all on the mock backend or against a llama.cpp server,
and the test suite needs neither a GPU nor a downloaded model.

## License

MIT. See [LICENSE](LICENSE). This covers Bread's own code; the models and
datasets you point it at carry their own terms.

Bread is not affiliated with Anthropic, OpenAI, Mojang, Roblox, or any model or
dataset provider it can be configured to use.
