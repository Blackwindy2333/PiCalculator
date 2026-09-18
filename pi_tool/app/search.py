from __future__ import annotations

import mmap
from pathlib import Path

from PySide6.QtCore import QThread, Signal

CHUNK_BYTES = 1 << 26


class SearchWorker(QThread):
    finished_results = Signal(list)
    failed = Signal(str)

    def __init__(self, path: Path, needle: str, limit: int = 100) -> None:
        super().__init__()
        self.path = path
        self.needle = needle
        self.limit = limit
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        needle = self.needle.encode("ascii")
        results: list[tuple[int, int]] = []
        carry = b""
        digits_seen = 0
        try:
            with open(self.path, "rb") as handle:
                with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as view:
                    position = 0
                    first = True
                    while position < len(view) and len(results) < self.limit and not self._cancelled:
                        block = view[position : position + CHUNK_BYTES]
                        position += CHUNK_BYTES
                        if first:
                            block = block[2:]
                            first = False
                        collapsed = block.replace(b"\n", b"")
                        data = carry + collapsed
                        start_index = digits_seen - len(carry)
                        at = data.find(needle)
                        while at != -1 and len(results) < self.limit:
                            results.append((start_index + at + 1, len(needle)))
                            at = data.find(needle, at + 1)
                        keep = len(needle) - 1
                        carry = data[-keep:] if keep else b""
                        digits_seen += len(collapsed)
            self.finished_results.emit(results)
        except OSError as error:
            self.failed.emit(str(error))
