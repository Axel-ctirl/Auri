# Linux setup

## 1. Prerequisites

- Python 3.11 or newer, with `venv`.
- Node.js 18 or newer.
- An NVIDIA driver new enough for your card. Check with `nvidia-smi`.

On Debian and Ubuntu:

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip git build-essential
```

The CUDA toolkit is **not** required for inference or QLoRA: the PyTorch wheels
bundle the runtime they need. You need the toolkit only to compile something
yourself, such as a CUDA build of `llama-cpp-python` or `flash-attn`.

## 2. Bread itself

```bash
git clone <your-fork> bread-ai
cd bread-ai

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env

# Terminal 1
cd backend && python -m app.cli serve

# Terminal 2
cd frontend && npm install && npm run dev
```

Open <http://127.0.0.1:5173>.

## 3. PyTorch with CUDA

Install torch first, from PyTorch's index, matching your driver. For an RTX 5090
you need a build compiled against CUDA 12.8 or newer:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu128
```

Verify with a real kernel launch, not just an availability check:

```bash
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
python -c "import torch; print(torch.zeros(8, device='cuda').sum())"
```

Then:

```bash
pip install -r requirements-inference.txt
pip install -r requirements-train.txt      # only if you plan to fine-tune
```

## 4. Download a model

```bash
python scripts/download_model.py \
  --model-id Qwen/Qwen2.5-Coder-7B-Instruct \
  --accept-download
```

The cache lives at `~/.cache/huggingface` unless `HF_HOME` says otherwise:

```bash
export HF_HOME=/mnt/big-disk/huggingface
```

## 5. Check the environment

```bash
cd backend && python -m app.cli status
```

## Running Bread as a service

A user unit keeps Bread running without a login shell. Adjust the paths:

```ini
# ~/.config/systemd/user/bread.service
[Unit]
Description=Bread local coding assistant
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/bread-ai/backend
Environment="PATH=%h/bread-ai/.venv/bin"
ExecStart=%h/bread-ai/.venv/bin/python -m app.cli serve
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now bread
journalctl --user -u bread -f
```

Build the frontend first (`cd frontend && npm run build`) so the one process
serves the interface too.

If you want it to survive logout, `sudo loginctl enable-linger $USER`.

## Docker

There is no shipped image, on purpose: pinning a CUDA base image would make one
driver version right and every other one wrong. If you build your own, start
from `nvidia/cuda:12.8.0-runtime-ubuntu22.04`, install the same torch wheel you
would install on the host, and run with `--gpus all` and the
`nvidia-container-toolkit` installed. Mount `data/` and the Hugging Face cache
as volumes so a rebuild does not discard them.

## Notes

**File descriptors.** Indexing a very large tree can exhaust the default limit.
`ulimit -n 4096` in the shell that runs Bread is usually enough.

**Multiple GPUs.** `MODEL_DEVICE=auto` lets Accelerate shard across whatever it
finds. Pin a single card with `CUDA_VISIBLE_DEVICES=0`.

**Headless servers.** Bread binds to `127.0.0.1`. To reach it from your laptop,
forward the port over SSH rather than binding to `0.0.0.0`:

```bash
ssh -L 8000:127.0.0.1:8000 user@server
```

That gives you an encrypted tunnel and leaves nothing listening on the network.
If you must bind wider, read [SECURITY.md](SECURITY.md) first.
