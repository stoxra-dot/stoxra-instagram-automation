-- Run manually in Supabase SQL editor. Uses isolated tables; no existing app data changes.
create table if not exists public.stoxra_publish_locks (
  account_id text primary key,
  owner uuid not null,
  acquired_at timestamptz not null default now()
);
create table if not exists public.stoxra_posts (
  post_key text primary key,
  account_id text not null,
  post jsonb not null,
  digest text not null,
  approved_digest text,
  review_digest text not null,
  media_hashes jsonb not null,
  evidence_digest text not null,
  status text not null check (status in ('prepared', 'container_ready', 'publishing', 'published')),
  urls jsonb not null default '[]',
  children jsonb not null default '[]',
  container_id text,
  instagram_post_id text,
  created_at timestamptz not null default now(),
  unique(account_id, digest)
);
alter table public.stoxra_posts enable row level security;
alter table public.stoxra_publish_locks enable row level security;
revoke all on public.stoxra_posts, public.stoxra_publish_locks from anon, authenticated;
grant all on public.stoxra_posts, public.stoxra_publish_locks to service_role;
create index if not exists stoxra_posts_history on public.stoxra_posts(account_id, created_at desc);
-- Public bucket contains ONLY rendered education JPEGs. Never upload metadata or credentials.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('stoxra-media', 'stoxra-media', true, 8388608, array['image/jpeg'])
on conflict (id) do nothing;
