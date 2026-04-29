"""ATS storage layer: Postgres (via SQLAlchemy async) + MinIO/S3."""

from __future__ import annotations

from .blob import BlobStore, BlobStoreProtocol
from .db import make_engine, make_sessionmaker
from .files import SUPPORTED, hash_file, hash_text, iter_resumes, read_text_file
from .uow import RepositoryBundle, current_uow, run_context, uow

__all__ = [
    "BlobStore",
    "BlobStoreProtocol",
    "RepositoryBundle",
    "SUPPORTED",
    "current_uow",
    "hash_file",
    "hash_text",
    "iter_resumes",
    "make_engine",
    "make_sessionmaker",
    "read_text_file",
    "run_context",
    "uow",
]
