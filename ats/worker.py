"""Background worker that processes queued runs.

The dashboard inserts ``runs`` rows with ``status='queued'`` and a
``queued_inputs`` payload pointing at MinIO blobs. This module's loop
claims them via ``FOR UPDATE SKIP LOCKED`` and invokes the existing
orchestrator pipeline.

Single worker for v1; scale by starting more processes — the SKIP LOCKED
claim makes it safe.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import tempfile
from pathlib import Path
from typing import Any

from ats.config import Settings
from ats.orchestrator import run_pipeline
from ats.storage import BlobStore, make_engine, make_sessionmaker
from ats.storage.models import RunStatus
from ats.storage.repositories.runs import claim_next_queued_run, mark_run_status

log = logging.getLogger("ats.worker")


def _default_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


async def _process_one(
    settings: Settings,
    sessionmaker: Any,
    blobs: BlobStore,
    claimed: dict[str, Any],
) -> None:
    run_id = int(claimed["id"])
    org_id = int(claimed["org_id"])
    inputs = claimed["queued_inputs"] or {}

    jd_blob_key = inputs.get("jd_blob_key")
    resume_blob_keys: list[str] = list(inputs.get("resume_blob_keys") or [])
    top_n = int(inputs.get("top_n") or 5)
    skip_optional = bool(inputs.get("skip_optional") or False)

    if not jd_blob_key or not resume_blob_keys:
        log.error(
            "queued run missing inputs", extra={"run_id": run_id, "inputs": inputs}
        )
        async with sessionmaker() as session:
            await mark_run_status(session, run_id, RunStatus.failed)
            await session.commit()
        return

    with tempfile.TemporaryDirectory(prefix=f"ats-run-{run_id}-") as tmp:
        tmp_path = Path(tmp)
        jd_local = tmp_path / Path(jd_blob_key).name
        jd_local.write_bytes(await blobs.get(jd_blob_key))

        resumes_dir = tmp_path / "resumes"
        resumes_dir.mkdir()
        for key in resume_blob_keys:
            (resumes_dir / Path(key).name).write_bytes(await blobs.get(key))

        try:
            summary = await run_pipeline(
                settings,
                jd_local,
                resumes_dir,
                top_n=top_n,
                skip_optional=skip_optional,
                org_id_override=org_id,
                existing_run_id=run_id,
                blob_store=blobs,
                sessionmaker_override=sessionmaker,
            )
            log.info(
                "run completed",
                extra={"run_id": run_id, "status": summary.get("status")},
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("run failed", extra={"run_id": run_id})
            async with sessionmaker() as session:
                await mark_run_status(session, run_id, RunStatus.failed)
                await session.commit()
            _ = exc


async def _loop(settings: Settings, worker_id: str, poll_s: float) -> None:
    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)
    blobs = BlobStore(settings)
    log.info("worker starting", extra={"worker_id": worker_id, "poll_s": poll_s})
    try:
        while True:
            async with sessionmaker() as session:
                claimed = await claim_next_queued_run(session, worker_id)
                await session.commit()
            if claimed is None:
                await asyncio.sleep(poll_s)
                continue
            await _process_one(settings, sessionmaker, blobs, claimed)
    finally:
        await engine.dispose()


def run_worker(
    settings: Settings,
    worker_id: str | None = None,
    poll_s: float = 3.0,
) -> None:
    """Entry point — blocks forever, processing runs as they arrive."""
    asyncio.run(_loop(settings, worker_id or _default_worker_id(), poll_s))
