"""Smoke test: upload and signed-URL a small blob to the lesson-files bucket.
Skipped without Supabase env vars."""
import os
import uuid

import httpx
import pytest


REQUIRED = ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "SUPABASE_STORAGE_BUCKET")


@pytest.mark.skipif(
    any(not os.getenv(k) for k in REQUIRED),
    reason="Supabase env not set",
)
async def test_upload_and_signed_url_roundtrip():
    from src.storage_adapter import SupabaseStorageAdapter
    from supabase import create_client

    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])
    adapter = SupabaseStorageAdapter(client=client)

    bucket = os.environ["SUPABASE_STORAGE_BUCKET"]
    path = f"smoke/{uuid.uuid4()}.txt"
    content = b"wtsagnt storage smoke"

    await adapter.upload(bucket=bucket, path=path, content=content, content_type="text/plain")
    url = await adapter.signed_url(bucket=bucket, path=path, expires_in_seconds=60)

    async with httpx.AsyncClient() as http:
        r = await http.get(url)
    assert r.status_code == 200
    assert r.content == content
