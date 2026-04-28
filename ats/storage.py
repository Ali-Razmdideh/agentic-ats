from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterator

SUPPORTED = {".pdf", ".docx", ".txt", ".md"}


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def iter_resumes(directory: Path) -> Iterator[Path]:
    for p in sorted(directory.iterdir()):
        if p.is_file() and p.suffix.lower() in SUPPORTED:
            yield p


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")
