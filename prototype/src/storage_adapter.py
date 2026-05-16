"""Storage adapter — Supabase Storage for Monday. Google Drive / OneDrive
implementations land later behind the same Protocol."""
from __future__ import annotations
import asyncio
from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageAdapter(Protocol):
    async def upload(self, *, bucket: str, path: str, content: bytes, content_type: str) -> None: ...
    async def signed_url(self, *, bucket: str, path: str, expires_in_seconds: int) -> str: ...


class SupabaseStorageAdapter:
    """Wraps supabase-py's storage client. The underlying SDK is sync (httpx-based
    internally); we hop to a thread so we don't block the event loop."""

    def __init__(self, *, client) -> None:
        self._client = client

    async def upload(self, *, bucket: str, path: str, content: bytes, content_type: str) -> None:
        def _do() -> None:
            self._client.storage.from_(bucket).upload(
                path=path,
                file=content,
                file_options={"content-type": content_type, "upsert": "true"},
            )
        await asyncio.get_running_loop().run_in_executor(None, _do)

    async def signed_url(self, *, bucket: str, path: str, expires_in_seconds: int) -> str:
        def _do() -> str:
            r = self._client.storage.from_(bucket).create_signed_url(path, expires_in_seconds)
            # supabase-py returns {'signedURL': '...', 'signedUrl': '...'} depending on version
            return r.get("signedURL") or r.get("signedUrl") or r["signed_url"]
        return await asyncio.get_running_loop().run_in_executor(None, _do)
