from __future__ import annotations

import gzip
from pathlib import Path


def gzip_export(source: Path, target: Path, on_progress=None) -> None:
    total = source.stat().st_size
    written = 0
    with open(source, "rb") as reader, gzip.open(target, "wb", compresslevel=6) as writer:
        while block := reader.read(1 << 20):
            writer.write(block)
            written += len(block)
            if on_progress is not None:
                on_progress(written, total)
