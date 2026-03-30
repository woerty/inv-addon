#!/bin/bash
set -e

# Initialize Postgres data directory if needed
if [ ! -d "/data/postgres" ]; then
    mkdir -p /data/postgres
    chown postgres:postgres /data/postgres
    su - postgres -c "/usr/lib/postgresql/16/bin/initdb -D /data/postgres"
fi

# Ensure postgres owns the data dir
chown -R postgres:postgres /data/postgres

# Start Postgres temporarily to run migrations
su - postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D /data/postgres -l /tmp/pg_init.log start"

# Wait for Postgres to be ready
until su - postgres -c "pg_isready -q"; do
    sleep 1
done

# Create database and user if they don't exist
su - postgres -c "psql -tc \"SELECT 1 FROM pg_database WHERE datname = 'recipe'\" | grep -q 1 || psql -c \"CREATE DATABASE recipe\""
su - postgres -c "psql -tc \"SELECT 1 FROM pg_roles WHERE rolname = 'recipe'\" | grep -q 1 || psql -c \"CREATE USER recipe WITH PASSWORD 'recipe'\""
su - postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE recipe TO recipe\""
su - postgres -c "psql -d recipe -c \"GRANT ALL ON SCHEMA public TO recipe\""

# Run Alembic migrations
cd /app/backend
alembic upgrade head

# Stop temporary Postgres (Supervisor will restart it)
su - postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D /data/postgres stop"

# Start Supervisor (manages Postgres + uvicorn)
exec supervisord -c /app/supervisord.conf
