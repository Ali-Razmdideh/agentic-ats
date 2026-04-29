"""In-memory fakes for tests that don't need real MinIO."""

from __future__ import annotations

import hashlib


class FakeBlobStore:
    """In-memory ``BlobStoreProtocol`` implementation."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    @staticmethod
    def _sha(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    async def ensure_bucket(self) -> None:
        return None

    async def put_resume(self, org_id: int, content: bytes, filename: str) -> str:
        sha = self._sha(content)
        key = f"orgs/{org_id}/resumes/{sha[:2]}/{sha}/{filename}"
        self.objects[key] = content
        return key

    async def put_jd(self, org_id: int, content: bytes, filename: str) -> str:
        sha = self._sha(content)
        key = f"orgs/{org_id}/jds/{sha}/{filename}"
        self.objects[key] = content
        return key

    async def get(self, key: str) -> bytes:
        return self.objects[key]

    async def presigned_url(self, key: str, expires_s: int = 300) -> str:
        return f"fake://{key}"

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)
