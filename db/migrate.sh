#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Starting database migrations..."

if [[ -z "${SUPABASE_DB_URL:-}" ]]; then
  echo "❌ ERROR: SUPABASE_DB_URL environment variable is not set"
  exit 1
fi

for file in db/migrations/*.sql; do
  echo "📄 Applying migration: $file"
  psql "$SUPABASE_DB_URL" \
    --set ON_ERROR_STOP=on \
    --single-transaction \
    -f "$file"
done

echo "✅ Database migrations completed successfully"