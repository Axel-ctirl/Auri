from __future__ import annotations

import asyncio
import json
import os
import tempfile
from typing import Any, Callable, TypeVar

from bread.config import DATA_DIR

T = TypeVar("T")


class JSONStore:
    """Atomic, lock-guarded JSON file backing a single collection.

    Reads are cached in memory after the first load; every mutation is
    serialized through a per-store ``asyncio.Lock`` and persisted via a
    temp-file + ``os.replace`` so a crash mid-write can't corrupt the file.
    """

    def __init__(self, name: str, default: Any = None) -> None:
        self._path = os.path.join(DATA_DIR, f"{name}.json")
        self._default = {} if default is None else default
        self._lock = asyncio.Lock()
        self._cache: Any = None

    def _read_sync(self) -> Any:
        if not os.path.exists(self._path):
            return json.loads(json.dumps(self._default))
        with open(self._path, encoding="utf-8") as fh:
            return json.load(fh)

    def _write_sync(self, data: Any) -> None:
        os.makedirs(DATA_DIR, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=DATA_DIR, prefix=".tmp-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, sort_keys=True)
            os.replace(tmp_path, self._path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    async def read(self) -> Any:
        async with self._lock:
            if self._cache is None:
                self._cache = await asyncio.to_thread(self._read_sync)
            return self._cache

    async def mutate(self, mutator: Callable[[Any], T]) -> T:
        """Run ``mutator`` against the cached data under the lock, persist, return its result."""
        async with self._lock:
            if self._cache is None:
                self._cache = await asyncio.to_thread(self._read_sync)
            result = mutator(self._cache)
            await asyncio.to_thread(self._write_sync, self._cache)
            return result
