"""A .zip held whole so it can be read piece by piece when the host ignores Range.

Held in memory up to `ram_bytes` and in an unnamed temporary file beyond that
(`tempfile.SpooledTemporaryFile`): the operating system removes the file when
the object is closed or collected, even after a crash, so nothing is left to
sweep. Slicing returns the same bytes `bytes[start:stop]` would, which is all
the Range-based zip readers in csv_reader ask of their `blob`.
"""

from __future__ import annotations

import tempfile
import threading


class SpooledBlob:
    def __init__(self, ram_bytes: int) -> None:
        self._ram_bytes = ram_bytes
        self._file = tempfile.SpooledTemporaryFile(max_size=ram_bytes, mode="w+b")  # noqa: SIM115
        self._size = 0
        # Reads come from the event loop and from a parsing thread at once.
        self._lock = threading.Lock()

    def write(self, data: bytes) -> None:
        with self._lock:
            self._file.seek(self._size)
            self._file.write(data)
            self._size += len(data)

    def __len__(self) -> int:
        return self._size

    def __getitem__(self, key: slice) -> bytes:
        if not isinstance(key, slice) or key.step not in (None, 1):
            raise TypeError("SpooledBlob only supports plain slices")
        start, stop, _step = key.indices(self._size)
        with self._lock:
            self._file.seek(start)
            return self._file.read(max(stop - start, 0))

    @property
    def on_disk(self) -> bool:
        """True once the bytes outgrew `ram_bytes` and went to a temporary file."""
        return self._size > self._ram_bytes

    def close(self) -> None:
        self._file.close()
