-- wtsagnt Monday WhatsApp slice — initial schema
-- Spec: docs/superpowers/specs/2026-05-17-monday-whatsapp-slice-design.md
-- RLS is intentionally OFF for the Monday single-phone demo. Hardening
-- pass post-Monday will scope to auth.uid() (or to phone via a sessions table).

create extension if not exists pgcrypto;

-- projects: one row per generation request
create table if not exists public.projects (
    id uuid primary key default gen_random_uuid(),
    phone text not null,
    original_request text not null,
    current_request text not null,
    state text not null default 'generating'
        check (state in ('generating','awaiting_approval','approved','delivered','error')),
    summary text,
    pptx_url text,
    pdf_url text,
    revision_count int not null default 0,
    error_reason text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists projects_phone_created_at_idx
    on public.projects (phone, created_at desc);

-- messages: every inbound and outbound WhatsApp message
create table if not exists public.messages (
    id uuid primary key default gen_random_uuid(),
    project_id uuid references public.projects(id) on delete set null,
    direction text not null check (direction in ('inbound','outbound')),
    provider_sid text,
    from_phone text not null,
    to_phone text not null,
    body text not null,
    created_at timestamptz not null default now()
);

-- partial UNIQUE on inbound provider_sid only — enforces webhook idempotency
-- without colliding with outbound SIDs returned by Twilio's send API
create unique index if not exists messages_inbound_provider_sid_unique
    on public.messages (provider_sid)
    where direction = 'inbound' and provider_sid is not null;

-- generations: every LLM API call (cost tracking + debugging)
create table if not exists public.generations (
    id uuid primary key default gen_random_uuid(),
    project_id uuid references public.projects(id) on delete cascade,
    step text not null check (step in (
        'revision_merge','intent','ppt_content','mcq','reckoner','reply_parse'
    )),
    model text not null,
    input_tokens int not null default 0,
    output_tokens int not null default 0,
    cost_cents int not null default 0,
    created_at timestamptz not null default now()
);

create index if not exists generations_project_id_idx
    on public.generations (project_id, created_at desc);

-- updated_at trigger on projects
create or replace function public.projects_set_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists projects_set_updated_at on public.projects;
create trigger projects_set_updated_at
    before update on public.projects
    for each row execute function public.projects_set_updated_at();

-- Storage bucket: 'lesson-files', private (signed URLs only)
insert into storage.buckets (id, name, public)
values ('lesson-files', 'lesson-files', false)
on conflict (id) do nothing;
