-- ==============================
-- Initial core tables
-- ==============================

create extension if not exists "pgcrypto";

create table if not exists matches (
  id uuid primary key default gen_random_uuid(),
  external_id text not null unique,
  home_team text not null,
  away_team text not null,
  status text not null check (status in ('scheduled', 'live', 'finished')),
  start_time timestamptz not null,
  created_at timestamptz default now()
);

create index if not exists idx_matches_status
  on matches(status);

create table if not exists match_events (
  id uuid primary key default gen_random_uuid(),
  match_id uuid not null references matches(id) on delete cascade,
  event_type text not null,
  event_minute int,
  event_key text not null,
  payload jsonb,
  created_at timestamptz default now(),
  unique (event_key)
);

create index if not exists idx_match_events_match_id
  on match_events(match_id);
