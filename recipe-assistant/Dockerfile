# Stage 1: Build Frontend
FROM node:22-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Production
FROM python:3.12-slim

# Install PostgreSQL 16 + Supervisor
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gnupg2 lsb-release curl ca-certificates && \
    echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list && \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        postgresql-16 \
        supervisor && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY backend/pyproject.toml ./backend/
RUN pip install --no-cache-dir ./backend

# Copy backend
COPY backend/ ./backend/

# Copy frontend build
COPY --from=frontend-build /frontend/build ./frontend/build

# Copy container config
COPY supervisord.conf run.sh ./
RUN chmod +x run.sh

# Create data directory
RUN mkdir -p /data/postgres && chown postgres:postgres /data/postgres

EXPOSE 8080

ENTRYPOINT ["./run.sh"]
