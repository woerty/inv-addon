# Stage 1: Build Frontend
FROM node:22-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --legacy-peer-deps
COPY frontend/ ./
RUN npm run build

# Stage 2: Production
# Python 3.13 is required by python-picnic-api2 >=1.3.3, which is the first
# version that exports Picnic2FARequired / Picnic2FAError. Earlier versions
# have no 2FA handling at all — the library just POSTs credentials and fails
# silently on 2FA challenges, breaking our web login flow.
FROM python:3.13-slim

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
RUN pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.34.0" \
    "sqlalchemy[asyncio]>=2.0.36" \
    "asyncpg>=0.30.0" \
    "alembic>=1.14.0" \
    "pydantic>=2.10.0" \
    "pydantic-settings>=2.7.0" \
    "httpx>=0.28.0" \
    "anthropic>=0.43.0" \
    "openai>=1.60.0" \
    "python-multipart>=0.0.18" \
    "python-picnic-api2>=1.3.3" \
    "rapidfuzz>=3.10.0"

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
