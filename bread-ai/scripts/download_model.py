#!/usr/bin/env python
"""Download model weights into the local Hugging Face cache, on purpose.

    python scripts/download_model.py --model-id Qwen/Qwen2.5-Coder-7B-Instruct --accept-download

Bread never downloads weights on its own. This script is the explicit path, and
it tells you how large the download is before it starts.

Rough sizes: a 1.5B model is about 3 GB, a 7B about 15 GB, a 14B about 29 GB.
Quantization happens at load time, so the download is the full-precision size
regardless of QUANTIZATION_MODE.
"""

from __future__ import annotations

import argparse
import sys

from _bootstrap import print_header, print_table

KNOWN_SIZES_GB = {
    "Qwen/Qwen2.5-Coder-1.5B-Instruct": 3.1,
    "Qwen/Qwen2.5-Coder-7B-Instruct": 15.2,
    "Qwen/Qwen2.5-Coder-14B-Instruct": 29.5,
    "sentence-transformers/all-MiniLM-L6-v2": 0.1,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--model-id", required=True)
    parser.add_argument(
        "--accept-download",
        action="store_true",
        help="Required. Confirms you want to transfer this much data.",
    )
    parser.add_argument("--revision", default=None, help="Pin a specific commit or tag.")
    parser.add_argument(
        "--embedding",
        action="store_true",
        help="Download a sentence-transformers embedding model instead of a causal LM.",
    )
    args = parser.parse_args(argv)

    size = KNOWN_SIZES_GB.get(args.model_id)
    print_header(f"Downloading {args.model_id}")
    print_table(
        {
            "estimated size": f"{size} GB" if size else "unknown (check the model card)",
            "revision": args.revision or "(default branch)",
            "destination": "your Hugging Face cache (HF_HOME or ~/.cache/huggingface)",
        }
    )

    if not args.accept_download:
        print(
            "\nerror: re-run with --accept-download once you are ready to transfer "
            "this. Nothing has been downloaded.",
            file=sys.stderr,
        )
        return 2

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print(
            "error: huggingface_hub is not installed. "
            "pip install -r requirements-inference.txt",
            file=sys.stderr,
        )
        return 3

    print("\nStarting. This can take a while and is resumable.\n")
    try:
        path = snapshot_download(repo_id=args.model_id, revision=args.revision)
    except Exception as exc:  # noqa: BLE001 - the user needs the real reason
        print(f"error: download failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4

    print_header("Done")
    print_table({"cached at": path})
    print("\nBread can now load this model without ALLOW_MODEL_DOWNLOAD or")
    print("confirm_download, because the weights are already local.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
