"""GPU and optional-dependency probing.

Everything here degrades quietly: a machine with no CUDA, no torch and no
nvidia-smi still gets a well-formed answer explaining what is missing.
"""

from __future__ import annotations

import importlib.util
import platform
import shutil
import subprocess
import sys
from typing import Any

OPTIONAL_DEPENDENCIES = (
    "torch",
    "transformers",
    "accelerate",
    "peft",
    "trl",
    "bitsandbytes",
    "datasets",
    "sentence_transformers",
    "chromadb",
    "llama_cpp",
    "pypdf",
)


def dependency_report() -> dict[str, bool]:
    return {name: importlib.util.find_spec(name) is not None for name in OPTIONAL_DEPENDENCIES}


def gpu_status() -> dict[str, Any]:
    notes: list[str] = []
    torch_spec = importlib.util.find_spec("torch")

    if torch_spec is None:
        notes.append(
            "PyTorch is not installed, so Bread cannot report VRAM or run the "
            "transformers backend. Install the CUDA build for your driver."
        )
        return {
            "cuda_available": False,
            "torch_installed": False,
            "device_count": 0,
            "devices": [],
            "driver_version": _driver_version(),
            "notes": notes,
        }

    import torch

    cuda_available = bool(torch.cuda.is_available())
    devices: list[dict[str, Any]] = []

    if cuda_available:
        for index in range(torch.cuda.device_count()):
            properties = torch.cuda.get_device_properties(index)
            free_bytes, total_bytes = torch.cuda.mem_get_info(index)
            devices.append(
                {
                    "index": index,
                    "name": properties.name,
                    "total_memory_mb": round(total_bytes / (1024**2), 1),
                    "free_memory_mb": round(free_bytes / (1024**2), 1),
                    "allocated_memory_mb": round(torch.cuda.memory_allocated(index) / (1024**2), 1),
                    "reserved_memory_mb": round(torch.cuda.memory_reserved(index) / (1024**2), 1),
                    "capability": f"{properties.major}.{properties.minor}",
                }
            )
    else:
        notes.append(
            "torch.cuda.is_available() is False. Check that the NVIDIA driver is "
            "installed and that torch was installed with a matching CUDA build."
        )

    return {
        "cuda_available": cuda_available,
        "torch_installed": True,
        "torch_version": torch.__version__,
        "cuda_version": getattr(torch.version, "cuda", None),
        "driver_version": _driver_version(),
        "device_count": len(devices),
        "devices": devices,
        "notes": notes,
    }


def _driver_version() -> str | None:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return None
    try:
        output = subprocess.run(
            [executable, "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    first_line = output.stdout.strip().splitlines()
    return first_line[0].strip() if first_line else None


def platform_summary() -> dict[str, str]:
    return {
        "python_version": sys.version.split()[0],
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
    }
