#!/bin/bash
set -e

# Wait for Postgres
echo "Waiting for PostgreSQL..."
until PGPASSWORD=$MT_POSTGRES_PASSWORD psql -h "$MT_POSTGRES_HOST" -U "$MT_POSTGRES_USER" -d "$MT_POSTGRES_DB" -c "SELECT 1" >/dev/null 2>&1; do
  sleep 1
done
echo "PostgreSQL is ready."

# Run migrations
echo "Running migrations..."
python -m memory_thread.cli migrate

# Start API server
echo "Starting MT API server..."
exec uvicorn memory_thread.api.server:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level warning
