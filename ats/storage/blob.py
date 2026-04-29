"""MinIO/S3 blob store for resumes, JDs, and future attachments.

Wraps ``aioboto3``. Same code works against MinIO or real S3 — only the
endpoint URL differs.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import aioboto3

from ats.config import Settings
from ats.storage.files import hash_text

log = logging.getLogger("ats.storage.blob")


class BlobStoreProtocol(Protocol):
    async def put_resume(self, org_id: int, content: bytes, filename: str) -> str: ...
    async def put_jd(self, org_id: int, content: bytes, filename: str) -> str: ...
    async def get(self, key: str) -> bytes: ...
    async def presigned_url(self, key: str, expires_s: int = 300) -> str: ...
    async def delete(self, key: str) -> None: ...
    async def ensure_bucket(self) -> None: ...


def _hash_bytes(content: bytes) -> str:
    # Reuse the same algorithm hash_text uses for text; for bytes we hash
    # directly. Keeps content-addressing consistent with file_hash.
    import hashlib

    return hashlib.sha256(content).hexdigest()


def _resume_key(org_id: int, sha: str, filename: str) -> str:
    return f"orgs/{org_id}/resumes/{sha[:2]}/{sha}/{filename}"


def _jd_key(org_id: int, sha: str, filename: str) -> str:
    return f"orgs/{org_id}/jds/{sha}/{filename}"


class BlobStore:
    """Thin async wrapper over an S3-compatible store."""

    def __init__(self, settings: Settings) -> None:
        self._endpoint = settings.minio_endpoint
        self._access_key = settings.minio_access_key
        self._secret_key = settings.minio_secret_key
        self._bucket = settings.minio_bucket
        self._region = settings.minio_region
        self._session = aioboto3.Session()

    def _client(self) -> Any:
        return self._session.client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
        )

    async def ensure_bucket(self) -> None:
        from botocore.exceptions import ClientError

        async with self._client() as s3:
            try:
                await s3.head_bucket(Bucket=self._bucket)
                return
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                # 404 / NoSuchBucket → create. Anything else (403, network,
                # auth) is a real error and should surface, not be papered
                # over with a create_bucket call against a misconfigured
                # endpoint.
                if code not in ("404", "NoSuchBucket"):
                    raise
            await s3.create_bucket(Bucket=self._bucket)
            log.info("created bucket", extra={"bucket": self._bucket})

    async def _put(self, key: str, content: bytes, content_type: str) -> None:
        async with self._client() as s3:
            await s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
            )

    async def put_resume(self, org_id: int, content: bytes, filename: str) -> str:
        sha = _hash_bytes(content)
        key = _resume_key(org_id, sha, filename)
        await self._put(key, content, "application/octet-stream")
        return key

    async def put_jd(self, org_id: int, content: bytes, filename: str) -> str:
        sha = hash_text(content.decode("utf-8", errors="replace"))
        key = _jd_key(org_id, sha, filename)
        await self._put(key, content, "text/plain; charset=utf-8")
        return key

    async def get(self, key: str) -> bytes:
        async with self._client() as s3:
            obj = await s3.get_object(Bucket=self._bucket, Key=key)
            async with obj["Body"] as stream:
                data: bytes = await stream.read()
                return data

    async def presigned_url(self, key: str, expires_s: int = 300) -> str:
        async with self._client() as s3:
            url: str = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_s,
            )
            return url

    async def delete(self, key: str) -> None:
        async with self._client() as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)
