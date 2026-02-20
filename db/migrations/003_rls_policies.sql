-- ==============================
-- Row Level Security Policies
-- ==============================

alter table predictions enable row level security;

-- Users can read their own predictions
create policy "users_read_own_predictions"
on predictions
for select
using (auth.uid() = user_id);

-- Users can insert predictions for themselves
create policy "users_insert_own_predictions"
on predictions
for insert
with check (auth.uid() = user_id);

-- Admin override (service role)
create policy "admin_full_access_predictions"
on predictions
for all
using (
  auth.role() = 'service_role'
);
