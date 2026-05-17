"""Project state machine + CAS operations against supabase-py.

All state transitions use compare-and-swap: the UPDATE includes the expected
current state in the WHERE clause. If 0 rows return, another handler already
advanced the state; the caller exits silently. This eliminates duplicate
work under webhook races (double-tap APPROVE, race with revision arrival).
"""
from __future__ import annotations
from typing import Any, Optional

from postgrest.exceptions import APIError


def create_project(client, phone: str, body: str) -> dict:
    """Insert a brand-new projects row in state='generating'. Returns the row."""
    r = (
        client.table("projects")
        .insert({
            "phone": phone,
            "original_request": body,
            "current_request": body,
            "state": "generating",
            "revision_count": 0,
        })
        .execute()
    )
    return r.data[0]


def latest_project_for_phone(client, phone: str) -> Optional[dict]:
    """Return the most recent project for this phone, or None."""
    r = (
        client.table("projects")
        .select("*")
        .eq("phone", phone)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return r.data[0] if r.data else None


def get_project(client, project_id: str) -> Optional[dict]:
    r = client.table("projects").select("*").eq("id", project_id).limit(1).execute()
    return r.data[0] if r.data else None


def list_projects_for_phone(client, phone: str, limit: int = 20) -> list[dict]:
    """Return the most recent projects for a phone, newest first.

    Used by GET /projects to render a history view. No auth gating yet — the
    public RLS hardening pass adds that (caller supplies an auth.uid()-scoped
    query, not a phone param)."""
    r = (
        client.table("projects")
        .select("*")
        .eq("phone", phone)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return r.data or []


def insert_inbound_message(
    client,
    *,
    project_id: Optional[str],
    provider_sid: str,
    from_phone: str,
    to_phone: str,
    body: str,
) -> bool:
    """Insert an inbound message. Returns False if the partial-UNIQUE index
    rejects it (duplicate webhook). True on successful insert."""
    payload = {
        "project_id": project_id,
        "direction": "inbound",
        "provider_sid": provider_sid,
        "from_phone": from_phone,
        "to_phone": to_phone,
        "body": body,
    }
    try:
        client.table("messages").insert(payload).execute()
        return True
    except APIError as exc:
        # 23505 = unique_violation in Postgres
        if str(getattr(exc, "code", "")) == "23505" or "23505" in str(exc):
            return False
        raise


def insert_outbound_message(
    client,
    *,
    project_id: Optional[str],
    provider_sid: Optional[str],
    from_phone: str,
    to_phone: str,
    body: str,
) -> None:
    client.table("messages").insert({
        "project_id": project_id,
        "direction": "outbound",
        "provider_sid": provider_sid,
        "from_phone": from_phone,
        "to_phone": to_phone,
        "body": body,
    }).execute()


def _cas(client, project_id: str, expected: str, updates: dict[str, Any]) -> bool:
    """Conditional UPDATE. Returns True iff the update affected exactly the
    target row (i.e., the project was in the expected state)."""
    r = (
        client.table("projects")
        .update(updates)
        .eq("id", project_id)
        .eq("state", expected)
        .execute()
    )
    return bool(r.data)


def cas_to_awaiting_approval(
    client, project_id: str, *, summary: str, pptx_url: str, pdf_url: str
) -> bool:
    return _cas(client, project_id, expected="generating", updates={
        "state": "awaiting_approval",
        "summary": summary,
        "pptx_url": pptx_url,
        "pdf_url": pdf_url,
    })


def cas_to_approved(client, project_id: str) -> bool:
    return _cas(client, project_id, expected="awaiting_approval",
                updates={"state": "approved"})


def cas_to_delivered(client, project_id: str) -> bool:
    return _cas(client, project_id, expected="approved",
                updates={"state": "delivered"})


def cas_to_generating_for_revision(client, project_id: str, revision_body: str) -> bool:
    """Append the revision to current_request and bump revision_count, only
    if we're still in awaiting_approval. supabase-py's table-builder doesn't
    expose SQL expressions, so we read-modify-write within a single CAS update."""
    project = get_project(client, project_id)
    if project is None or project["state"] != "awaiting_approval":
        return False
    n = (project.get("revision_count") or 0) + 1
    new_request = (
        (project.get("current_request") or "")
        + f"\n\nRevision {n}: {revision_body}"
    )
    return _cas(client, project_id, expected="awaiting_approval", updates={
        "state": "generating",
        "current_request": new_request,
        "revision_count": n,
    })


def cas_to_error(client, project_id: str, *, error_reason: str,
                 expected_states: tuple[str, ...] = ("generating",)) -> bool:
    """Set state=error from any of expected_states. Returns True on a win."""
    for st in expected_states:
        if _cas(client, project_id, expected=st, updates={
            "state": "error",
            "error_reason": error_reason,
        }):
            return True
    return False


def insert_generation(
    client,
    *,
    project_id: str,
    step: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_cents: int,
) -> None:
    client.table("generations").insert({
        "project_id": project_id,
        "step": step,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_cents": cost_cents,
    }).execute()
