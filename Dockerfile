# syntax=docker/dockerfile:1.7

# ---------- Stage 1: build the SPA ----------
FROM --platform=$BUILDPLATFORM node:22-alpine AS frontend

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ ./
# vite.config.ts sets build.outDir to ../app/static, so the build output lands at
# /app/static (a sibling of this /build workdir), copied into the runtime image below.
RUN npm run build


# ---------- Stage 2: python dependencies ----------
FROM python:3.12-slim AS deps

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# build-essential and libffi are needed for bcrypt/asyncpg source builds on arm64
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./

ARG BACKENDS="all"
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install ".[${BACKENDS}]"


# ---------- Stage 3: runtime ----------
FROM python:3.12-slim AS runtime

# Release version, passed by the Docker workflow (YYYY.M.PATCH). Recorded as an
# OCI label and surfaced by the app (/api/v1/health) so the image tag and the
# reported version match.
ARG VERSION=dev

LABEL org.opencontainers.image.title="Mailsieve" \
      org.opencontainers.image.description="Self-hosted email validation API over the mailboxlayer verification endpoint" \
      org.opencontainers.image.source="https://github.com/t0mer/mailsieve" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.version="${VERSION}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    MAILSIEVE_CONFIG_FILE=/config/config.yaml \
    MAILSIEVE_VERSION=${VERSION}

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 mailsieve \
    && useradd -u 1000 -g mailsieve -m -s /usr/sbin/nologin mailsieve

COPY --from=deps /opt/venv /opt/venv

WORKDIR /app
COPY --chown=mailsieve:mailsieve app/ ./app/
COPY --chown=mailsieve:mailsieve alembic/ ./alembic/
COPY --chown=mailsieve:mailsieve alembic.ini ./
COPY --chown=mailsieve:mailsieve config.example.yaml ./
COPY --from=frontend --chown=mailsieve:mailsieve /app/static ./app/static

RUN mkdir -p /data /data/backups /config \
    && chown -R mailsieve:mailsieve /data /config

USER mailsieve

VOLUME ["/data", "/config"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8080/api/v1/health || exit 1

ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
