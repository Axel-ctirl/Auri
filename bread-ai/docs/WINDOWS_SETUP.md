# Windows setup

Bread targets Windows first. The one genuinely fiddly part is PyTorch with
CUDA; everything else is a normal Python and Node install.

## 1. Prerequisites

- **Windows 10 or 11**, 64-bit.
- **Python 3.11** from [python.org](https://www.python.org/downloads/). Tick
  "Add python.exe to PATH" during install. The Microsoft Store build works but
  puts packages in a redirected directory that confuses some tools.
- **Node.js 18 or newer** from [nodejs.org](https://nodejs.org/).
- **Git for Windows**.
- **An up-to-date NVIDIA driver.** Check with `nvidia-smi` in a terminal. For an
  RTX 5090 you want a recent driver from the 570 series or newer.

Verify:

```powershell
python --version     # 3.11.x
node --version       # v18+
nvidia-smi           # driver version and GPU name
```

## 2. Bread itself

```powershell
git clone <your-fork> bread-ai
cd bread-ai

python -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

copy .env.example .env
```

Start it:

```powershell
cd backend
python -m app.cli serve
```

and in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open <http://127.0.0.1:5173>. Bread starts on the mock backend, so this works
before anything large is downloaded.

If `.venv\Scripts\activate` is blocked, PowerShell's execution policy is
stopping the script:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

## 3. PyTorch with CUDA

This is the step to be careful with. **Install torch before anything that
depends on it**, and install it from PyTorch's own index, not from PyPI's
default wheel, which may be CPU-only.

For an RTX 5090 (Blackwell, compute capability 12.0) you need a build compiled
against **CUDA 12.8 or newer**. An older wheel imports fine and then fails at
the first kernel launch with:

```
CUDA error: no kernel image is available for execution on the device
```

```powershell
pip install torch --index-url https://download.pytorch.org/whl/cu128
```

For older cards (30-series, 40-series), `cu121` or `cu124` is fine.

Verify before going further:

```powershell
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
python -c "import torch; print(torch.zeros(8, device='cuda').sum())"
```

The second line is the one that matters. `torch.cuda.is_available()` returning
`True` only proves torch found a device; running a kernel proves the build
matches it.

## 4. Inference and training packages

```powershell
pip install -r requirements-inference.txt
pip install -r requirements-train.txt      # only if you plan to fine-tune
```

### bitsandbytes on Windows

`bitsandbytes` provides the 4-bit and 8-bit kernels QLoRA needs. Recent versions
ship Windows wheels, but pip can still resolve one built for a different CUDA
version. Check it:

```powershell
python -c "import bitsandbytes; print(bitsandbytes.__version__)"
python -m bitsandbytes
```

The second command runs its own diagnostic. If it reports a missing or mismatched
CUDA library, reinstall against your CUDA version:

```powershell
pip uninstall -y bitsandbytes
pip install bitsandbytes --index-url https://pypi.org/simple --force-reinstall
```

If it still will not work, Bread runs without it: set `QUANTIZATION_MODE=none`
and use a 1.5B model, or use the llama.cpp backend with a GGUF file instead.

### llama.cpp (optional)

```powershell
pip install llama-cpp-python
```

The default wheel is CPU-only. For GPU offload you need a CUDA build, which
either comes from a prebuilt wheel matching your CUDA version or is compiled
locally with Visual Studio Build Tools and `CMAKE_ARGS="-DGGML_CUDA=on"`.

## 5. Download a model

```powershell
python scripts\download_model.py --model-id Qwen/Qwen2.5-Coder-7B-Instruct --accept-download
```

By default this lands in `%USERPROFILE%\.cache\huggingface`. If your C: drive is
tight, move it:

```powershell
setx HF_HOME "D:\huggingface"
```

Then restart the terminal, and edit `.env`:

```ini
MODEL_BACKEND=transformers
MODEL_ID=Qwen/Qwen2.5-Coder-7B-Instruct
QUANTIZATION_MODE=4bit
```

Restart the server and load the model from the Models page.

## 6. Check the whole environment

```powershell
cd backend
python -m app.cli status
```

That prints your GPU, VRAM, torch and CUDA versions and which optional packages
are installed. Paste its output into any bug report.

## Windows-specific notes

**Paths in configs.** Use forward slashes or escaped backslashes in `.env` and
YAML. `C:/models/model.gguf` works; `C:\models\model.gguf` inside a
double-quoted YAML string does not.

**Long paths.** Some model repositories have deep nesting that trips Windows'
260-character limit. Enable long paths:

```powershell
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
  -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

**Windows Defender** scans every file of a large model download and slows it
noticeably. Excluding your Hugging Face cache directory is a reasonable
trade-off on a machine you control.

**Firewall prompts.** Bread binds to `127.0.0.1`, so Windows should not prompt.
If it does, you or a config changed the bind address; read
[SECURITY.md](SECURITY.md) before allowing it.

**WSL2.** Bread runs well under WSL2 with the NVIDIA WSL driver, and the Linux
instructions apply. Note that disk access across the Windows/WSL boundary is
slow, so keep the repository and the model cache inside the WSL filesystem.
