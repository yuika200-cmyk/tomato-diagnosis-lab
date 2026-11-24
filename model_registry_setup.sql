-- Execute in Supabase SQL editor once, using the same project as history_cloud.py.
-- Only authenticated users can read/write their own registry entries.
create table if not exists public.model_registrations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 80),
  model_type text not null check (model_type in ('株全体','葉','実')),
  model_url text not null check (char_length(model_url) <= 300),
  created_at timestamptz not null default now()
);
create index if not exists idx_model_registrations_owner_created
  on public.model_registrations (user_id, created_at desc);
alter table public.model_registrations enable row level security;
revoke all on public.model_registrations from anon;
grant select, insert, delete on public.model_registrations to authenticated;
drop policy if exists model_registry_select_own on public.model_registrations;
create policy model_registry_select_own on public.model_registrations for select to authenticated
  using (auth.uid() = user_id);
drop policy if exists model_registry_insert_own on public.model_registrations;
create policy model_registry_insert_own on public.model_registrations for insert to authenticated
  with check (auth.uid() = user_id);
drop policy if exists model_registry_delete_own on public.model_registrations;
create policy model_registry_delete_own on public.model_registrations for delete to authenticated
  using (auth.uid() = user_id);
